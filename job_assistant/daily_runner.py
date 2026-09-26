"""
每日任务执行器 — 为单个用户跑完整的采集→评分→入库→日报→推送。

设计原则:
- 单用户失败不影响其他用户(外层捕获异常)
- 去重:已在主表或已关闭表的岗位不重复写入
- 状态复查:对主表中"是否在招=是"的岗位复查 JD,关闭的归档
- 失败降级:飞书写入失败不阻塞推送,WxPusher 失败不影响数据
"""
import time
import logging
from datetime import datetime
from typing import List, Dict

from models import User, HashStore
from feishu_client import FeishuClient
from wxpusher_client import WxPusherClient
from collector import JobCollector
from scorer import score_job
from config import settings

logger = logging.getLogger(__name__)


class DailyRunner:
    """单用户每日任务"""

    def __init__(self, user: User):
        self.user = user
        self.feishu = FeishuClient()
        self.wxpusher = WxPusherClient()
        self.collector = JobCollector()
        self.hash_store = HashStore(user.id)

    def run(self) -> Dict:
        """执行完整流程,返回执行结果摘要"""
        result = {
            "user_id": self.user.id,
            "new_jobs": 0,
            "closed_jobs": 0,
            "doc_url": "",
            "push_ok": False,
            "errors": [],
        }
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
            # 1. 采集 + 评分
            raw_jobs = self.collector.collect(
                self.user.profile,
                self.user.profile.target_companies,
                self.user.profile.target_cities,
                limit=settings.DAILY_JOBS_PER_USER,
            )
            scored = [score_job(j, self.user.profile) for j in raw_jobs]

            # 2. 去重 + 入库
            new_jobs = self._dedupe_and_write(scored)
            result["new_jobs"] = len(new_jobs)

            # 3. 复查已有岗位在招状态,归档已关闭
            closed = self._recheck_and_archive()
            result["closed_jobs"] = len(closed)

            # 4. 生成日报文档
            date_str = datetime.now().strftime("%Y-%m-%d")
            doc_url = self._create_daily_report(date_str, new_jobs, closed)
            result["doc_url"] = doc_url

            # 5. 微信推送
            if self.user.wxpusher_uid:
                result["push_ok"] = self.wxpusher.send_daily_summary(
                    self.user.wxpusher_uid, date_str, new_jobs, doc_url,
                    closed_count=len(closed),
                    major=self.user.profile.major,
                )

        except Exception as e:
            logger.exception(f"用户 {self.user.id} 每日任务失败")
            result["errors"].append(str(e))

        return result

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

    def _recheck_and_archive(self) -> List[Dict]:
        """复查主表在招岗位,关闭的归档到已关闭表"""
        closed = []
        try:
            # 先查在招岗位的ID+URL(只查必要字段)
            records = self.feishu.search_records(
                self.user.feishu_base_token, self.user.feishu_table_id,
                'AND(CurrentValue.[是否在招] = "是")',
                fields=["JD链接"],
            )
        except Exception as e:
            logger.warning(f"查询在招岗位失败: {e}")
            return closed

        # 限制每日复查数量,避免请求过多(MVP 最多复查 20 条)
        records = records[:20]
        for r in records:
            rid = r.get("record_id", "")
            url = r.get("fields", {}).get("JD链接", "")
            if isinstance(url, dict):
                url = url.get("link", "")
            if not url or not rid:
                continue
            # 复查 JD 是否还在
            from collector import fetch_jd
            jd = fetch_jd(url, timeout=8)
            if not jd or "no longer" in jd.lower() or "已关闭" in jd or "404" in jd:
                try:
                    # 拉取完整记录
                    full_fields = self.feishu.get_record(
                        self.user.feishu_base_token, self.user.feishu_table_id, rid)
                    # 归一化字段格式
                    norm = self.feishu.normalize_fields(full_fields)
                    # 写入已关闭表
                    archive_record = {**norm, "是否在招": "否",
                                      "关闭日期": time.strftime("%Y-%m-%d %H:%M:%S")}
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
            blocks.append({"block_type": 3, "heading2": {
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
            blocks.append({"block_type": 3, "heading2": {
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
