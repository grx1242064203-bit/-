#!/usr/bin/env python3
"""Analyze existing main and closed records to build dedup hash sets and rev check candidates."""
import json
import re
from urllib.parse import urlparse

def normalize_hash(h):
    if not h:
        return ""
    return re.sub(r"\s+", "", str(h)).strip().lower()

main_hashes = set()
main_records = []
with open("/workspace/.run/main_records.ndjson", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        h = normalize_hash(r.get("去重hash"))
        if h:
            main_hashes.add(h)
        main_records.append(r)

closed_hashes = set()
closed_records = []
with open("/workspace/.run/closed_records.ndjson", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        h = normalize_hash(r.get("去重hash"))
        if h:
            closed_hashes.add(h)
        closed_records.append(r)

# Find duplicate hashes inside main (records that should be unique but aren't)
from collections import Counter
hash_counter = Counter()
for r in main_records:
    h = normalize_hash(r.get("去重hash"))
    if h:
        hash_counter[h] += 1
duplicates = {h: c for h, c in hash_counter.items() if c > 1}

# Stats on 是否在招
zai_zhao = {"yes": 0, "no": 0, "empty": 0}
for r in main_records:
    val = r.get("是否在招") or []
    if not val:
        zai_zhao["empty"] += 1
    elif "是" in val:
        zai_zhao["yes"] += 1
    elif "否" in val:
        zai_zhao["no"] += 1

# Records with non-empty JD link (for status check) - only those marked "是" or empty (assume open)
recheck_candidates = []
for r in main_records:
    val = r.get("是否在招") or []
    link = r.get("JD链接") or ""
    # extract URL from markdown link
    urls = re.findall(r"https?://[^\s)]+", link)
    is_open = (not val) or ("是" in val)
    if is_open and urls:
        recheck_candidates.append({
            "record_id": r.get("record_id"),
            "hash": r.get("去重hash"),
            "title": r.get("岗位标题"),
            "company": r.get("公司"),
            "url": urls[0],
        })

print(json.dumps({
    "main_records_count": len(main_records),
    "main_unique_hashes": len(main_hashes),
    "closed_records_count": len(closed_records),
    "closed_unique_hashes": len(closed_hashes),
    "duplicates_in_main": len(duplicates),
    "zai_zhao_stats": zai_zhao,
    "recheck_candidates_count": len(recheck_candidates),
}, ensure_ascii=False, indent=2))

# Save consolidated hash list
with open("/workspace/.run/existing_hashes.json", "w", encoding="utf-8") as f:
    json.dump({
        "main_hashes": sorted(main_hashes),
        "closed_hashes": sorted(closed_hashes),
    }, f, ensure_ascii=False, indent=2)

# Save recheck candidates (split into batches of 20 for sampling - we'll randomly sample)
with open("/workspace/.run/recheck_candidates.json", "w", encoding="utf-8") as f:
    json.dump(recheck_candidates, f, ensure_ascii=False, indent=2)

print(f"\nRecheck candidates saved: {len(recheck_candidates)}")
print(f"Existing hashes saved: main={len(main_hashes)}, closed={len(closed_hashes)}")
