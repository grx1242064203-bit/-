#!/usr/bin/env python3
"""Parse Standard Chartered sitemap, extract China+HK positions, keyword filter."""
import re
import json
import sys

with open("/workspace/.run/sc_sitemap.xml", encoding="utf-8") as f:
    xml = f.read()

urls = re.findall(r"<loc>(https://jobs\.standardchartered\.com/job/[^<]+)</loc>", xml)
print(f"Total URLs in sitemap: {len(urls)}")

# China mainland city keywords (URL prefix patterns, before the title)
china_cities = [
    "Beijing", "Shanghai", "ShenZhen", "Shenzhen", "Guangzhou", "Tianjin",
    "Chengdu", "Hangzhou", "Nanjing", "Qingdao", "Suzhou", "Xiamen",
    "Wuhan", "Chongqing", "Dalian", "Xi-An", "Xi'An", "Hefei", "Changsha",
    "Zhengzhou", "Shenyang", "Jinan", "Kunming", "Haikou", "Ningbo", "Xi'an",
]
# HK districts
hk_cities = ["Hong-Kong", "HongKong", "Central", "Tsim-Sha-Tsui", "Kwun-Tong",
             "Causeway-Bay", "MongKok", "Kowloon", "Taikoo", "Quarry-Bay",
             "Hong Kong", "HK", "Admiralty", "Wan-Chai", "Sheung-Wan"]

china_re = re.compile(r"/job/(?:China-)?(" + "|".join(china_cities) + r")(?:[-/])", re.I)
hk_re = re.compile(r"/job/(" + "|".join(hk_cities) + r")(?:[-/])", re.I)
# Also generic China pattern
china_generic = re.compile(r"/job/China[-/]|/job/.*China", re.I)

china_urls = []
hk_urls = []
for u in urls:
    if china_re.search(u) or "China" in u.split("/job/")[1].split("-")[0] or "/job/China-" in u:
        china_urls.append(u)
    elif hk_re.search(u) or u.lower().find("hong-kong") >= 0:
        hk_urls.append(u)

print(f"China mainland URLs: {len(china_urls)}")
print(f"HK URLs: {len(hk_urls)}")

# Keyword filter on URL (title) - initial screening
KEYWORDS = [
    "investment", "wealth", "asset", "portfolio", "FOF", "fund", "research",
    "strateg", "allocat", "private-bank", "RM", "relationship-manager",
    "analyst", "quant", "trading", "product", "graduate", "IGP",
    "management-trainee", "trainee", "summer", "intern",
]
KW_RE = re.compile("|".join(KEYWORDS), re.I)

china_kw = [u for u in china_urls if KW_RE.search(u)]
hk_kw = [u for u in hk_urls if KW_RE.search(u)]

print(f"China after keyword filter: {len(china_kw)}")
print(f"HK after keyword filter: {len(hk_kw)}")

# Save for next step
out = {
    "china_count": len(china_urls),
    "hk_count": len(hk_urls),
    "china_kw_count": len(china_kw),
    "hk_kw_count": len(hk_kw),
    "china_kw_urls": china_kw[:60],
    "hk_kw_urls": hk_kw[:60],
    "all_china_urls": china_urls,
    "all_hk_urls": hk_urls,
}
with open("/workspace/.run/sc_filtered.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f"\nSample China URLs (first 10):")
for u in china_kw[:10]:
    print(f"  {u}")
print(f"\nSample HK URLs (first 10):")
for u in hk_kw[:10]:
    print(f"  {u}")
