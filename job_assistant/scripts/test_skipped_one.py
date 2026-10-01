"""测试单条 skipped 公告的重处理效果。"""
import sys
sys.path.insert(0, "/opt/job_assistant")

from llm_enricher import PositionEnricher
import job_db

# 取1条 skipped 公告测试
anns = job_db.get_announcements_for_llm(limit=1, status="skipped")
if not anns:
    print("没有 skipped 公告")
    sys.exit(0)

ann = anns[0]
title = ann.get("announcement_title", "")
content = ann.get("content") or ""
print(f"测试公告 id={ann['id']}")
print(f"公司={ann['company_name']}")
print(f"标题={title[:80]}")
print(f"content 长度={len(content)}")

# 清理旧岗位
deleted = job_db.delete_positions_by_announcement(ann["id"])
print(f"清理旧岗位数={deleted}")

e = PositionEnricher()
count = e.enrich_announcement(ann)
print(f"拆出岗位数={count}")

# 查看结果
conn = job_db._get_conn()
positions = conn.execute(
    "SELECT position_title, job_category, job_subcategory, city, min_education, major_required "
    "FROM positions WHERE announcement_id=?",
    (ann["id"],),
).fetchall()
conn.close()

for p in positions:
    print(f"  - {p[0]} | 大类={p[1]} | 子类={p[2]} | 城市={p[3]} | 学历={p[4]} | 专业={p[5]}")
