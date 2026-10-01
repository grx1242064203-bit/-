"""小批量重处理 skipped 公告并输出详细结果。"""
import sys
sys.path.insert(0, "/opt/job_assistant")

from llm_enricher import run_skipped_reprocess
import job_db

LIMIT = 20

print(f"=== 开始重处理 {LIMIT} 条 skipped 公告 ===")
result = run_skipped_reprocess(limit=LIMIT, max_workers=3)
print(f"结果: {result}")

# 输出每条公告的岗位
print("\n=== 重处理后岗位详情 ===")
conn = job_db._get_conn()
anns = conn.execute(
    "SELECT id, company_name, announcement_title, llm_status, positions_count "
    "FROM announcements WHERE llm_status IN ('success','skipped','failed') "
    "ORDER BY id DESC LIMIT ?",
    (LIMIT,),
).fetchall()
for a in anns:
    positions = conn.execute(
        "SELECT position_title FROM positions WHERE announcement_id=?",
        (a[0],),
    ).fetchall()
    pos_titles = ", ".join(p[0] for p in positions) if positions else "(无岗位)"
    print(f"[{a[3]}] {a[1]} | {a[2][:50]} → {pos_titles}")
conn.close()
