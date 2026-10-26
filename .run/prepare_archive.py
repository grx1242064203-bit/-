#!/usr/bin/env python3
"""检查 closed_hashes_now.ndjson,确认 2 条 closed 候选是否已归档,并准备归档 payload。"""
import json

# 已归档的 hash 集合
archived_hashes = set()
try:
    with open("/workspace/.run/closed_hashes_now.ndjson", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                h = rec.get("去重hash")
                if h:
                    archived_hashes.add(h)
            except Exception:
                pass
except FileNotFoundError:
    pass
print(f"Archived hashes count: {len(archived_hashes)}")

# 2 条要归档的候选
to_archive = [
    {
        "record_id": "recvqcanSl6RB6",
        "hash": "BlackRock量化研究员Analyst上海",
        "company": "BlackRock（贝莱德）",
        "title": "Analyst, Quantitative Researcher",
    },
    {
        "record_id": "recvqfODkBorUx",
        "hash": "国泰海通证券2026管培生上海分公司上海",
        "company": "国泰海通证券",
        "title": "2026管培生(上海分公司)",
    },
]

for c in to_archive:
    already = c["hash"] in archived_hashes
    print(f"{c['record_id']} | {c['hash']} | already_archived={already}")
