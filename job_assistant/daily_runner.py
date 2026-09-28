"""
每日任务执行器 — 中心化管线 + 单用户匹配分发。

架构(V3 三表重构后):
1. 中心化管线(每日一次,非按用户):
   飞书源表同步 → Playwright 正文抓取 → LLM 岗位拆分
2. 单用户分发(每用户一次):
   positions 表匹配 → 写入用户飞书表 → 日报 → 推送

设计原则:
- 单用户失败不影响其他用户(外层捕获异常)
- 去重:已在主表或已关闭表的岗位不重复写入
- 失败降级:飞书写入失败不阻塞推送,WxPusher 失败不影响数据
"""
import time
import os
import fcntl
import logging
from datetime import datetime
from typing import List, Dict

from models import User, HashStore
from feishu_client import FeishuClient
from wxpusher_client import WxPusherClient
from scorer import score_job
from config import settings

logger = logging.getLogger(__name__)


def run_daily_pipeline(sync_full: bool = False, crawl_limit: int = 200,
                       enrich_limit: int = 200, crawl_workers: int = 1) -> Dict:
    """
    中心化数据管线(每日执行一次,非按用户):
    1. 飞书源表增量同步 → companies + announcements
    2. Playwright 正文抓取 → 更新 crawl_status
    3. LLM 岗位拆分 → positions 表

    Args:
        sync_full: True=全量同步(首次), False=增量
        crawl_limit: 本次抓取正文上限
        enrich_limit: 本次 LLM 拆岗上限

    Returns: 各阶段统计
    """
    import job_db
    from feishu_source import FeishuSourceSync
    from content_fetcher import fetch_announcement_contents
    from llm_enricher import run_enrichment

    job_db.init_db()
    result = {"sync": {}, "crawl": {}, "enrich": {}}

    # 1. 飞书源表同步
    try:
        syncer = FeishuSourceSync()
        result["sync"] = syncer.sync(full=sync_full)
        logger.info(f"源表同步完成: {result['sync']}")
    except Exception as e:
        logger.error(f"源表同步失败: {e}")
        result["sync"] = {"error": str(e)}

    # 2. 正文抓取
    try:
        result["crawl"] = fetch_announcement_contents(limit=crawl_limit, workers=crawl_workers)
        logger.info(f"正文抓取完成: {result['crawl']}")
    except Exception as e:
        logger.error(f"正文抓取失败: {e}")
        result["crawl"] = {"error": str(e)}

    # 3. LLM 岗位拆分
    try:
        result["enrich"] = run_enrichment(limit=enrich_limit)
        logger.info(f"LLM 拆岗完成: {result['enrich']}")
    except Exception as e:
        logger.error(f"LLM 拆岗失败: {e}")
        result["enrich"] = {"error": str(e)}

    return result


class UserRunLock:
    """用户级采集锁 — 防止同一用户的采集任务并发执行。

    使用 fcntl.flock 非阻塞排他锁,若锁已被持有则抛出 RuntimeError。
    锁文件路径: data/locks/{user_id}.lock
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        lock_dir = os.path.join(settings.DATA_DIR, "locks")
        os.makedirs(lock_dir, exist_ok=True)
        self.lock_path = os.path.join(lock_dir, f"{user_id}.lock")
        self.lock_fd = None

    def __enter__(self):
        self.lock_fd = open(self.lock_path, "w")
        try:
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            self.lock_fd.close()
            self.lock_fd = None
            raise RuntimeError(f"用户 {self.user_id} 的采集任务正在执行中,跳过本次")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock_fd:
            fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
            self.lock_fd.close()
            self.lock_fd = None


class DailyRunner:
    """单用户每日任务"""

    def __init__(self, user: User):
        self.user = user
        self.feishu = FeishuClient()
        self.wxpusher = WxPusherClient()
        self.hash_store = HashStore(user.id)
        from llm_client import LLMClient
        self.llm = LLMClient()

    def run(self, on_start=None) -> Dict:
        """执行完整流程,返回执行结果摘要。
        on_start: 可选回调,在成功获取锁后调用(用于发送"开始采集"通知)。
        """
        result = {
            "user_id": self.user.id,
            "new_jobs": 0,
            "closed_jobs": 0,
            "doc_url": "",
            "push_ok": False,
            "errors": [],
        }
        # 用户级采集锁:防止即时采集与每日定时任务并发写同一用户数据
        try:
            with UserRunLock(self.user.id):
                # 锁获取成功后才发送"开始采集"通知,避免重复通知
                if on_start:
                    try:
                        on_start()
                    except Exception:
                        pass
                return self._run_with_lock(result)
        except RuntimeError as e:
            # 锁被持有:另一采集任务正在执行,跳过本次
            logger.warning(str(e))
            result["errors"].append(str(e))
            return result

    def _run_with_lock(self, result: Dict) -> Dict:
        """持锁后的实际执行逻辑"""
        # 前置校验:用户必须完成 onboarding(有飞书多维表格 token)
        missing = []
        if not self.user.feishu_base_token:
            missing.append("feishu_base_token")
        if not self.user.feishu_table_id:
            missing.append("feishu_table_id")
        if not self.user.feishu_closed_table_id:
            missing.append("feishu_closed_table_id")
        if missing:
            msg = f"用户 {self.user.id} 未完成 onboarding,缺少飞书配置: {', '.join(missing)}。请先完成飞书应用安装流程。"
            logger.error(msg)
            result["errors"].append(msg)
            return result
        try:
            # 字段迁移:确保飞书表包含 schema 中定义的所有字段(如 行业/公司类型/难度)
            # 已存在的表若缺少新字段,写入会失败,所以这里自动补建
            self._ensure_table_fields()

            # === 校招专属:从 positions 表匹配(中心化管线 → 按需分发) ===
            from user_matcher import match_jobs_for_user
            scored = match_jobs_for_user(
                self.user.profile, llm_client=self.llm, max_per_company=5
            )
            # user_matcher 已完成 DB预筛 + 规则预筛 + AI评分 + 每公司≤5

            # 分离管培岗位到独立表格(校招用户)
            mt_jobs = [j for j in scored if j.get("管培项目")]
            regular_jobs = [j for j in scored if not j.get("管培项目")]
            if mt_jobs and self.user.feishu_mt_table_id:
                self._write_mt_jobs(mt_jobs)
                result["mt_jobs"] = len(mt_jobs)

            # 3. 去重 + 入库(普通岗位)
            new_jobs = self._dedupe_and_write(regular_jobs)
            result["new_jobs"] = len(new_jobs)

            # 4. 复查已有岗位在招状态,归档已关闭
            closed = self._recheck_and_archive()
            result["closed_jobs"] = len(closed)

            # 4. 生成日报文档
            date_str = datetime.now().strftime("%Y-%m-%d")
            doc_url = self._create_daily_report(date_str, new_jobs, closed)
            result["doc_url"] = doc_url

            # 5. 微信推送(WxPusher 已降级为可选辅助通道,主推送走飞书)
            if self.user.wxpusher_uid:
                result["push_ok"] = self.wxpusher.send_daily_summary(
                    self.user.wxpusher_uid, date_str, new_jobs, doc_url,
                    closed_count=len(closed),
                    major=self.user.profile.major,
                )

            # 6. 飞书交互卡片推送(主推送渠道): TOP3 摘要 + 表格链接
            if self.user.feishu_open_id:
                try:
                    self._send_daily_card(date_str, new_jobs, closed, doc_url)
                    logger.info(f"飞书日报卡片已发送: user_id={self.user.id}")
                except Exception as e:
                    logger.warning(f"飞书日报卡片发送失败,降级为纯文本: {e}")
                    # 降级:卡片发送失败时用纯文本消息,确保用户能收到通知
                    try:
                        major = self.user.profile.major.strip()
                        title = f"{major}招聘日报" if major else "招聘日报"
                        priority = sum(1 for j in new_jobs if j.get("综合推荐度") == "优先申请")
                        msg = (
                            f"📋 {title} {date_str}\n\n"
                            f"今日新增 {len(new_jobs)} 条岗位"
                            + (f"，归档关闭 {len(closed)} 条" if closed else "")
                            + f"。\n优先申请 {priority} 条。\n\n"
                            f"📄 完整日报：{doc_url}"
                        )
                        self.feishu.send_message(self.user.feishu_open_id, msg)
                    except Exception:
                        logger.warning("飞书纯文本降级消息也发送失败")

            # 7. 校招截止提醒(提前 3 天)
            self._check_deadline_reminders()

            # 8. 投递跟踪:复查已投递岗位状态
            self._check_applied_jobs()

        except Exception as e:
            logger.exception(f"用户 {self.user.id} 每日任务失败")
            result["errors"].append(str(e))

        return result

    def _ensure_table_fields(self):
        """
        字段迁移:确保用户的飞书表包含 schema 中定义的所有字段。
        已存在的表若缺少新字段(如 行业/公司类型/难度),写入记录会失败。
        这里对比 schema 与现有字段,自动补建缺失字段(幂等,已有则跳过)。
        """
        from schema import JOB_FIELDS, CLOSED_JOB_FIELDS

        tables = [
            (self.user.feishu_table_id, JOB_FIELDS),
            (self.user.feishu_closed_table_id, CLOSED_JOB_FIELDS),
        ]
        for table_id, fields_def in tables:
            if not table_id:
                continue
            try:
                existing = self.feishu.list_fields(self.user.feishu_base_token, table_id)
                existing_names = {f.get("field_name", "") for f in existing}
            except Exception as e:
                logger.warning(f"读取表字段失败 table={table_id}: {e}")
                continue
            for f in fields_def:
                name = f["name"]
                if name in existing_names:
                    continue
                kwargs = {}
                if "options" in f:
                    kwargs["property"] = {"options": f["options"]}
                if "style" in f:
                    kwargs["property"] = {**kwargs.get("property", {}), **f["style"]}
                try:
                    self.feishu.create_field(
                        self.user.feishu_base_token, table_id, name, f["type"], **kwargs
                    )
                    logger.info(f"补建字段: {name} (table={table_id})")
                    time.sleep(0.1)
                except Exception as e:
                    logger.warning(f"补建字段失败 {name}: {e}")

    def _bitable_url(self, table_id: str = None) -> str:
        """生成多维表格访问 URL(用于卡片中直达链接)"""
        base = self.user.feishu_base_token
        if not base:
            return ""
        domain = os.environ.get("FEISHU_DOMAIN", "www.feishu.cn")
        if table_id:
            return f"https://{domain}/base/{base}?table={table_id}"
        return f"https://{domain}/base/{base}"

    def _send_daily_card(self, date_str: str, new_jobs: List[Dict],
                         closed: List[Dict], doc_url: str):
        """
        发送飞书交互卡片:日报摘要 + TOP3 岗位 + 直达链接。
        这是主推送渠道(WxPusher 降级为可选)。
        """
        major = self.user.profile.major.strip()
        title = f"{major}招聘日报" if major else "招聘日报"
        priority_count = sum(1 for j in new_jobs if j.get("综合推荐度") == "优先申请")

        # TOP3 岗位(按相关性评分降序)
        top3 = sorted(new_jobs, key=lambda x: x.get("相关性评分", 0), reverse=True)[:3]

        # 构建卡片元素
        elements = []

        # 概览
        overview = (
            f"📊 **今日新增 {len(new_jobs)} 条** | 优先申请 {priority_count} 条"
            + (f" | 归档关闭 {len(closed)} 条" if closed else "")
        )
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": overview},
        })

        # TOP3 推荐
        if top3:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "**🔥 TOP 3 推荐岗位**"},
            })
            for i, j in enumerate(top3, 1):
                company = j.get("公司", "")
                pos = j.get("岗位标题", "")
                loc = j.get("地点", "")
                score = j.get("相关性评分", "?")
                rec = j.get("综合推荐度", "")
                brief = (j.get("简评", "") or "")[:80]
                content = (
                    f"**{i}. {company} · {pos}**\n"
                    f"📍 {loc} | 📈 相关性 {score} | {rec}\n"
                    f"_{brief}_"
                )
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": content},
                })

        # 直达链接
        elements.append({"tag": "hr"})
        job_table_url = self._bitable_url(self.user.feishu_table_id)
        closed_table_url = self._bitable_url(self.user.feishu_closed_table_id)
        actions = []
        if job_table_url:
            actions.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": "📋 岗位数据库"},
                "type": "primary",
                "url": job_table_url,
            })
        if closed_table_url:
            actions.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🗄️ 已关闭岗位"},
                "url": closed_table_url,
            })
        if doc_url:
            actions.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": "📄 完整日报"},
                "url": doc_url,
            })
        if actions:
            elements.append({"tag": "action", "actions": actions})

        # 底部备注
        elements.append({
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": "明天 9:00 继续为您推送 | 招聘情报助手"}],
        })

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"{title} {date_str}"},
                "template": "blue",
            },
            "elements": elements,
        }
        self.feishu.send_card_message(self.user.feishu_open_id, card)

    def _check_deadline_reminders(self):
        """
        校招截止提醒:检查主表中投递截止日期在 3 天内的岗位,飞书通知用户。
        仅对有截止日期且未过期的岗位提醒。
        """
        try:
            records = self.feishu.search_records(
                self.user.feishu_base_token, self.user.feishu_table_id,
                'AND(CurrentValue.[投递截止日期] != "")',
                fields=["岗位标题", "公司", "投递截止日期", "申请状态"],
            )
        except Exception as e:
            logger.warning(f"查询截止日期岗位失败: {e}")
            return

        now = datetime.now()
        deadline_jobs = []
        for r in records:
            fields = r.get("fields", {})
            deadline_ts = fields.get("投递截止日期")
            if not deadline_ts:
                continue
            # 飞书日期字段返回毫秒时间戳
            try:
                deadline_dt = datetime.fromtimestamp(int(deadline_ts) / 1000)
            except (ValueError, TypeError):
                continue
            days_left = (deadline_dt - now).days
            if 0 <= days_left <= 3:
                deadline_jobs.append({
                    "title": fields.get("岗位标题", ""),
                    "company": fields.get("公司", ""),
                    "deadline": deadline_dt.strftime("%Y-%m-%d"),
                    "days_left": days_left,
                    "status": fields.get("申请状态", "未投递"),
                })

        if not deadline_jobs:
            return

        # 发送飞书提醒
        lines = [f"⏰ **投递截止提醒**({len(deadline_jobs)}个岗位即将截止)\n"]
        for j in deadline_jobs:
            day_word = "今天" if j["days_left"] == 0 else f"{j['days_left']}天后"
            lines.append(
                f"• {j['company']} · {j['title']}\n"
                f"  截止: {j['deadline']} ({day_word}) | 状态: {j['status']}"
            )
        content = "\n".join(lines)
        msg = (
            f"⏰ 校招投递截止提醒\n\n{content}\n\n"
            f"请尽快投递,避免错过截止日期!"
        )
        try:
            self.feishu.send_message(self.user.feishu_open_id, msg)
            logger.info(f"截止提醒已发送: {len(deadline_jobs)} 个岗位")
        except Exception as e:
            logger.warning(f"截止提醒发送失败: {e}")

    def _check_applied_jobs(self):
        """
        投递跟踪:复查用户标记为"已投递/面试中"的岗位状态。
        若岗位已关闭,通知用户。
        """
        try:
            records = self.feishu.search_records(
                self.user.feishu_base_token, self.user.feishu_table_id,
                'OR(CurrentValue.[申请状态] = "已投递", CurrentValue.[申请状态] = "面试中")',
                fields=["岗位标题", "公司", "JD链接", "申请状态"],
            )
        except Exception as e:
            logger.warning(f"查询已投递岗位失败: {e}")
            return

        closed_applied = []
        for r in records[:15]:  # 限制复查数量
            rid = r.get("record_id", "")
            fields = r.get("fields", {})
            company = fields.get("公司", "")
            if isinstance(company, list):
                company = company[0].get("name", "") if company else ""
            title = fields.get("岗位标题", "")
            if isinstance(title, list):
                title = title[0].get("text", "") if title else ""
            if not rid:
                continue
            # 基于 positions 表检查是否已关闭(替代旧的 URL 抓取)
            if not self._is_position_active(company, title):
                closed_applied.append({
                    "title": title,
                    "company": company,
                    "status": fields.get("申请状态", ""),
                })
                # 将该岗位从主表移到已关闭表(复用归档逻辑)
                try:
                    full_fields = self.feishu.get_record(
                        self.user.feishu_base_token, self.user.feishu_table_id, rid)
                    norm = self.feishu.normalize_fields(full_fields)
                    close_ts = int(time.time() * 1000)
                    archive_record = {**norm, "是否在招": "否", "关闭日期": close_ts}
                    self.feishu.batch_create_records(
                        self.user.feishu_base_token, self.user.feishu_closed_table_id,
                        [archive_record])
                    self.feishu.delete_record(
                        self.user.feishu_base_token, self.user.feishu_table_id, rid)
                except Exception as e:
                    logger.warning(f"归档已投递关闭岗位失败: {e}")
            time.sleep(0.2)

        if closed_applied:
            lines = [f"📬 **投递状态更新**({len(closed_applied)}个已投递岗位已关闭)\n"]
            for j in closed_applied:
                lines.append(f"• {j['company']} · {j['title']} (原状态:{j['status']})")
            content = "\n".join(lines)
            msg = (
                f"📬 投递跟踪通知\n\n{content}\n\n"
                f"这些岗位已关闭,建议关注其他机会。"
            )
            try:
                self.feishu.send_message(self.user.feishu_open_id, msg)
                logger.info(f"投递跟踪通知已发送: {len(closed_applied)} 个岗位关闭")
            except Exception as e:
                logger.warning(f"投递跟踪通知发送失败: {e}")

    def _get_existing_hashes(self) -> set:
        """从主表+已关闭表读取已有 hash"""
        hashes = set()
        for table_id in [self.user.feishu_table_id, self.user.feishu_closed_table_id]:
            if not table_id:
                continue
            try:
                records = self.feishu.search_records(
                    self.user.feishu_base_token, table_id,
                    'AND(CurrentValue.[去重hash] != "")',
                    fields=["去重hash"],
                )
                for r in records:
                    h = r.get("fields", {}).get("去重hash", "")
                    if h:
                        hashes.add(h)
            except Exception as e:
                logger.warning(f"读取已有 hash 失败: {e}")
        return hashes

    def _filter_top_per_company(self, jobs: List[Dict], max_per_company: int = 5) -> List[Dict]:
        """
        校招用户:按企业分组,每家企业只保留匹配度最高的 top N 个岗位。

        逻辑:
        1. 按 company 字段分组
        2. 组内按"相关性评分"降序排序
        3. 取前 max_per_company 个
        4. 过滤掉评分极低(<=30)的岗位(不匹配)
        """
        if not jobs:
            return jobs

        from collections import defaultdict
        company_groups = defaultdict(list)
        unknown_company = []

        for j in jobs:
            # 过滤极低分岗位
            score = j.get("相关性评分", 0) or 0
            if score < 20:
                continue
            company = (j.get("company") or "").strip()
            if company and company != "未知":
                company_groups[company].append(j)
            else:
                unknown_company.append(j)

        result = []
        for company, group_jobs in company_groups.items():
            # 按评分降序,取前 N
            sorted_jobs = sorted(group_jobs, key=lambda x: x.get("相关性评分", 0), reverse=True)
            result.extend(sorted_jobs[:max_per_company])

        # 未知公司的岗位也保留(取前 20 个,避免过多)
        unknown_sorted = sorted(unknown_company, key=lambda x: x.get("相关性评分", 0), reverse=True)
        result.extend(unknown_sorted[:20])

        logger.info(f"企业分组筛选: {len(jobs)} → {len(result)} 条(覆盖 {len(company_groups)} 家企业)")
        return result

    def _dedupe_and_write(self, jobs: List[Dict]) -> List[Dict]:
        """去重后写入主表,返回新增的岗位"""
        existing = self._get_existing_hashes()
        new_jobs = [j for j in jobs if j["去重hash"] not in existing
                    and not self.hash_store.exists(j["去重hash"])]
        if new_jobs:
            try:
                self.feishu.batch_create_records(
                    self.user.feishu_base_token, self.user.feishu_table_id,
                    new_jobs,
                )
                for j in new_jobs:
                    self.hash_store.add(j["去重hash"])
                logger.info(f"写入 {len(new_jobs)} 条新岗位")
            except Exception as e:
                logger.error(f"写入岗位失败: {e}")
                return []
        return new_jobs

    def _write_mt_jobs(self, mt_jobs: List[Dict]):
        """将管培岗位写入管培项目独立表格"""
        from datetime import datetime
        cur_year = datetime.now().year
        next_year = cur_year + 1

        # 管培类型映射
        mt_type_map = {
            "finance": "金融管培",
            "internet": "互联网管培",
            "consulting_fmcg": "快消管培",  # 简化映射
            "soe": "国企管培",
            "all": "综合管培",
        }
        mt_pref = getattr(self.user.profile, "mt_program_preference", "all") or "all"
        default_mt_type = mt_type_map.get(mt_pref, "综合管培")

        mt_records = []
        for j in mt_jobs:
            company = j.get("公司", "未知")
            title = j.get("岗位标题", "")
            # 项目名称 = 公司 + 管培项目名
            project_name = f"{company} · {title}" if company != "未知" else title

            # 推断届数
            cohort = f"{next_year}届"
            for y in (cur_year, next_year):
                if f"{y}届" in j.get("JD摘要", "") or f"{y}届" in title:
                    cohort = f"{y}届"
                    break

            mt_records.append({
                "项目名称": project_name,
                "公司": company,
                "管培类型": default_mt_type,
                "届数": cohort,
                "招聘阶段": "网申中",  # 默认网申中,后续可更新
                "地点": j.get("地点", ""),
                "项目介绍": j.get("JD摘要", "")[:500],
                "申请要求": j.get("经验要求", "") + " " + j.get("学历要求", ""),
                "网申链接": j.get("JD链接", ""),
                "截止日期": j.get("投递截止日期", ""),
                "综合推荐度": j.get("综合推荐度", "可申请"),
                "相关性评分": j.get("相关性评分", 0),
                "申请状态": "未投递",
                "去重hash": j.get("去重hash", ""),
                "来源": j.get("来源", "搜索"),
                "抓取日期": int(time.time() * 1000),
            })

        if not mt_records:
            return

        try:
            self.feishu.batch_create_records(
                self.user.feishu_base_token, self.user.feishu_mt_table_id,
                mt_records,
            )
            logger.info(f"写入 {len(mt_records)} 条管培项目到独立表格")
        except Exception as e:
            logger.error(f"写入管培项目失败: {e}")

    def _is_position_active(self, company: str, title: str) -> bool:
        """检查岗位在 positions 表中是否仍在招(替代旧的 URL 抓取复查)。"""
        import job_db
        try:
            positions = job_db.get_positions_by_company(company)
            if not positions:
                return True  # 公司不在库中,保守认为在招(避免误归档)
            # 模糊匹配岗位标题
            title_lower = (title or "").lower()
            for p in positions:
                if title_lower and title_lower in (p.get("position_title", "") or "").lower():
                    return True
            # 公司在库但无匹配岗位,可能已关闭
            return False
        except Exception:
            return True  # 出错时保守认为在招

    def _recheck_and_archive(self) -> List[Dict]:
        """复查主表在招岗位,关闭的归档到已关闭表(基于 positions 表状态)"""
        closed = []
        try:
            records = self.feishu.search_records(
                self.user.feishu_base_token, self.user.feishu_table_id,
                'AND(CurrentValue.[是否在招] = "是")',
                fields=["岗位标题", "公司", "JD链接"],
            )
        except Exception as e:
            logger.warning(f"查询在招岗位失败: {e}")
            return closed

        records = records[:20]
        for r in records:
            rid = r.get("record_id", "")
            fields = r.get("fields", {})
            company = fields.get("公司", "")
            if isinstance(company, list):
                company = company[0].get("name", "") if company else ""
            title = fields.get("岗位标题", "")
            if isinstance(title, list):
                title = title[0].get("text", "") if title else ""
            if not rid:
                continue
            # 基于 positions 表检查是否仍在招
            if not self._is_position_active(company, title):
                try:
                    # 拉取完整记录
                    full_fields = self.feishu.get_record(
                        self.user.feishu_base_token, self.user.feishu_table_id, rid)
                    # 归一化字段格式
                    norm = self.feishu.normalize_fields(full_fields)
                    # 写入已关闭表(关闭日期需转毫秒时间戳,飞书日期字段不接受字符串)
                    close_ts = int(time.time() * 1000)
                    archive_record = {**norm, "是否在招": "否", "关闭日期": close_ts}
                    self.feishu.batch_create_records(
                        self.user.feishu_base_token, self.user.feishu_closed_table_id,
                        [archive_record],
                    )
                    # 从主表删除
                    self.feishu.delete_record(
                        self.user.feishu_base_token, self.user.feishu_table_id, rid)
                    closed.append(norm)
                    logger.info(f"归档关闭岗位: {norm.get('公司','')} {norm.get('岗位标题','')}")
                except Exception as e:
                    logger.warning(f"归档岗位失败: {e}")
            time.sleep(0.2)
        return closed

    def _create_daily_report(self, date_str: str, new_jobs: List[Dict],
                             closed: List[Dict]) -> str:
        """生成日报文档,返回文档 URL"""
        # 标题通用化:有专业则用"专业招聘日报",否则用"招聘日报",避免行业硬编码
        major = self.user.profile.major.strip()
        title_prefix = f"{major}招聘日报" if major else "招聘日报"
        title = f"{title_prefix} {date_str}"
        doc_id, url = self.feishu.create_doc(title)

        blocks = []
        # 概览
        blocks.append({
            "block_type": 2,  # text
            "text": {"elements": [{"text_run": {"content": (
                f"今日新增 {len(new_jobs)} 条岗位"
                + (f",归档关闭 {len(closed)} 条" if closed else "")
                + f"。\n优先申请 {sum(1 for j in new_jobs if j.get('综合推荐度')=='优先申请')} 条。"
            )}}], "style": {}},
        })

        # TOP 推荐
        if new_jobs:
            blocks.append({"block_type": 4, "heading2": {
                "elements": [{"text_run": {"content": "TOP 推荐"}}], "style": {}}})
            top = sorted(new_jobs, key=lambda x: x.get("相关性评分", 0), reverse=True)[:5]
            for j in top:
                blocks.append({"block_type": 2, "text": {
                    "elements": [{"text_run": {"content": (
                        f"【{j.get('综合推荐度','')}】{j.get('公司','')} · {j.get('岗位标题','')}\n"
                        f"地点: {j.get('地点','')} | 相关性: {j.get('相关性评分','')} | 难度: {j.get('难度评分','')}\n"
                        f"简评: {j.get('简评','')}\n"
                        f"建议: {j.get('申请建议','')}\n"
                    )}}], "style": {}}})

        # 已关闭岗位
        if closed:
            blocks.append({"block_type": 4, "heading2": {
                "elements": [{"text_run": {"content": "今日关闭岗位"}}], "style": {}}})
            for c in closed[:10]:
                blocks.append({"block_type": 2, "text": {
                    "elements": [{"text_run": {"content": (
                        f"{c.get('公司','')} · {c.get('岗位标题','')} ({c.get('地点','')})"
                    )}}], "style": {}}})

        try:
            self.feishu.append_doc_blocks(doc_id, blocks)
            # 分享给用户(仅当用户有 feishu_open_id 时)
            if self.user.feishu_open_id:
                self.feishu.share_with_user(doc_id, "docx", self.user.feishu_open_id)
            else:
                logger.warning("用户无 feishu_open_id,跳过日报文档分享")
        except Exception as e:
            logger.warning(f"写入日报文档失败: {e}")

        return url
