import sqlite3
conn = sqlite3.connect("data/jobs.db")
cur = conn.cursor()

# 1. positions 表所有字段及填充率
print("=== positions 表全部字段填充率 ===")
cols = [r[1] for r in cur.execute("PRAGMA table_info(positions)").fetchall()]
total = cur.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
print("总记录数:", total)
print()
print("%-22s %8s %8s  %s" % ("字段", "非空数", "填充率", "样例"))
print("-" * 80)
for f in cols:
    q = "SELECT COUNT(*) FROM positions WHERE length(" + f + ") > 0"
    cnt = cur.execute(q).fetchone()[0]
    # 取一个非空样例
    sq = "SELECT " + f + " FROM positions WHERE length(" + f + ") > 0 LIMIT 1"
    sample = cur.execute(sq).fetchone()
    sample_str = str(sample[0])[:40] if sample and sample[0] else ""
    print("%-22s %8d %7.0f%%  %s" % (f, cnt, 100*cnt/total, sample_str))

# 2. announcements 源表能提供的字段
print()
print("=== announcements 源表字段(可映射到 positions) ===")
ann_cols = [r[1] for r in cur.execute("PRAGMA table_info(announcements)").fetchall()]
print(", ".join(ann_cols))

conn.close()
