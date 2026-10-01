"""调试单条 skipped 公告:打印内容、LLM调用、校验过程。"""
import sys
sys.path.insert(0, "/opt/job_assistant")

import logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

from llm_enricher import PositionEnricher, _is_category_title, _is_garbage_content
import job_db

# 石药集团
ann = job_db.get_announcement_by_id(6127)
title = ann["announcement_title"]
content = ann.get("content") or ""
print(f"标题: {title}")
print(f"DB content 长度: {len(content)}")
print(f"_is_category_title: {_is_category_title(title)}")
print(f"_is_garbage_content: {_is_garbage_content(content)}")

# 清理旧岗位
job_db.delete_positions_by_announcement(ann["id"])

e = PositionEnricher()
count = e.enrich_announcement(ann)
print(f"\n拆出岗位数: {count}")

conn = job_db._get_conn()
positions = conn.execute(
    "SELECT position_title FROM positions WHERE announcement_id=?",
    (ann["id"],),
).fetchall()
conn.close()
for p in positions:
    print(f"  - {p[0]}")
