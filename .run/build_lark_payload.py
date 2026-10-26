#!/usr/bin/env python3
"""Build lark-cli batch-create payload from final_records, filter duplicates."""
import json
import re

with open("/workspace/.run/final_records_to_insert.json", encoding="utf-8") as f:
    records = json.load(f)

with open("/workspace/.run/existing_hashes.json", encoding="utf-8") as f:
    existing = json.load(f)

main_hashes = set(existing["main_hashes"])
closed_hashes = set(existing["closed_hashes"])

today = "2026-10-26 09:10:00"

# Map category - the L0-管培 doesn't exist as option, so map to L3-其他前台
def map_category(cat):
    if cat == "L0-管培":
        return "L3-其他前台"
    return cat

# Build create_records payload, filtering out duplicates
create_records = []
skipped = 0
for r in records:
    h = r["dedup_hash"].lower()
    if h in main_hashes or h in closed_hashes:
        skipped += 1
        continue
    # Convert grad_window bool to 是/否
    grad_window_str = "是" if r["grad_window"] else "否"
    # Build JD link as markdown
    jd_link = f"[查看JD]({r['jd_link_url']})"
    # Build create_record object
    record = {
        "岗位标题": r["title"],
        "公司": r["company"],
        "部门": r["department"],
        "地点": r["location"],
        "薪资范围": r["salary_range"],
        "经验要求": r["experience"],
        "学历要求": r["education"],
        "JD摘要": r["jd_summary"],
        "JD链接": jd_link,
        "抓取日期": today,
        "发布时间": r["posted_date"],
        "岗位类别": [map_category(r["category"])],
        "平台层级": [r["platform_tier"]],
        "相关性评分": r["relevance_score"],
        "难度评分": r["difficulty_score"],
        "综合推荐度": [r["recommendation"]],
        "简评": r["comment"],
        "申请建议": r["advice"],
        "申请状态": ["未投递"],
        "去重hash": r["dedup_hash"],
        "应届窗口": [grad_window_str],
        "是否在招": ["是"],
    }
    create_records.append(record)

print(f"Records to create (after dedup): {len(create_records)}")
print(f"Skipped (already in DB): {skipped}")

# Save payload
payload = {"create_records": create_records}
with open("/workspace/.run/lark_create_payload.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

print(f"Payload saved to /workspace/.run/lark_create_payload.json")
print(f"Total field count per record: {len(create_records[0]) if create_records else 0}")
