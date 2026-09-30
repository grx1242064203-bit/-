import sqlite3
conn = sqlite3.connect("data/jobs.db")
cur = conn.cursor()
total = cur.execute("SELECT COUNT(*) FROM announcements").fetchone()[0]
print("=== 源表字段非空率 ===")
fields = ["company_name","announcement_title","recruit_type","recruit_target",
          "min_grade","max_grade","industry_raw","company_type_raw",
          "location","education_req","apply_url","announcement_url",
          "deadline","publish_time"]
for f in fields:
    q = "SELECT COUNT(*) FROM announcements WHERE " + f + " IS NOT NULL AND length(" + f + ") > 0"
    cnt = cur.execute(q).fetchone()[0]
    print("  %-20s: %5d/%d (%.0f%%)" % (f, cnt, total, 100*cnt/total))
print()
print("=== 标题长度分布 ===")
lens = sorted([r[0] for r in cur.execute("SELECT length(announcement_title) FROM announcements WHERE announcement_title IS NOT NULL").fetchall()])
print("  最短:%d 最长:%d 中位:%d" % (min(lens), max(lens), lens[len(lens)//2]))
short = sum(1 for l in lens if l < 15)
mid = sum(1 for l in lens if 15 <= l < 30)
long_ = sum(1 for l in lens if l >= 30)
print("  <15字: %d (%.0f%%)" % (short, 100*short/total))
print("  15-30字: %d (%.0f%%)" % (mid, 100*mid/total))
print("  >=30字: %d (%.0f%%)" % (long_, 100*long_/total))
print()
print("=== 标题是否含具体岗位名 ===")
keywords = ["工程师","经理","专员","分析师","运营","产品","研发","测试","开发","设计","管培","培训生","销售","市场","财务","法务","人力","教师","医生","算法","数据","前端","后端","Java","Python","咨询","审计"]
titles = [r[0] for r in cur.execute("SELECT announcement_title FROM announcements").fetchall() if r[0]]
has_kw = sum(1 for t in titles if any(k in t for k in keywords))
print("  含岗位关键词: %d/%d (%.0f%%)" % (has_kw, len(titles), 100*has_kw/len(titles)))
print()
print("=== 标题样例(成功 vs 失败) ===")
print("--- 成功抓取 ---")
for r in cur.execute("SELECT announcement_title FROM announcements WHERE crawl_status='success' LIMIT 5"):
    print("  " + r[0][:70])
print("--- 失败抓取 ---")
for r in cur.execute("SELECT announcement_title FROM announcements WHERE crawl_status='failed' LIMIT 5"):
    print("  " + r[0][:70])
conn.close()
