#!/usr/bin/env python3
"""重置20条skipped公告为pending并清除LLM缓存,用于测试重新拆岗效果。"""
import sqlite3, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm_enricher import _is_garbage_content, _content_hash, LLM_CACHE_DIR

conn = sqlite3.connect("data/jobs.db")
conn.row_factory = sqlite3.Row

# 选20条skipped: 10条有content, 10条无content
rows_with = conn.execute(
    "SELECT * FROM announcements WHERE llm_status='skipped' AND content IS NOT NULL AND content!='' LIMIT 10"
).fetchall()
rows_without = conn.execute(
    "SELECT * FROM announcements WHERE llm_status='skipped' AND (content IS NULL OR content='') LIMIT 10"
).fetchall()
rows = list(rows_with) + list(rows_without)

print(f"选中 {len(rows)} 条skipped公告 (有content={len(rows_with)}, 无content={len(rows_without)})")

cleared = 0
for r in rows:
    ann = dict(r)
    content = ann.get("content", "") or ""
    if not content or len(content) < 30 or _is_garbage_content(content):
        content = ann.get("announcement_title", "") or ""

    c_hash = _content_hash(content, company=ann.get("company_name", ""), title=ann.get("announcement_title", ""))
    cache_path = os.path.join(LLM_CACHE_DIR, f"{c_hash}.json")
    if os.path.exists(cache_path):
        os.remove(cache_path)
        cleared += 1

print(f"清除缓存文件: {cleared} 个")

ids = [r["id"] for r in rows]
placeholders = ",".join("?" * len(ids))
sql = f"UPDATE announcements SET llm_status='pending' WHERE id IN ({placeholders})"
conn.execute(sql, ids)
conn.commit()

pending = conn.execute(f"SELECT COUNT(*) FROM announcements WHERE id IN ({placeholders}) AND llm_status='pending'", ids).fetchone()[0]
print(f"重置为pending: {pending}/{len(ids)} 条")

print("\n样例公告:")
for r in rows[:5]:
    title = r["announcement_title"][:50] if r["announcement_title"] else ""
    print(f"  ID={r['id']} | {r['company_name']} | {title} | crawl={r['crawl_status']}")

conn.close()
