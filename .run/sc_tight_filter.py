#!/usr/bin/env python3
"""Tighter filter for SC positions: focus on investment/wealth/asset/FOF/analyst/graduate."""
import json
import re

with open("/workspace/.run/sc_filtered.json", encoding="utf-8") as f:
    data = json.load(f)

# High-priority keywords - what user really wants
HIGH_PRIORITY = [
    "Coverage-Banking-Graduate", "Graduate-Programme", "IGP",
    "International-Graduate", "Wealth-Management", "Asset-Management",
    "Investment", "Portfolio", "FOF", "Fund", "Research", "Strateg",
    "Allocat", "Private-Bank", "RM", "Relationship-Manager", "Analyst",
    "Quant", "Trading", "Product-Owner", "Product-Manager", "Summer-Analyst",
    "Intern-Hong-Kong", "Wealth-&-Protection", "Wealth-Solutions",
    "Financial-Markets", "Markets", "Coverage", "CIB-RM",
]

# Exclude pure IT/ops/compliance/audit/HR
EXCLUDE = [
    "AI-Data-Engineer", "Software", "DevOps", "SRE", "Backend", "Frontend",
    "Audit", "Compliance", "Risk-Officer", "Internal-Control", "Cybersecurity",
    "Talent", "HR-", "Recruitment", "Tax", "Treasury-Ops", "Learning",
    "Procurement", "Real-Estate", "Facilities", "Finance-Ops", "Accounting",
    "Investigation", "Data-Engineer", "Data-Analyst", "MLOps", "Solution-Architect",
    "Program-Manager", "Project-Manager", "Scrum", "VP-Technology", "Engineering",
    "Information-Security", "Security", "CISO", "Network",
]

def passes(url):
    u = url.lower()
    if any(e.lower() in u for e in EXCLUDE):
        return False
    return any(h.lower() in u for h in HIGH_PRIORITY)

high_pri_china = [u for u in data["all_china_urls"] if passes(u)]
high_pri_hk = [u for u in data["all_hk_urls"] if passes(u)]

# Also graduate programs as separate category - capture for 管培专题
grad_china = [u for u in data["all_china_urls"] if "graduate" in u.lower() or "trainee" in u.lower() or "intern" in u.lower()]
grad_hk = [u for u in data["all_hk_urls"] if "graduate" in u.lower() or "trainee" in u.lower() or "intern" in u.lower()]

print(f"High-priority China: {len(high_pri_china)}")
print(f"High-priority HK: {len(high_pri_hk)}")
print(f"Graduate/Intern China: {len(grad_china)}")
print(f"Graduate/Intern HK: {len(grad_hk)}")

# Cap at 30 China + 20 HK for fetching
fetch_list = (high_pri_china + grad_china)[:30] + (high_pri_hk + grad_hk)[:20]

with open("/workspace/.run/sc_fetch_list.json", "w", encoding="utf-8") as f:
    json.dump({
        "high_pri_china": high_pri_china,
        "high_pri_hk": high_pri_hk,
        "grad_china": grad_china,
        "grad_hk": grad_hk,
        "fetch_list": fetch_list,
    }, f, ensure_ascii=False, indent=2)

print(f"\nFetch list (capped): {len(fetch_list)}")
for u in fetch_list[:20]:
    print(f"  {u}")
