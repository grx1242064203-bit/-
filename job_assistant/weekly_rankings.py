"""
每周校招投递热度榜 — 统计所有校招用户的投递数据,生成专业热度榜。

设计原则:
1. 仅统计 role=campus 的用户(校招专属)
2. 按岗位聚类(公司+岗位标题归一化),统计"已投递"次数
3. 生成 TOP10 热度榜文档,推送给所有校招用户
4. 每周一执行(由 cron 调度)
"""
import logging
from collections import Counter
from datetime import datetime
from typing import Dict, List

from models import UserStore
from feishu_client import FeishuClient
from scorer import _normalize_for_hash

logger = logging.getLogger(__name__)


def collect_campus_applications(store: UserStore = None,
                                client: FeishuClient = None) -> List[Dict]:
    """
    收集所有校招用户的已投递岗位,返回标准化列表。
    每条: {company, title, hash, major}
    """
    store = store or UserStore()
    client = client or FeishuClient()

    campus_users = [u for u in store.list_active()
                    if (u.profile.role or "") == "campus" and u.feishu_base_token]

    all_jobs = []
    for user in campus_users:
        try:
            records = client.search_records(
                user.feishu_base_token, user.feishu_table_id,
                'OR(CurrentValue.[申请状态] = "已投递", CurrentValue.[申请状态] = "面试中", CurrentValue.[申请状态] = "Offer")',
                fields=["岗位标题", "公司"],
            )
            for r in records:
                fields = r.get("fields", {})
                company = fields.get("公司", "")
                title = fields.get("岗位标题", "")
                if not company or not title:
                    continue
                h = _normalize_for_hash(company) + "|" + _normalize_for_hash(title)
                all_jobs.append({
                    "company": company,
                    "title": title,
                    "hash": h,
                    "major": user.profile.major,
                })
        except Exception as e:
            logger.warning(f"读取用户 {user.id} 投递数据失败: {e}")

    return all_jobs


def build_ranking(jobs: List[Dict], top_n: int = 10) -> List[Dict]:
    """
    构建热度榜:按 hash 聚类统计投递次数,返回 TOP N。
    每条: {rank, company, title, count, majors}
    """
    counter: Counter = Counter()
    major_map: Dict[str, set] = {}

    for j in jobs:
        counter[j["hash"]] += 1
        if j["hash"] not in major_map:
            major_map[j["hash"]] = set()
        if j["major"]:
            major_map[j["hash"]].add(j["major"])

    # 取原始公司+标题(用第一个出现的)
    name_map: Dict[str, Dict] = {}
    for j in jobs:
        if j["hash"] not in name_map:
            name_map[j["hash"]] = {"company": j["company"], "title": j["title"]}

    ranking = []
    for i, (h, count) in enumerate(counter.most_common(top_n), 1):
        info = name_map.get(h, {"company": "未知", "title": "未知"})
        ranking.append({
            "rank": i,
            "company": info["company"],
            "title": info["title"],
            "count": count,
            "majors": sorted(major_map.get(h, set())),
        })
    return ranking


def generate_ranking_doc(ranking: List[Dict], week_str: str) -> str:
    """
    生成热度榜飞书文档,返回文档 URL。
    """
    client = FeishuClient()
    title = f"校招投递热度榜 {week_str}"
    doc_id, url = client.create_doc(title)

    blocks = []
    blocks.append({
        "block_type": 2,
        "text": {"elements": [{"text_run": {"content": (
            f"统计周期: {week_str}\n"
            f"数据来源: 校招用户投递标记\n"
            f"共统计 {len(ranking)} 个热门岗位\n"
        )}}], "style": {}},
    })
    blocks.append({"block_type": 4, "heading2": {
        "elements": [{"text_run": {"content": "TOP 10 热门岗位"}}], "style": {}}})

    for item in ranking:
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(item["rank"], f"{item['rank']}.")
        major_str = "、".join(item["majors"][:3]) if item["majors"] else "多专业"
        content = (
            f"{medal} {item['company']} · {item['title']}\n"
            f"   投递次数: {item['count']} | 主要专业: {major_str}"
        )
        blocks.append({"block_type": 2, "text": {
            "elements": [{"text_run": {"content": content}}], "style": {}}})

    blocks.append({"block_type": 4, "heading2": {
        "elements": [{"text_run": {"content": "说明"}}], "style": {}}})
    blocks.append({"block_type": 2, "text": {
        "elements": [{"text_run": {"content": (
            "本榜单基于招聘情报助手校招用户的投递标记统计,仅供参考。"
            "投递次数越多说明竞争越激烈,建议结合自身情况理性投递。"
        )}}], "style": {}}})

    try:
        client.append_doc_blocks(doc_id, blocks)
    except Exception as e:
        logger.warning(f"写入热度榜文档失败: {e}")

    return url


def push_ranking_to_campus_users(doc_url: str, ranking: List[Dict],
                                 store: UserStore = None):
    """
    将热度榜推送给所有校招用户(飞书消息)。
    """
    store = store or UserStore()
    client = FeishuClient()
    campus_users = [u for u in store.list_active()
                    if (u.profile.role or "") == "campus" and u.feishu_open_id]

    # 构造卡片消息
    elements = []
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md",
                 "content": f"📊 本周校招投递热度榜已更新,共 {len(ranking)} 个热门岗位。"},
    })
    for item in ranking[:5]:
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(item["rank"], f"{item['rank']}.")
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md",
                     "content": f"{medal} **{item['company']} · {item['title']}** — {item['count']}人投递"},
        })
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "action",
        "actions": [{
            "tag": "button",
            "text": {"tag": "plain_text", "content": "📄 查看完整热度榜"},
            "type": "primary",
            "url": doc_url,
        }],
    })

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "🔥 校招投递热度榜"},
            "template": "orange",
        },
        "elements": elements,
    }

    sent = 0
    for user in campus_users:
        try:
            if client.send_card_message(user.feishu_open_id, card):
                sent += 1
        except Exception as e:
            logger.warning(f"推送热度榜给用户 {user.id} 失败: {e}")

    logger.info(f"热度榜已推送给 {sent}/{len(campus_users)} 名校招用户")


def run_weekly_ranking():
    """执行每周热度榜统计 + 生成文档 + 推送"""
    logger.info("开始执行每周校招投递热度榜...")
    now = datetime.now()
    week_str = now.strftime("%Y年第%W周")

    jobs = collect_campus_applications()
    logger.info(f"收集到校招投递记录 {len(jobs)} 条")

    if not jobs:
        logger.info("暂无校招投递数据,跳过热度榜生成")
        return

    ranking = build_ranking(jobs, top_n=10)
    doc_url = generate_ranking_doc(ranking, week_str)
    logger.info(f"热度榜文档已生成: {doc_url}")

    push_ranking_to_campus_users(doc_url, ranking)
    logger.info("每周校招投递热度榜执行完成")
