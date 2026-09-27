"""
飞书秋招汇总表同步模块 — 主数据源。

数据源: https://dcn2fr2wam82.feishu.cn/base/WfgTb3wE3aSGhesttvack8innbh
表名: 27届实习秋招春招汇总 (10150 条记录)

职责:
1. 从飞书表拉取全部记录
2. 过滤校招类型(秋招/秋招提前批/春招/春招补招/春招补录)
3. 行业归一化(259→18类) + 企业性质归一化(19→5类)
4. 解析招聘对象届数范围(如"26届-27届" → min=2026, max=2027)
5. 写入 companies 表 + jobs 表(直接映射字段,岗位详情由 job_detail_analyzer 补全)
6. 数据源故障时通过飞书消息告警
"""
import re
import time
import logging
from typing import List, Dict, Tuple, Optional

from feishu_client import FeishuClient
from classify_mapping import normalize_industry, normalize_company_type, normalize_industries
import job_db

logger = logging.getLogger(__name__)

# 飞书表配置
BASE_TOKEN = "WfgTb3wE3aSGhesttvack8innbh"
TABLE_ID = "tblcBX0o8CIJlQQr"

# 校招招聘类型(纳入数据源)
CAMPUS_RECRUITMENT_TYPES = {"秋招", "秋招提前批", "春招", "春招补招", "春招补录"}

# 告警接收人 open_id(优先从环境变量 ALERT_OPEN_ID 读取,否则发给所有校招用户)
import os
from config import settings

ALERT_OPEN_ID = os.getenv("ALERT_OPEN_ID", "")


# ========== 届数解析 ==========

def parse_grade_range(target_text: str) -> Tuple[Optional[int], Optional[int]]:
    """
    解析招聘对象届数范围。

    示例:
      "27届" → (2027, 2027)
      "26届-27届" → (2026, 2027)
      "25届-27届" → (2025, 2027)
      "26-27届" → (2026, 2027)
      空/无法解析 → (None, None)
    """
    if not target_text:
        return None, None
    text = str(target_text).strip()
    # 匹配所有两位数届数(如 25, 26, 27)
    years = re.findall(r"(\d{2})\s*届?", text)
    if not years:
        # 尝试匹配四位数
        years = re.findall(r"20(\d{2})", text)
    if not years:
        return None, None
    nums = []
    for y in years:
        n = int(y)
        # 两位数补全为 20xx
        if n < 100:
            n += 2000
        # 合理范围校验
        if 2020 <= n <= 2035:
            nums.append(n)
    if not nums:
        return None, None
    return min(nums), max(nums)


# ========== 链接提取 ==========

def extract_url(field_value) -> str:
    """从飞书 URL 字段提取链接。字段格式: {"text": "...", "link": "..."} 或纯字符串"""
    if not field_value:
        return ""
    if isinstance(field_value, dict):
        return field_value.get("link", "") or field_value.get("text", "")
    if isinstance(field_value, list):
        for item in field_value:
            if isinstance(item, dict):
                return item.get("link", "") or item.get("text", "")
    return str(field_value)


# ========== 告警 ==========

def send_alert(message: str):
    """数据源故障告警 — 通过飞书消息发送"""
    try:
        client = FeishuClient()
        if ALERT_OPEN_ID:
            client.send_message(ALERT_OPEN_ID, f"[数据源告警] {message}")
            logger.info(f"告警已发送给 {ALERT_OPEN_ID}: {message}")
            return
        # 无指定 open_id:发给所有校招用户
        from models import UserStore
        store = UserStore()
        users = store.list_active()
        sent = 0
        for u in users:
            if u.profile.role == "campus" and u.feishu_open_id:
                if client.send_message(u.feishu_open_id, f"[数据源告警] {message}"):
                    sent += 1
        logger.info(f"告警已发送给 {sent} 名校招用户: {message}")
    except Exception as e:
        logger.error(f"告警发送失败: {e}")


# ========== 主同步逻辑 ==========

def fetch_all_records(client: FeishuClient = None) -> List[Dict]:
    """从飞书表拉取全部记录"""
    if client is None:
        client = FeishuClient()
    # 先验证表可访问
    try:
        tables = client.list_tables(BASE_TOKEN)
        if not any(t.get("table_id") == TABLE_ID for t in tables):
            send_alert(f"飞书表结构异常:未找到目标表 {TABLE_ID}")
            return []
    except Exception as e:
        send_alert(f"飞书表访问失败: {e}")
        return []

    all_records = []
    page_token = None
    page = 0
    while True:
        page += 1
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        try:
            data = client._request(
                "GET",
                f"/open-apis/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records",
                params=params,
            )
        except Exception as e:
            send_alert(f"飞书表第 {page} 页拉取失败: {e}")
            break
        items = data.get("items") or []
        all_records.extend(items)
        logger.info(f"飞书同步:第 {page} 页 {len(items)} 条,累计 {len(all_records)} 条")
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
        time.sleep(0.2)  # 避免触发限流

    if not all_records:
        send_alert("飞书表返回 0 条记录,可能数据源异常")
    return all_records


def _field(record: Dict, name: str):
    """从飞书记录中按字段名取字段值"""
    return record.get("fields", {}).get(name)


def sync_from_feishu() -> Dict:
    """
    全量同步飞书秋招汇总表到本地总数据库。

    流程:
    1. 拉取全部记录
    2. 过滤校招类型
    3. 归一化行业/企业性质
    4. 解析届数范围
    5. 写入 companies 表(去重)
    6. 写入 jobs 表(岗位标题=招聘岗位大类,detail_analyzed=0 等待 AI 分析)

    返回统计: {"total_records": N, "campus_records": N, "companies": N, "jobs_inserted": N}
    """
    logger.info("开始飞书秋招汇总表同步")
    records = fetch_all_records()
    if not records:
        return {"total_records": 0, "campus_records": 0, "companies": 0, "jobs_inserted": 0}

    # 公司元数据聚合
    company_meta: Dict[str, Dict] = {}
    # 待入库岗位
    jobs_to_insert: List[Dict] = []
    campus_count = 0

    for record in records:
        # 招聘类型可能是数组
        recruit_types = _field(record, "招聘类型") or []
        if isinstance(recruit_types, list):
            type_names = [t for t in recruit_types]
        else:
            type_names = [str(recruit_types)]
        # 判断是否校招
        is_campus = any(t in CAMPUS_RECRUITMENT_TYPES for t in type_names)
        if not is_campus:
            continue
        campus_count += 1

        company = str(_field(record, "公司名称") or "").strip()
        if not company:
            continue

        # 行业归一化
        raw_industries = _field(record, "公司行业") or []
        if isinstance(raw_industries, str):
            raw_industries = [raw_industries]
        industries = normalize_industries(raw_industries)
        primary_industry = industries[0] if industries else "其他"

        # 企业性质归一化
        raw_types = _field(record, "企业性质") or []
        if isinstance(raw_types, str):
            raw_types = [raw_types]
        company_type = normalize_company_type(raw_types[0]) if raw_types else "其他"

        # 地点
        locations = _field(record, "工作地点") or []
        if isinstance(locations, list):
            locations = ", ".join(str(x) for x in locations)
        else:
            locations = str(locations)

        # 公告链接
        announcement_url = extract_url(_field(record, "网申公告"))
        # 投递链接
        apply_url = extract_url(_field(record, "投递链接"))

        # 届数范围
        target_text = _field(record, "招聘对象") or ""
        if isinstance(target_text, list):
            target_text = " ".join(str(x) for x in target_text)
        min_grade, max_grade = parse_grade_range(target_text)

        # 学历
        education = _field(record, "学历") or ""
        if isinstance(education, list):
            education = ", ".join(str(x) for x in education)
        else:
            education = str(education)

        # 截止日期
        deadline = _field(record, "网申截止") or ""
        if isinstance(deadline, list):
            deadline = ", ".join(str(x) for x in deadline)
        else:
            deadline = str(deadline)

        # 招聘阶段(取校招类型)
        stage = next((t for t in type_names if t in CAMPUS_RECRUITMENT_TYPES), "秋招")

        # 岗位大类(用于初始入库,AI 分析后拆分为具体岗位)
        job_category = str(_field(record, "招聘岗位") or "").strip()
        if not job_category:
            job_category = "校招岗位"

        # 聚合公司元数据
        if company not in company_meta:
            company_meta[company] = {
                "industry": primary_industry,
                "company_type": company_type,
                "locations": locations,
                "announcement_url": announcement_url,
            }
        else:
            # 有公告链接就更新
            if announcement_url and not company_meta[company]["announcement_url"]:
                company_meta[company]["announcement_url"] = announcement_url

        # 构造岗位记录(初始版本,AI 分析会拆分+补全)
        jobs_to_insert.append({
            "company": company,
            "job_title": job_category,
            "department": "",
            "salary": "",
            "education": education,
            "locations": locations,
            "industry": primary_industry,
            "company_type": company_type,
            "difficulty": "",
            "recruitment_stage": stage,
            "target_min_grade": min_grade,
            "target_max_grade": max_grade,
            "apply_url": apply_url,
            "announcement_url": announcement_url,
            "jd_summary": "",
            "publish_time": "",
            "deadline": deadline,
            "is_fresh_graduate": True,
            "mt_program": False,
            "source": "feishu",
            "link_valid": True,
            "detail_analyzed": False,
        })

    # 写入公司表
    for name, meta in company_meta.items():
        job_db.upsert_company(
            name=name,
            industry=meta["industry"],
            company_type=meta["company_type"],
            locations=meta["locations"],
            announcement_url=meta["announcement_url"],
            source="feishu",
        )

    # 批量写入岗位表
    result = job_db.batch_insert_jobs(jobs_to_insert)

    stats = {
        "total_records": len(records),
        "campus_records": campus_count,
        "companies": len(company_meta),
        "jobs_inserted": result["inserted"],
        "jobs_skipped": result["skipped"],
    }
    logger.info(f"飞书同步完成: {stats}")

    # 异常检测:公司数较预期过少
    if len(company_meta) < 100:
        send_alert(f"飞书同步后公司数仅 {len(company_meta)},可能数据源异常")

    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    job_db.init_db()
    stats = sync_from_feishu()
    print(f"同步统计: {stats}")
