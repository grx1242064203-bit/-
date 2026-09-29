"""
公司地位评级脚本 — 批量给已有公司打 company_tier(顶/中/保底),不重跑拆岗。

按公司去重(179家),每批15家调一次 LLM,输出 JSON 映射。
结果写入 positions.company_tier(同公司所有岗位同步更新)。
缓存:data/company_tier_cache/{company_id}.json,支持断点续跑。
"""
import hashlib
import json
import logging
import os
import sqlite3
import time
from typing import Dict, List, Optional

from config import settings
from llm_client import LLMClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB = os.path.join(settings.DATA_DIR, "jobs.db")
CACHE_DIR = os.path.join(settings.DATA_DIR, "company_tier_cache")
BATCH_SIZE = 15

_TIER_PROMPT = """你是资深校招HR。请根据公司名称和行业,判断该公司在校招市场的行业地位(竞争激烈程度)。

公司列表(JSON):
{companies_json}

对每家公司输出一个对象,字段:
- company_id: 输入的 id
- tier: "顶" / "中" / "保底"
  - 顶: 行业头部公司,校招竞争极激烈(如BAT、华为、大疆、中金、宁德时代、字节、腾讯、美团等)
  - 中: 行业内有一定知名度的中型公司,竞争中等
  - 保底: 普通中小公司,竞争较小
- reason: 20字内判断依据

输出严格 JSON 数组,不要输出 JSON 以外的文字。
注意:只根据公司知名度和行业地位判断,不要考虑岗位方向。不确定的公司填"中"。
"""


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def _cache_path(company_id: int) -> str:
    return os.path.join(CACHE_DIR, f"{company_id}.json")


def _load_cached(company_id: int) -> Optional[str]:
    path = _cache_path(company_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("tier")
        except Exception:
            return None
    return None


def _save_cache(company_id: int, tier: str, reason: str = ""):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_cache_path(company_id), "w", encoding="utf-8") as f:
        json.dump({"tier": tier, "reason": reason, "ts": int(time.time())}, f, ensure_ascii=False)


def fetch_companies() -> List[Dict]:
    """获取所有已分析公告的独立公司(含 industry + 公告数 + 岗位数)。"""
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT c.id, c.name, c.industry,
                   COUNT(DISTINCT a.id) as ann_count,
                   COUNT(p.id) as pos_count
            FROM announcements a
            JOIN companies c ON a.company_id = c.id
            LEFT JOIN positions p ON p.announcement_id = a.id
            WHERE a.llm_status = 'success'
            GROUP BY c.id
            ORDER BY c.name
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def batch_rate(llm: LLMClient, batch: List[Dict]) -> Dict[int, str]:
    """批量评级,返回 {company_id: tier}。"""
    companies_json = json.dumps(
        [{"id": c["id"], "name": c["name"], "industry": c["industry"]} for c in batch],
        ensure_ascii=False,
    )
    prompt = _TIER_PROMPT.format(companies_json=companies_json)
    result_text = llm._chat(
        [{"role": "user", "content": prompt}],
        temperature=0.0, max_tokens=2000,
    )
    if not result_text:
        return {}
    # 解析 JSON
    text = result_text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
        # LLM 可能返回 {"type":"json_object","content":[...]} 或 {"type":"json_object","value":[...]}
        if isinstance(data, dict):
            data = data.get("content") or data.get("value") or data
    except json.JSONDecodeError:
        # 尝试截取第一个 [ 到最后一个 ]
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end + 1])
            except Exception:
                logger.warning(f"批量 JSON 解析失败: {result_text[:300]}")
                return {}
        else:
            return {}

    out: Dict[int, str] = {}
    if not isinstance(data, list):
        return out
    for item in data:
        if not isinstance(item, dict):
            continue
        cid = item.get("company_id") or item.get("id")
        tier = (item.get("tier") or "").strip()
        if cid and tier in ("顶", "中", "保底"):
            out[int(cid)] = tier
            _save_cache(int(cid), tier, item.get("reason", ""))
    return out


def update_positions(company_id: int, tier: str):
    """更新该公司所有岗位的 company_tier。"""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE positions SET company_tier = ? WHERE company_id = ?",
            (tier, company_id),
        )
        conn.commit()
    finally:
        conn.close()


def main():
    companies = fetch_companies()
    logger.info(f"待评级公司: {len(companies)} 家")

    # 过滤已缓存的
    todo = []
    cached_count = 0
    for c in companies:
        tier = _load_cached(c["id"])
        if tier:
            cached_count += 1
            update_positions(c["id"], tier)
        else:
            todo.append(c)
    logger.info(f"已缓存: {cached_count}, 待 LLM 评级: {len(todo)}")

    if not todo:
        logger.info("全部已缓存,无需调用 LLM")
        return

    llm = LLMClient()
    total_rated = 0
    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i:i + BATCH_SIZE]
        batch_no = i // BATCH_SIZE + 1
        total_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE
        logger.info(f"批次 {batch_no}/{total_batches}: {len(batch)} 家公司")
        try:
            result = batch_rate(llm, batch)
            for cid, tier in result.items():
                update_positions(cid, tier)
            total_rated += len(result)
            logger.info(f"  成功评级 {len(result)}/{len(batch)} 家")
        except Exception as e:
            logger.error(f"批次 {batch_no} 失败: {e}")
        time.sleep(1)  # 避免限流

    logger.info(f"完成: 本次评级 {total_rated} 家,缓存 {cached_count} 家,合计 {cached_count + total_rated}/{len(companies)}")


if __name__ == "__main__":
    main()
