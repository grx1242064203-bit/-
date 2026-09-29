"""
飞书数据备份模块 — 将 announcements 和 positions 同步到飞书多维表格。
作为异地备份,防止沙箱+git 同时丢失。

策略:增量同步,按 announcement_id / position_id 去重,只写入新增记录。
"""
import logging
import sqlite3
import os
import time
from typing import List, Dict, Set

from config import settings
from feishu_client import FeishuClient

logger = logging.getLogger(__name__)

# 飞书备份表的 app_token(创建后持久化到 data/feishu_backup_token)
TOKEN_FILE = os.path.join(settings.DATA_DIR, "feishu_backup_token")

# 表名
ANN_TABLE_NAME = "公告备份"
POS_TABLE_NAME = "岗位备份"


def _get_conn():
    conn = sqlite3.connect(os.path.join(settings.DATA_DIR, "jobs.db"))
    conn.row_factory = sqlite3.Row
    return conn


def _get_or_create_base(client: FeishuClient) -> str:
    """获取或创建飞书备份多维表格,返回 app_token。"""
    # 1. 读本地缓存的 token
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
        if token:
            return token

    # 2. 创建新的多维表格
    logger.info("创建飞书备份多维表格...")
    data = client._request(
        "POST", "/open-apis/bitable/v1/apps",
        json_body={"name": "校招数据备份", "folder_token": ""},
    )
    token = data["app"]["app_token"]
    with open(TOKEN_FILE, "w") as f:
        f.write(token)
    logger.info(f"飞书备份表已创建: {token}")
    return token


def _get_or_create_table(client: FeishuClient, app_token: str,
                          table_name: str, fields: List[Dict]) -> str:
    """获取或创建数据表,返回 table_id。"""
    # 列出已有表
    try:
        data = client._request(
            "GET", f"/open-apis/bitable/v1/apps/{app_token}/tables",
        )
    except Exception as e:
        logger.warning(f"列出飞书表失败: {e}")
        data = None
    items = (data or {}).get("items", []) if data else []
    for t in items:
        if t.get("name") == table_name:
            return t["table_id"]

    # 创建新表
    logger.info(f"创建数据表: {table_name}")
    data = client._request(
        "POST", f"/open-apis/bitable/v1/apps/{app_token}/tables",
        json_body={
            "table": {
                "name": table_name,
                "default_view_name": "全部",
                "fields": fields,
            }
        },
    )
    return data["table_id"]


def _get_existing_ids(client: FeishuClient, app_token: str,
                      table_id: str, id_field: str) -> Set[int]:
    """查询飞书表中已有的 id 集合,用于增量去重。"""
    existing = set()
    page_token = None
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        try:
            data = client._request(
                "GET",
                f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                params=params,
            )
        except Exception as e:
            logger.warning(f"查询飞书记录失败: {e}")
            break
        if not data:
            break
        for r in data.get("items", []) or []:
            fields = r.get("fields", {}) or {}
            val = fields.get(id_field)
            if val:
                try:
                    existing.add(int(val))
                except (ValueError, TypeError):
                    pass
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
        time.sleep(0.1)
    return existing


def sync_announcements(client: FeishuClient, app_token: str) -> Dict:
    """同步 announcements 表到飞书。"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, company_name, announcement_title, announcement_url, "
            "crawl_status, llm_status, positions_count, last_modified "
            "FROM announcements ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"total": 0, "synced": 0}

    # 字段定义
    fields = [
        {"field_name": "announcement_id", "type": 2},  # 数字
        {"field_name": "company_name", "type": 1},      # 文本
        {"field_name": "announcement_title", "type": 1},
        {"field_name": "announcement_url", "type": 1},
        {"field_name": "crawl_status", "type": 1},
        {"field_name": "llm_status", "type": 1},
        {"field_name": "positions_count", "type": 2},
        {"field_name": "last_modified", "type": 1},
    ]
    table_id = _get_or_create_table(client, app_token, ANN_TABLE_NAME, fields)

    # 查询已有 id
    existing = _get_existing_ids(client, app_token, table_id, "announcement_id")
    logger.info(f"[公告同步] 本地 {len(rows)} 条,飞书已有 {len(existing)} 条")

    # 只同步新增的
    to_sync = []
    for r in rows:
        if r["id"] in existing:
            continue
        to_sync.append({
            "announcement_id": r["id"],
            "company_name": r["company_name"] or "",
            "announcement_title": r["announcement_title"] or "",
            "announcement_url": r["announcement_url"] or "",
            "crawl_status": r["crawl_status"] or "",
            "llm_status": r["llm_status"] or "",
            "positions_count": r["positions_count"] or 0,
            "last_modified": r["last_modified"] or "",
        })

    if not to_sync:
        logger.info("[公告同步] 无新增,跳过")
        return {"total": len(rows), "synced": 0, "existing": len(existing)}

    # 批量写入
    logger.info(f"[公告同步] 待写入 {len(to_sync)} 条")
    client.batch_create_records(app_token, table_id, to_sync)
    return {"total": len(rows), "synced": len(to_sync), "existing": len(existing)}


def sync_positions(client: FeishuClient, app_token: str) -> Dict:
    """同步 positions 表到飞书。"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, announcement_id, company_name, position_title, "
            "job_category, city, min_education, is_management_trainee, "
            "company_tier, status, created_at "
            "FROM positions ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"total": 0, "synced": 0}

    fields = [
        {"field_name": "position_id", "type": 2},
        {"field_name": "announcement_id", "type": 2},
        {"field_name": "company_name", "type": 1},
        {"field_name": "position_title", "type": 1},
        {"field_name": "job_category", "type": 1},
        {"field_name": "city", "type": 1},
        {"field_name": "min_education", "type": 1},
        {"field_name": "is_management_trainee", "type": 1},
        {"field_name": "company_tier", "type": 1},
        {"field_name": "status", "type": 1},
        {"field_name": "created_at", "type": 1},
    ]
    table_id = _get_or_create_table(client, app_token, POS_TABLE_NAME, fields)

    existing = _get_existing_ids(client, app_token, table_id, "position_id")
    logger.info(f"[岗位同步] 本地 {len(rows)} 条,飞书已有 {len(existing)} 条")

    to_sync = []
    for r in rows:
        if r["id"] in existing:
            continue
        to_sync.append({
            "position_id": r["id"],
            "announcement_id": r["announcement_id"] or 0,
            "company_name": r["company_name"] or "",
            "position_title": r["position_title"] or "",
            "job_category": r["job_category"] or "",
            "city": r["city"] or "",
            "min_education": r["min_education"] or "",
            "is_management_trainee": str(r["is_management_trainee"] or ""),
            "company_tier": r["company_tier"] or "",
            "status": r["status"] or "",
            "created_at": r["created_at"] or "",
        })

    if not to_sync:
        logger.info("[岗位同步] 无新增,跳过")
        return {"total": len(rows), "synced": 0, "existing": len(existing)}

    logger.info(f"[岗位同步] 待写入 {len(to_sync)} 条")
    client.batch_create_records(app_token, table_id, to_sync)
    return {"total": len(rows), "synced": len(to_sync), "existing": len(existing)}


def sync_all() -> Dict:
    """全量同步:公告 + 岗位。"""
    client = FeishuClient()
    app_token = _get_or_create_base(client)

    result = {}
    try:
        result["announcements"] = sync_announcements(client, app_token)
    except Exception as e:
        logger.error(f"[公告同步] 失败: {e}")
        result["announcements"] = {"error": str(e)}

    try:
        result["positions"] = sync_positions(client, app_token)
    except Exception as e:
        logger.error(f"[岗位同步] 失败: {e}")
        result["positions"] = {"error": str(e)}

    logger.info(f"[飞书同步] 完成: {result}")
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sync_all()
