#!/usr/bin/env python3
"""Merge JD texts from SC + extra fetches, enrich candidate records."""
import json
import re

# Load all sources
with open("/workspace/.run/final_candidates.json", encoding="utf-8") as f:
    candidates = json.load(f)

with open("/workspace/.run/extra_jds.json", encoding="utf-8") as f:
    extra = json.load(f)

# Build URL -> extra_jd map
extra_map = {r["url"]: r for r in extra if r.get("fetch_success")}
# Also build label->text map for fallback matching
label_map = {r.get("label", ""): r for r in extra}

# Map by URL
for c in candidates:
    url = c.get("url", "")
    # Try direct URL match
    if url in extra_map:
        r = extra_map[url]
        if r.get("jd_text") and len(r["jd_text"]) > 100:
            c["jd_text"] = r["jd_text"]
            if r.get("posted_date"):
                c["posted_date"] = r["posted_date"]
            if r.get("title"):
                c["page_title"] = r["title"]
            if r.get("meta_desc"):
                c["meta_desc"] = r["meta_desc"]

print(f"After merge - text stats:")
for c in candidates:
    text_len = len(c.get("jd_text", ""))
    print(f"  [{text_len:5d}] [{c['company'][:15]:<15}] {c['title'][:50]:<50}")

# Save enriched
with open("/workspace/.run/final_candidates_enriched.json", "w", encoding="utf-8") as f:
    json.dump(candidates, f, ensure_ascii=False, indent=2)

print(f"\nSaved to /workspace/.run/final_candidates_enriched.json")
