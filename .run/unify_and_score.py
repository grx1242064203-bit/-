#!/usr/bin/env python3
"""Unify all candidate sources and apply pre-scoring to pick top N for deep analysis."""
import json
import re
from html import unescape

# Load all sources
with open("/workspace/.run/sc_jds.json", encoding="utf-8") as f:
    sc_jds = json.load(f)
with open("/workspace/.run/foreign_other_candidates.json", encoding="utf-8") as f:
    foreign = json.load(f)
with open("/workspace/.run/domestic_candidates.json", encoding="utf-8") as f:
    domestic = json.load(f)

# Load existing hashes for dedup
with open("/workspace/.run/existing_hashes.json", encoding="utf-8") as f:
    existing = json.load(f)

main_hashes = set(existing["main_hashes"])
closed_hashes = set(existing["closed_hashes"])

# Build candidate list
candidates = []

# Standard Chartered
for r in sc_jds:
    if not r.get("fetch_success") or r.get("is_closed"):
        continue
    title = r.get("title", "").replace(" Job Details | Standard Chartered Bank", "").replace(" Job Detail", "").replace("&amp;", "&").strip()
    # Sometimes title is "Coverage Banking Graduate Programme Shanghai 2027" - keep as is
    loc = r.get("location", "").replace("-", " ").strip()
    candidates.append({
        "company": "渣打银行",
        "source_site": "jobs.standardchartered.com",
        "title": title,
        "url": r.get("url"),
        "location": loc,
        "is_graduate_program": "graduate" in title.lower() or "intern" in title.lower(),
        "graduate_program_name": "Coverage Banking Graduate Programme" if "Coverage Banking Graduate" in title else ("Coverage Banking Intern" if "Intern" in title else ""),
        "jd_text": r.get("jd_text", ""),
        "meta_desc": r.get("meta_desc", ""),
        "posted_date": r.get("posted_date", ""),
        "relative_date": r.get("relative_date", ""),
        "raw_url": r.get("url"),
        "source": "sc_sitemap",
    })

# Foreign
for r in foreign:
    jd = r.get("title_summary", "") or ""
    candidates.append({
        "company": r.get("company", ""),
        "source_site": r.get("source_site", ""),
        "title": r.get("title", ""),
        "url": r.get("url", ""),
        "location": r.get("location", ""),
        "is_graduate_program": r.get("is_graduate_program", False),
        "graduate_program_name": r.get("graduate_program_name", ""),
        "jd_text": jd,
        "meta_desc": "",
        "posted_date": "",
        "relative_date": "",
        "raw_url": r.get("url", ""),
        "source": "foreign_other",
    })

# Domestic
for r in domestic:
    jd = r.get("title_summary", "") or ""
    candidates.append({
        "company": r.get("company", ""),
        "source_site": r.get("source_site", ""),
        "title": r.get("title", ""),
        "url": r.get("url", ""),
        "location": r.get("location", ""),
        "is_graduate_program": r.get("is_graduate_program", False),
        "graduate_program_name": r.get("graduate_program_name", ""),
        "jd_text": jd,
        "meta_desc": "",
        "posted_date": "",
        "relative_date": "",
        "raw_url": r.get("url", ""),
        "source": "domestic",
    })

print(f"Total candidates pre-dedup: {len(candidates)}")

# Generate dedup hash and check against existing
def make_hash(company, title, location):
    s = f"{company}{title}{location}"
    return re.sub(r"\s+", "", s).strip().lower()

# Pre-score based on title + JD text keywords
def prescore(c):
    title = c["title"]
    jd = c["jd_text"]
    text = (title + " " + jd).lower()
    is_grad = c["is_graduate_program"]
    company = c["company"]
    
    # Category - L1 / L2 / L3 / L0-grad
    if is_grad:
        cat = "L0-管培"  # 外资管培
        cat_score = 15  # placeholder for L0 (between L1 and L2)
    elif any(k in text for k in ["fof", "私募研究", "私募基金", "fund of funds", "self trade", "自营投资", "自营交易"]):
        cat = "L1-私募研究FOF自营"
        cat_score = 40
    elif any(k in text for k in ["asset allocat", "资产配置", "宏观策略", "macro strateg", "index", "指数", "smart beta", "大类资产"]):
        cat = "L2-大类资产配置"
        cat_score = 25
    elif any(k in text for k in ["investment strategist", "investment advisor", "投资策略", "投资顾问", "wealth", "财富管理", "private bank", "私人银行", "markets", "coverage", "ib ", "investment banking", "投行", "销售", "relationship manager"]):
        cat = "L3-其他前台"
        cat_score = 10
    else:
        cat = "L3-其他前台"
        cat_score = 10
    
    # Platform match - foreign big bank = 20, top domestic = 20, others = 10
    foreign_big = ["Goldman Sachs", "JPMorgan", "Morgan Stanley", "HSBC", "渣打银行", "Standard Chartered",
                   "UBS", "BlackRock", "Citi", "Deutsche Bank", "BNP Paribas", "Barclays", "Nomura",
                   "Fidelity", "Vanguard", "PIMCO"]
    top_domestic = ["中金公司", "中信证券", "中信建投", "华泰证券", "国泰海通证券", "申万宏源证券",
                    "招商证券", "广发证券", "中国银河", "海通证券", "中金", "易方达", "华夏基金",
                    "南方基金", "博时基金", "汇添富", "嘉实", "景林", "高毅", "幻方", "明汯", "九坤"]
    
    if company in foreign_big:
        platform = "外资头部"
        plat_score = 20
    elif company in top_domestic or any(t in company for t in top_domestic):
        platform = "头部券商基金"
        plat_score = 20
    else:
        platform = "其他"
        plat_score = 10
    
    # Experience match - 1-3 years = 15, grad program = 15
    if is_grad:
        exp_score = 15
    else:
        # Check JD text for years requirement
        years_m = re.search(r"(\d+)\s*[-至到]\s*(\d+)\s*年|(\d+)\+?\s*年", text)
        if years_m:
            nums = [int(x) for x in years_m.groups() if x]
            if nums and min(nums) <= 3:
                exp_score = 15
            elif nums and min(nums) >= 5:
                exp_score = 5
            else:
                exp_score = 10
        else:
            exp_score = 12  # default assume moderate
    
    # Skills match (based on JD keywords)
    skills = 0
    if any(k in text for k in ["fof", "fund of funds", "组合管理", "组合构建", "私募基金", "尽调", "尽职调查"]):
        skills += 5
    if any(k in text for k in ["量化", "cta", "套利", "quant", "hedge", "对冲"]):
        skills += 3
    if any(k in text for k in ["资产配置", "asset allocat", "宏观", "macro"]):
        skills += 3
    if any(k in text for k in ["ai", "数据", "机器学习", "python", "system", "系统"]):
        skills += 2
    if any(k in text for k in ["海外", "跨境", "global", "international"]):
        skills += 2
    skills = min(skills, 15)
    
    # Education - master 985 (assume yes) = 10
    edu_score = 10  # user has 985 + master
    
    total = cat_score + plat_score + exp_score + skills + edu_score
    return {
        "category": cat,
        "platform": platform,
        "cat_score": cat_score,
        "plat_score": plat_score,
        "exp_score": exp_score,
        "skills_score": skills,
        "edu_score": edu_score,
        "total_score": total,
    }

# Apply scoring and dedup
final = []
skipped_dup = 0
for c in candidates:
    h = make_hash(c["company"], c["title"], c["location"])
    if h in main_hashes or h in closed_hashes:
        skipped_dup += 1
        continue
    s = prescore(c)
    c["dedup_hash"] = h
    c.update(s)
    final.append(c)

print(f"After dedup: {len(final)} (skipped {skipped_dup} duplicates)")

# Sort by score desc
final.sort(key=lambda x: -x["total_score"])

# Top 30
print("\n=== TOP 30 (prescored) ===")
for i, c in enumerate(final[:30]):
    grad = "[GRAD]" if c["is_graduate_program"] else ""
    print(f"{i+1:2d}. [{c['total_score']:3d}] {grad:7s} [{c['company'][:15]:<15}] {c['title'][:50]:<50} | {c['location'][:15]:<15} | cat={c['category']}")

# Save final
with open("/workspace/.run/final_candidates.json", "w", encoding="utf-8") as f:
    json.dump(final[:30], f, ensure_ascii=False, indent=2)

print(f"\nTop 30 saved to /workspace/.run/final_candidates.json")
