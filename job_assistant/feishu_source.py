"""
飞书秋招源表同步 — 从中心化数据源拉取招聘公告,归一化后写入三表。

设计原则(第一性):
1. 飞书源表是唯一权威数据源(人工维护、每日更新)
2. 系统不做爬虫发现,只做 ETL:拉取 → 过滤 → 归一化 → 入库
3. 增量同步:基于 last_modified_time,首次全量,之后只处理新增/变更
4. 只保留校招类型(秋招/提前批/春招/补招/补录),实习社招丢弃

数据流:
  飞书源表记录 → 过滤招聘类型 → 归一化行业/性质/届数
  → upsert companies(公司去重) → upsert announcements(公告入库)
"""
import json
import logging
import time
from typing import Dict, List, Optional, Tuple

from config import settings
from feishu_client import FeishuClient
import job_db
import normalizer

logger = logging.getLogger(__name__)

# === 源表字段名映射(若源表字段名调整,改这里即可) ===
# key = 内部字段名, value = 飞书源表字段名
SOURCE_FIELD_MAP = {
    "company_name": "公司名称",
    "announcement_title": "招聘岗位",
    "recruit_type": "招聘类型",
    "recruit_target": "招聘对象",
    "industry_raw": "公司行业",
    "company_type_raw": "公司性质",
    "location": "工作地点",
    "education_req": "学历要求",
    "apply_url": "网申链接",
    "announcement_url": "网申公告",
    "deadline": "投递截止日期",
    "publish_time": "发布时间",
    "apply_update": "网申更新",
}

# 字段名候选(源表字段名可能因版本不同有细微差异,按优先级匹配)
FIELD_ALIASES = {
    "company_name": ["公司名称", "公司", "企业名称"],
    "announcement_title": ["招聘岗位", "招聘职位", "岗位名称", "标题"],
    "recruit_type": ["招聘类型", "招聘阶段", "类型"],
    "recruit_target": ["招聘对象", "面向对象", "目标届数"],
    "industry_raw": ["公司行业", "行业", "所属行业"],
    "company_type_raw": ["公司性质", "企业性质", "公司类型", "企业类型"],
    "location": ["工作地点", "工作城市", "地点", "城市"],
    "education_req": ["学历要求", "学历", "教育要求"],
    "apply_url": ["网申链接", "投递链接", "申请链接", "网申地址"],
    "announcement_url": ["网申公告", "公告链接", "招聘公告", "详情链接"],
    "deadline": ["投递截止日期", "截止日期", "截止时间", "网申截止"],
    "publish_time": ["发布时间", "发布日期", "公告时间"],
    "apply_update": ["网申更新", "网申更新时间", "更新时间"],
}


def _extract_value(fields: Dict, internal_name: str) -> str:
    """
    从飞书记录的 fields 中提取字段值,返回纯文本。
    支持多种飞书字段格式的提取(text/select/url/datetime)。
    """
    # 优先用 SOURCE_FIELD_MAP,再尝试别名
    candidates = [SOURCE_FIELD_MAP.get(internal_name, "")] + FIELD_ALIASES.get(internal_name, [])
    raw_value = None
    for name in candidates:
        if name and name in fields:
            raw_value = fields[name]
            break
    if raw_value is None:
        return ""
    return _flatten_value(raw_value)


def _flatten_value(value) -> str:
    """将飞书字段值(多种格式)拍平为纯文本字符串。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        # 富文本数组 [{"text":"xx"}] 或 多选 [{"name":"xx"}]
        parts = []
        for item in value:
            if isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item["text"]))
                elif "name" in item:
                    parts.append(str(item["name"]))
                elif "link" in item:
                    parts.append(str(item.get("link", "")))
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts).strip()
    if isinstance(value, dict):
        # 单选 {"name":"xx"} 或 URL {"text":"xx","link":"xx"}
        if "name" in value:
            return str(value["name"]).strip()
        if "link" in value:
            return str(value["link"]).strip()
        if "text" in value:
            return str(value["text"]).strip()
        return str(value).strip()
    return str(value).strip()


def _extract_url(fields: Dict, internal_name: str) -> str:
    """专门提取 URL 字段值(优先 link,其次 text)。"""
    candidates = [SOURCE_FIELD_MAP.get(internal_name, "")] + FIELD_ALIASES.get(internal_name, [])
    for name in candidates:
        if name and name in fields:
            value = fields[name]
            if isinstance(value, dict):
                return value.get("link") or value.get("text") or ""
            if isinstance(value, str):
                return value
            return _flatten_value(value)
    return ""


def _extract_datetime(fields: Dict, internal_name: str) -> str:
    """提取日期字段,飞书返回毫秒时间戳,转为 YYYY-MM-DD。"""
    candidates = [SOURCE_FIELD_MAP.get(internal_name, "")] + FIELD_ALIASES.get(internal_name, [])
    for name in candidates:
        if name and name in fields:
            value = fields[name]
            if isinstance(value, (int, float)):
                # 毫秒时间戳 → 日期
                try:
                    return time.strftime("%Y-%m-%d", time.localtime(value / 1000))
                except Exception:
                    return ""
            if isinstance(value, str):
                return value.strip()[:10]  # 取 YYYY-MM-DD 部分
    return ""


class FeishuSourceSync:
    """飞书秋招源表同步器。"""

    def __init__(self, client: FeishuClient = None):
        self.client = client or FeishuClient()
        self.app_token = settings.SOURCE_APP_TOKEN
        self.table_id = settings.SOURCE_TABLE_ID

    def _fetch_all_records(self) -> List[Dict]:
        """拉取源表全部记录(自动分页)。每条含 record_id/fields/last_modified_time。"""
        logger.info(f"开始拉取源表: app={self.app_token} table={self.table_id}")
        app_token = self.client.resolve_app_token(self.app_token)
        all_records = []
        page_token = None
        page = 0
        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self.client._request(
                "GET",
                f"/open-apis/bitable/v1/apps/{app_token}/tables/{self.table_id}/records",
                params=params,
            )
            items = data.get("items") or []
            all_records.extend(items)
            page += 1
            if page % 10 == 0:
                logger.info(f"已拉取 {len(all_records)} 条...")
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            time.sleep(settings.FEISHU_API_INTERVAL)
        logger.info(f"源表拉取完成: 共 {len(all_records)} 条记录")
        return all_records

    def _process_record(self, record: Dict) -> Optional[Tuple[int, bool]]:
        """
        处理单条源表记录:过滤 → 归一化 → 写入 companies + announcements。
        返回 (announcement_id, is_new) 或 None(被过滤)。
        """
        fields = record.get("fields", {})
        record_id = record.get("record_id", "")
        last_modified = record.get("last_modified_time", 0)
        # last_modified_time 是毫秒时间戳,转为字符串存储
        last_modified_str = ""
        if last_modified:
            try:
                last_modified_str = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(last_modified / 1000)
                )
            except Exception:
                last_modified_str = str(last_modified)

        # 1. 提取字段
        company_name = _extract_value(fields, "company_name")
        recruit_type = _extract_value(fields, "recruit_type")
        if not company_name:
            return None

        # 2. 过滤:只保留校招类型
        if not normalizer.is_campus_recruit_type(recruit_type):
            return None

        # 3. 归一化
        industry_raw = _extract_value(fields, "industry_raw")
        company_type_raw = _extract_value(fields, "company_type_raw")
        industry = normalizer.normalize_industry(industry_raw)
        company_type = normalizer.normalize_company_type(company_type_raw)

        recruit_target = _extract_value(fields, "recruit_target")
        min_grade, max_grade = normalizer.parse_grade_range(recruit_target)

        # 4. 写 companies 表
        company_id = job_db.upsert_company(
            company_name, industry=industry, company_type=company_type,
            industry_raw=industry_raw, company_type_raw=company_type_raw,
        )

        # 5. 写 announcements 表
        ann_data = {
            "feishu_record_id": record_id,
            "company_name": company_name,
            "announcement_title": _extract_value(fields, "announcement_title"),
            "recruit_type": recruit_type,
            "recruit_target": recruit_target,
            "min_grade": min_grade,
            "max_grade": max_grade,
            "industry_raw": industry_raw,
            "company_type_raw": company_type_raw,
            "location": _extract_value(fields, "location"),
            "education_req": _extract_value(fields, "education_req"),
            "apply_url": _extract_url(fields, "apply_url"),
            "announcement_url": _extract_url(fields, "announcement_url"),
            "deadline": _extract_datetime(fields, "deadline"),
            "publish_time": _extract_datetime(fields, "publish_time"),
            "apply_update": _extract_datetime(fields, "apply_update"),
            "last_modified": last_modified_str,
        }
        ann_id, is_new = job_db.upsert_announcement(ann_data, company_id)
        return (ann_id, is_new)

    def sync(self, full: bool = False) -> Dict:
        """
        同步源表到本地数据库。

        增量策略(第一性原理):
        - 飞书 Bitable API 可能不返回 last_modified_time,业务字段 apply_update
          (网申更新日期)不能可靠代表记录新增/修改时间(可能回填/空值)。
        - 因此不再用 apply_update 做游标过滤,改为「全量拉取 + upsert 去重」:
          每次处理源表全部记录,upsert_announcement 按 feishu_record_id 去重,
          已存在则更新、不存在则插入。6000 条量级的 upsert 耗时数秒,可接受。
        - 若飞书返回 last_modified_time,则仅处理该时间晚于上次同步的记录(优化)。

        Args:
            full: 保留参数(兼容旧调用),当前逻辑始终全量处理。

        Returns: {"total": N, "processed": M, "new": K, "updated": U, "skipped": S}
        """
        job_db.init_db()
        records = self._fetch_all_records()

        total = len(records)
        processed = 0
        new_count = 0
        updated_count = 0
        skipped = 0

        # 取上次同步时间(用于 last_modified_time 优化,若可用)
        last_sync_ts = job_db.get_last_sync_timestamp()  # 秒级时间戳,0 表示无记录

        for record in records:
            # 优化:若飞书返回 last_modified_time,且记录未在上次同步后修改,则跳过
            mod_ts = record.get("last_modified_time", 0)
            if mod_ts and last_sync_ts > 0:
                if mod_ts / 1000 <= last_sync_ts:
                    skipped += 1
                    continue

            result = self._process_record(record)
            if result is None:
                skipped += 1
                continue
            _, is_new = result
            processed += 1
            if is_new:
                new_count += 1
            else:
                updated_count += 1

        # 记录本次同步时间戳(秒级)
        job_db.set_last_sync_timestamp(int(time.time()))

        logger.info(
            f"同步完成: 总计={total} 处理={processed} 新增={new_count} "
            f"更新={updated_count} 跳过={skipped}"
        )

        # 打印未命中归一化告警
        unmapped = normalizer.get_unmapped_stats()
        if unmapped:
            logger.warning(f"归一化未命中的原始值(需补充映射): {unmapped}")

        return {
            "total": total, "processed": processed, "new": new_count,
            "updated": updated_count, "skipped": skipped,
        }


def run_initial_sync():
    """首次全量同步(拉取所有源表记录)。"""
    syncer = FeishuSourceSync()
    return syncer.sync(full=True)


def run_daily_sync():
    """每日增量同步(只处理新增/变更记录)。"""
    syncer = FeishuSourceSync()
    return syncer.sync(full=False)
