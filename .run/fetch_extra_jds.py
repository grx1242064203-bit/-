#!/usr/bin/env python3
"""Fetch JD text for domestic L1 positions + foreign graduate programs in parallel."""
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape

# Top domestic L1 URLs + foreign grad URLs
DOMESTIC_URLS = [
    ("中金公司-FOF投资经理-J19153", "https://cicc.zhiye.com/custom/socialxq?jobAdId=807f99ac-3faa-4580-a266-ad30403128cc"),
    ("中金公司-FOF研究员-J19758", "https://www.liepin.com/job/1985789235.shtml"),
    ("申万宏源证券-FOF研究及投资岗", "https://vita.51jrq.com/vita/jobinfo/1284577"),
    ("招商证券-投资岗FOF方向", "https://m.qcc.com/jobdetail/8341663d4e02c6b6d95d2709fb1815b6.html"),
    ("招商证券-投资岗公募FOF", "http://www.szbarc.com/job2813798833.shtml"),
    ("中信建投期货-FOF投资经理-J10404", "http://www.shbsrc.com/job785696003.shtml"),
    ("中信建投证券-资管投资经理", "https://m.liepin.com/company-jobs/8029798/jc-N10/"),
    ("国泰海通证券-资产配置专员", "https://m.liepin.com/company-jobs/8376413/jc-N10/"),
    ("华泰证券-多资产投资岗", "https://www.hotjob.cn/wt/HTSC/mobweb/v8/position/subscriptionPositionList"),
    ("华泰柏瑞-FOF研究员", "https://finance.sina.com.cn/wm/2026-06-22/doc-iniekzkr8720725.shtml"),
    ("九坤投资-量化策略研究员", "https://www.ubiquant.com/website/career"),
    ("明汯投资-量化策略研究员", "https://m.bosszhipin.com/zhaopin/b0fc8b50352290ff1HRy3Ni8/"),
    ("广发基金-指数产品研究岗", "https://gffunds.jobs.feishu.cn/833056"),
    ("国泰海通证券-管培生", "https://scc.pku.edu.cn/frontpage/pku/html/recruitmentinfoForm.html"),
    ("华泰证券-Kingsman星训营2027", "http://job.htsc.com.cn/index.html?organize=2&jobtype=2"),
]

# Foreign grad programs - top priority
FOREIGN_URLS = [
    ("Goldman Sachs-AWM-New-Analyst", "https://higher.gs.com/roles/171418"),
    ("Goldman Sachs-FICC-New-Analyst", "https://higher.gs.com/roles/150685"),
    ("Goldman Sachs-PE-Investing-Analyst", "https://higher.gs.com/roles/174590"),
    ("JPMorgan-Global-Private-Bank-Analyst", "https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/job/210795"),
    ("JPMorgan-Quant-Early-Mentorship", "https://careers.jpmorgan.com/us/en/students/programs/quant-fin-programs"),
    ("Morgan Stanley-IB-Summer-Analyst", "https://uat.morganstanley.com/careers/career-opportunities-search?businessarea=i"),
    ("Morgan Stanley-Early-Careers", "https://uat.morganstanley.com/people-opportunities/students-graduates"),
    ("HSBC-IB-Graduate-Programme", "https://apply.careers.hsbc.com/emergingtalent/job/Central-Investment-Banking-Graduate-Programme-Hong-Kong/665677"),
    ("HSBC-Investment-Analyst-Asset-Mgmt", "https://apply.careers.hsbc.com/job/Central-Investment-Analyst-HSBC-Global-Asset-Management/665578"),
    ("UBS-Graduate-Talent-Program", "https://jobs.ubs.com/TGnewUI/Search/home/HomeWithPreLoad?partnerid=25008&siteid=5012"),
    ("BlackRock-Full-Time-Analyst-APAC", "https://careers.blackrock.com/en/job/sydney/2027-full-time-analyst-program-apac/6946-14188"),
    ("Citi-Wealth-Citigold-Summer-Analyst", "https://jobs.citi.com/job/hong-kong/wealth-citigold-summer-analyst-hong-kong-2027/3/1/"),
    ("Deutsche-Bank-Graduate-FICC", "https://app.joinhandshake.com/jobs/11465169/share_preview"),
    ("BNP-Paribas-APAC-Graduate", "https://www.bnpparibas.com.hk/en/careers/early-careers/"),
    ("Barclays-IB-Graduate-Expert", "https://search.jobs.barclays/en/graduates-investment-banking"),
    ("Nomura-Graduate-Programs", "https://www.nomura.com/careers/early-careers/graduate-programs/"),
    ("Fidelity-Multi-Asset-Graduate", "https://careers.fidelityinternational.com/early-careers-overview/graduates-and-placement/"),
    ("PIMCO-Full-Time-Opportunities", "https://www.pimco.com/hk/zh/about-us/careers/students/full-time-opportunities"),
]

def strip_html(text):
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.I)
    text = re.sub(r"<nav[^>]*>.*?</nav>", "", text, flags=re.DOTALL | re.I)
    text = re.sub(r"<header[^>]*>.*?</header>", "", text, flags=re.DOTALL | re.I)
    text = re.sub(r"<footer[^>]*>.*?</footer>", "", text, flags=re.DOTALL | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"</li>", "\n", text, flags=re.I)
    text = re.sub(r"</div>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()

def fetch_one(label, url):
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", "20", "-A",
             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"],
            capture_output=True, text=True, timeout=25
        )
        # Actually use url as the curl arg
        result = subprocess.run(
            ["curl", "-sL", "--max-time", "20", "-A",
             "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
             url],
            capture_output=True, text=True, timeout=25
        )
        html = result.stdout
        if not html or len(html) < 500:
            return {"label": label, "url": url, "error": "empty", "jd_text": ""}
        
        # Title
        title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        title = title_m.group(1).strip() if title_m else ""
        
        # Meta description
        meta_m = re.search(r'<meta[^>]+(?:name|property)="(?:description|og:description)"[^>]+content="([^"]+)"', html, re.I)
        meta_desc = meta_m.group(1) if meta_m else ""
        
        # Posted date patterns
        posted_date = ""
        for pattern in [r"Posted\s*(?:on|:)\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
                        r"发布(?:于|时间|日期)[:\s]*([0-9]{4}-[0-9]{2}-[0-9]{2})",
                        r'"datePosted"\s*:\s*"([^"]+)"',
                        r"Posted\s*(\d+)\s*days?\s*ago",
                        r"发布于\s*(\d+)\s*天前"]:
            m = re.search(pattern, html, re.I)
            if m:
                posted_date = m.group(1) if "ago" not in pattern and "前" not in pattern else m.group(0)
                break
        
        # Find body and strip
        body_m = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.I)
        body = body_m.group(1) if body_m else html
        text = strip_html(body)
        
        # Truncate and find JD-relevant section
        if len(text) > 6000:
            # Try to find a JD-relevant section
            for marker in ["Responsibilities", "职责", "Key Responsibilities", "Job Description", "Position Summary", "About the Role", "任职资格", "任职要求", "Qualifications", "What You'll", "What You Will", "Program Overview", "Programme Overview"]:
                idx = text.find(marker)
                if idx > 0:
                    text = text[max(0, idx-200):idx+5000]
                    break
            text = text[:6000]
        
        return {
            "label": label,
            "url": url,
            "title": title,
            "meta_desc": meta_desc,
            "jd_text": text,
            "posted_date": posted_date,
            "fetch_success": True,
        }
    except Exception as e:
        return {"label": label, "url": url, "error": str(e), "jd_text": "", "fetch_success": False}

all_urls = [("DOMESTIC", x[0], x[1]) for x in DOMESTIC_URLS] + [("FOREIGN", x[0], x[1]) for x in FOREIGN_URLS]
print(f"Fetching {len(all_urls)} JD pages in parallel...")

results = []
with ThreadPoolExecutor(max_workers=8) as executor:
    futures = {executor.submit(fetch_one, label, url): (cat, label, url) for cat, label, url in all_urls}
    for future in as_completed(futures):
        r = future.result()
        results.append(r)
        cat = "DOMESTIC" if r["label"] in [x[0] for x in DOMESTIC_URLS] else "FOREIGN"
        text_len = len(r.get("jd_text", ""))
        status = "OK" if r.get("fetch_success") and text_len > 200 else "THIN" if r.get("fetch_success") else "FAIL"
        print(f"  [{cat[:3]}-{status}] {r.get('label', '')[:50]:<50} | text={text_len}")

# Save
with open("/workspace/.run/extra_jds.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\nTotal: {len(results)}")
print(f"Success with text > 200: {sum(1 for r in results if r.get('fetch_success') and len(r.get('jd_text', '')) > 200)}")
print(f"Saved to /workspace/.run/extra_jds.json")
