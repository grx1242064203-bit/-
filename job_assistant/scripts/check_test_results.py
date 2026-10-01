#!/usr/bin/env python3
"""检查skipped公告重新拆岗的结果。"""
import sqlite3

conn = sqlite3.connect("data/jobs.db")
conn.row_factory = sqlite3.Row

# 查看最近处理的20条(用llm_time倒序)
rows = conn.execute("""
    SELECT id, company_name, announcement_title, llm_status, positions_count,
           length(content) as content_len,
           CASE WHEN content = announcement_title THEN 'title_only' ELSE 'has_content' END as content_type
    FROM announcements
    WHERE llm_status IN ('success', 'skipped')
    ORDER BY llm_time DESC LIMIT 20
""").fetchall()

success_count = sum(1 for r in rows if r["llm_status"] == "success")
print(f"最近20条: success={success_count}, skipped={len(rows)-success_count}")
print()

for r in rows:
    print(f"ID={r['id']} | {r['company_name'][:15]} | status={r['llm_status']} | pos={r['positions_count']} | content_len={r['content_len']} | type={r['content_type']}")
    print(f"    标题: {r['announcement_title'][:60]}")
    if r["llm_status"] == "success":
        positions = conn.execute(
            "SELECT position_title, jd_summary, hard_skills, job_category FROM positions WHERE announcement_id=?",
            (r["id"],)
        ).fetchall()
        for p in positions[:5]:
            print(f"    -> {p['position_title'][:30]} | {p['job_category']} | JD: {str(p['jd_summary'])[:40]}")

conn.close()
