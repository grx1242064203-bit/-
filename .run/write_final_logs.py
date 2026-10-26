#!/usr/bin/env python3
"""写最终的 recheck_results.json 和 archive_log.json。"""
import json

# 读取初步复查结果
with open("/workspace/.run/recheck_results.json", encoding="utf-8") as f:
    data = json.load(f)

# 读取严格复查结果
with open("/workspace/.run/recheck_verified.json", encoding="utf-8") as f:
    verified = json.load(f)

# 用 verify_status 更新初步结果
vmap = {v["record_id"]: v for v in verified}
final_results = []
for r in data["results"]:
    rid = r["record_id"]
    if rid in vmap:
        v = vmap[rid]
        # 严格复查后的最终状态
        if v["verify_status"] == "closed":
            final_status = "closed"
            final_reason = v["verify_reason"]
        else:
            # 原初步判 closed 但严格复查不通过 -> ambiguous
            final_status = "ambiguous"
            final_reason = f"strict_recheck_failed (initial: {r['reason']})"
        final_results.append({
            **r,
            "final_status": final_status,
            "final_reason": final_reason,
            "verify_http": v.get("verify_http"),
        })
    else:
        # 未进入严格复查的(初步非 closed)
        final_results.append({
            **r,
            "final_status": r["status"],
            "final_reason": r["reason"],
        })

final_data = {
    "pool_stats": data["pool_stats"],
    "summary": {
        "sampled": len(final_results),
        "closed": sum(1 for r in final_results if r["final_status"] == "closed"),
        "open": sum(1 for r in final_results if r["final_status"] == "open"),
        "ambiguous": sum(1 for r in final_results if r["final_status"] == "ambiguous"),
        "skip": sum(1 for r in final_results if r["final_status"] == "skip"),
    },
    "results": final_results,
}
with open("/workspace/.run/recheck_results.json", "w", encoding="utf-8") as f:
    json.dump(final_data, f, ensure_ascii=False, indent=2)

# 写 archive_log.json
archived = [
    {
        "original_record_id": "recvqcanSl6RB6",
        "closed_table_record_id": "reczz28RrHgeiHK8",
        "company": "BlackRock（贝莱德）",
        "title": "Analyst, Quantitative Researcher",
        "hash": "BlackRock量化研究员Analyst上海",
        "url": "https://www.themuse.com/jobs/blackrock/analyst-quantitative-researcher",
        "close_reason": "strict_text: no longer available (page: 'This job is no longer available.')",
        "close_date": "2026-10-26 09:30:00",
        "main_table_deleted": True,
        "archived_at": "2026-10-26 09:30:00",
    },
    {
        "original_record_id": "recvqfODkBorUx",
        "closed_table_record_id": "reczz28RrHgegERF",
        "company": "国泰海通证券",
        "title": "2026管培生(上海分公司)",
        "hash": "国泰海通证券2026管培生上海分公司上海",
        "url": "https://career.shiep.edu.cn/campus/view/id/667247",
        "close_reason": "strict_text: expired (page: '过期时间：2026-06-28', today 2026-10-26 already past)",
        "close_date": "2026-10-26 09:30:00",
        "main_table_deleted": True,
        "archived_at": "2026-10-26 09:30:00",
    },
]
with open("/workspace/.run/archive_log.json", "w", encoding="utf-8") as f:
    json.dump(archived, f, ensure_ascii=False, indent=2)

print("=== Final Summary ===")
print(json.dumps(final_data["summary"], ensure_ascii=False, indent=2))
print(f"\nArchived: {len(archived)}")
for a in archived:
    print(f"  {a['original_record_id']} -> {a['closed_table_record_id']} | {a['company']}")
