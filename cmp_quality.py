import sqlite3
conn = sqlite3.connect("data/jobs.db")
cur = conn.cursor()

print("=== 岗位字段填充率对比(成功抓取 vs 失败抓取) ===")
print("%-20s %12s %12s %8s" % ("字段", "成功抓取", "失败抓取", "差异"))
print("-" * 60)

pos_fields = ["position_title","department","job_category","job_subcategory",
              "hard_skills","soft_skills","major_required","major_category",
              "min_education","city","responsibilities","requirements",
              "keywords","jd_summary","company_tier","difficulty"]

total1 = cur.execute("SELECT COUNT(*) FROM positions p JOIN announcements a ON p.announcement_id=a.id WHERE a.crawl_status=?", ("success",)).fetchone()[0]
total2 = cur.execute("SELECT COUNT(*) FROM positions p JOIN announcements a ON p.announcement_id=a.id WHERE a.crawl_status=?", ("failed",)).fetchone()[0]

for f in pos_fields:
    q1 = "SELECT COUNT(*) FROM positions p JOIN announcements a ON p.announcement_id=a.id WHERE a.crawl_status=? AND length(p." + f + ") > 0"
    q2 = "SELECT COUNT(*) FROM positions p JOIN announcements a ON p.announcement_id=a.id WHERE a.crawl_status=? AND length(p." + f + ") > 0"
    cnt1 = cur.execute(q1, ("success",)).fetchone()[0]
    cnt2 = cur.execute(q2, ("failed",)).fetchone()[0]
    p1 = 100*cnt1/total1 if total1 else 0
    p2 = 100*cnt2/total2 if total2 else 0
    print("%-20s %5d/%-5d %5d/%-5d %+.0f%%" % (f, cnt1, total1, cnt2, total2, p2-p1))

print()
print("=== 每条公告平均拆岗数 ===")
q = "SELECT a.crawl_status, AVG(a.positions_count) FROM announcements a WHERE a.llm_status='success' GROUP BY a.crawl_status"
for r in cur.execute(q).fetchall():
    print("  %s: %.1f 岗位/公告" % (r[0], r[1]))

print()
print("=== 标题样例 + 拆出的岗位(失败抓取,多岗位公告) ===")
q = "SELECT a.id, a.announcement_title, p.position_title FROM announcements a JOIN positions p ON p.announcement_id=a.id WHERE a.crawl_status='failed' AND a.positions_count > 1 LIMIT 15"
rows = cur.execute(q).fetchall()
prev_id = None
for r in rows:
    if r[0] != prev_id:
        print("\n  公告#%d: %s" % (r[0], r[1][:70]))
        prev_id = r[0]
    print("    - %s" % r[2])

conn.close()
