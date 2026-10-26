#!/usr/bin/env python3
"""Build prioritized SC fetch list - top 20 most relevant for user."""
import json
import re

with open("/workspace/.run/sc_filtered.json", encoding="utf-8") as f:
    data = json.load(f)

# User priorities:
# 1. Graduate Programme (2027 = recent grad, fits 1-year window)
# 2. Investment Strategist / Investment Advisor / Wealth Manager
# 3. RM (Relationship Manager - Priority/Private Banking) - L3 front-office
# 4. Markets / Trading / Product - L2/L1
# 5. Analyst (non-IT)

PRIORITY_KEYWORDS = {
    "graduate_programme": [
        "Coverage-Banking-Graduate-Programme",
        "Graduate-Programme",
        "International-Graduate",
        "IGP",
        "Graduate-Analyst",
    ],
    "investment_finance": [
        "Investment-Strategist", "Investment-Advisor", "Investment-Manager",
        "Investment-Specialist", "Wealth-Management", "Wealth-&-Protection",
        "Wealth-Solutions", "Asset-Management", "Portfolio-Manager",
        "Portfolio-Advisor", "Private-Banker", "Private-Banking",
    ],
    "RM": [
        "Relationship-Manager", "RM%2C-CIB", "Associate-Director%2C-RM",
        "Associate-Director%2C-Relationship", "Senior-Relationship-Manager",
    ],
    "markets_trading": [
        "Markets-Products-Specialist", "Trading", "Financial-Markets",
        "Coverage-Banking", "Strategist", "Research", "Analyst",
        "Specialist%2C-CIB",
    ],
}

# Build priority buckets
buckets = {k: [] for k in PRIORITY_KEYWORDS}
all_china = data["all_china_urls"]
all_hk = data["all_hk_urls"]

for u in all_china + all_hk:
    # decode HTML entities
    url_decoded = u.replace("&amp;", "&")
    for bucket, kws in PRIORITY_KEYWORDS.items():
        if any(kw in url_decoded for kw in kws):
            buckets[bucket].append(url_decoded)
            break

# Remove duplicates within bucket, then dedup across
seen = set()
final = []
# Order: graduate_programme > investment_finance > markets_trading > RM
for bucket in ["graduate_programme", "investment_finance", "markets_trading", "RM"]:
    for u in buckets[bucket]:
        if u not in seen:
            seen.add(u)
            final.append({"url": u, "bucket": bucket})

print(f"Total priority candidates: {len(final)}")
for f in final[:25]:
    print(f"  [{f['bucket']}] {f['url']}")

with open("/workspace/.run/sc_priority_list.json", "w", encoding="utf-8") as f:
    json.dump(final[:25], f, ensure_ascii=False, indent=2)
