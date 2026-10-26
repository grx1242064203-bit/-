#!/usr/bin/env python3
"""抽样 30 条候选记录,优先第三方招聘平台 URL,并复查 JD URL 关闭状态。"""
import json
import re
import subprocess
import sys
from urllib.parse import urlparse

CAND_PATH = "/workspace/.run/recheck_candidates.json"
RESULTS_PATH = "/workspace/.run/recheck_results.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# 第三方招聘平台域名(关闭频率高,优先抽)
THIRD_PARTY_DOMAINS = [
    "liepin.com", "qcc.com", "51jrq.com", "szbarc.com",
    "jrzp.com", "zhaopin.com", "51job.com", "zhipin.com",
    "lagou.com", "hunterchina.com.cn", "huhren.com",
    "en.zhaopin.com", "m.qcc.com", "m.sohu.com", "sohu.com",
    "sina.com.cn", "cj.sina.cn",
]
# 官方招聘门户(可信度高,少抽)
OFFICIAL_DOMAINS = [
    "cicc.zhiye.com", "hotjob.cn", "morganstanley.com", "taleo.net",
    "successfactors.com", "workday.com", "icims.com", "greenhouse.io",
    "lever.co", "themuse.com", "higher.gs.com", "ocbc.com.cn",
    "jobs.ca-cib.com", "hsbc.com", "group.bnpparibas", "credit-suisse.com",
    "ubs.com", "rbs.com", "jpmorgan.com",
]

CLOSE_PATTERNS = [
    "职位已关闭", "已下线", "已关闭", "职位已下线", "该职位已",
    "position closed", "position is closed", "no longer available",
    "no longer accepting applications", "expired", "job closed",
    "job has expired", "已过期", "the position you are looking for is no longer",
    "job not found", "job does not exist", "404", "page not found",
    "页面不存在", "您访问的页面不存在", "页面已删除",
]

WAF_PATTERNS = [
    "405", "method not allowed", "您要查看的网页无法访问",
    "请输入验证码", "captcha", "安全验证", "waf",
]

def clean_url(raw_url):
    """清洗 URL,去除 Markdown 残留。"""
    if not raw_url:
        return ""
    # 取 markdown 链接中的真实 URL: [text](url) -> 提取括号里的 url
    # 但这里看到的是: https://xxx](https://xxx 这种残留
    # 取第一个 https://... 到 ]( 之间的部分,或者 ]( 后面的部分
    m = re.match(r'^https?://[^\]\s]+\]\((https?://[^\]\s]+)', raw_url)
    if m:
        return m.group(1).rstrip(')')
    # 如果有 ]( 残留,取前面的
    if '](' in raw_url:
        raw_url = raw_url.split('](')[0]
    return raw_url.rstrip(')]').strip()

def categorize(url):
    """返回 (is_third_party, is_official)。"""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return (False, False)
    for d in THIRD_PARTY_DOMAINS:
        if d in host:
            return (True, False)
    for d in OFFICIAL_DOMAINS:
        if d in host:
            return (False, True)
    return (False, False)

def sample_candidates(candidates, n=30):
    """优先第三方平台,然后官方门户,然后其他。"""
    third_party = []
    official = []
    other = []
    for c in candidates:
        url = clean_url(c.get("url", ""))
        c["clean_url"] = url
        is_tp, is_off = categorize(url)
        if is_tp:
            third_party.append(c)
        elif is_off:
            official.append(c)
        else:
            other.append(c)
    # 抽样: 20 第三方 + 5 官方 + 5 其他
    sample = third_party[:20] + official[:5] + other[:5]
    # 不足则从其他补充
    if len(sample) < n:
        used_ids = {c["record_id"] for c in sample}
        for c in third_party[20:] + official[5:] + other[5:]:
            if c["record_id"] in used_ids:
                continue
            sample.append(c)
            used_ids.add(c["record_id"])
            if len(sample) >= n:
                break
    return sample[:n], {
        "third_party_pool": len(third_party),
        "official_pool": len(official),
        "other_pool": len(other),
        "sampled_tp": sum(1 for c in sample if categorize(c["clean_url"])[0]),
        "sampled_off": sum(1 for c in sample if categorize(c["clean_url"])[1]),
        "sampled_other": sum(1 for c in sample if not any(categorize(c["clean_url"]))),
    }

def check_url(url, record_id):
    """curl 抓取 URL,判定关闭状态。返回 dict。"""
    if not url or not url.startswith("http"):
        return {"status": "skip", "reason": "invalid_url", "http_code": None}
    cmd = [
        "curl", "-sL", "--max-time", "15", "-A", UA,
        "-o", "/tmp/jd_page.html", "-w", "%{http_code}|%{url_effective}|%{content_type}",
        url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return {"status": "skip", "reason": "curl_timeout", "http_code": None}
    except Exception as e:
        return {"status": "skip", "reason": f"curl_error: {e}", "http_code": None}
    out = proc.stdout.strip() if proc.stdout else ""
    parts = out.split("|")
    http_code = parts[0] if parts else ""
    try:
        content = open("/tmp/jd_page.html", encoding="utf-8", errors="ignore").read()
    except Exception:
        content = ""
    body_lower = content.lower()[:50000]
    # HTTP 404/410
    if http_code in ("404", "410"):
        return {"status": "closed", "reason": f"http_{http_code}", "http_code": http_code,
                "final_url": parts[1] if len(parts) > 1 else ""}
    # WAF 拦截(qcc 返回 405 不算关闭)
    if http_code == "405":
        return {"status": "skip", "reason": "waf_405", "http_code": http_code}
    if http_code in ("403", "503"):
        # 可能是 WAF,检查页面
        if any(p in body_lower for p in ["captcha", "验证码", "安全验证", "waf"]):
            return {"status": "skip", "reason": "waf_block", "http_code": http_code}
        return {"status": "skip", "reason": f"http_{http_code}", "http_code": http_code}
    if http_code in ("200", "301", "302", "304"):
        # 检查关闭标志
        for pattern in CLOSE_PATTERNS:
            if pattern.lower() in body_lower:
                return {"status": "closed", "reason": f"text_match: {pattern}",
                        "http_code": http_code,
                        "final_url": parts[1] if len(parts) > 1 else ""}
        # 200 但页面为空(SPA)不算关闭
        if len(content.strip()) < 200:
            return {"status": "skip", "reason": "spa_empty_page", "http_code": http_code}
        return {"status": "open", "reason": "no_closed_marker", "http_code": http_code,
                "final_url": parts[1] if len(parts) > 1 else ""}
    # 其他状态码不判定
    return {"status": "skip", "reason": f"http_{http_code}", "http_code": http_code}

def main():
    with open(CAND_PATH, encoding="utf-8") as f:
        candidates = json.load(f)
    print(f"Loaded {len(candidates)} candidates")
    sample, pool_stats = sample_candidates(candidates, n=30)
    print(f"Sampled {len(sample)} (pools: {pool_stats})")
    results = []
    for i, c in enumerate(sample, 1):
        url = c["clean_url"]
        print(f"[{i}/30] {c['record_id']} {c['company']} | {url[:80]}")
        res = check_url(url, c["record_id"])
        results.append({
            "record_id": c["record_id"],
            "hash": c.get("hash", ""),
            "title": c.get("title", ""),
            "company": c.get("company", ""),
            "url": url,
            "raw_url": c.get("url", ""),
            **res,
        })
        print(f"   -> {res['status']}: {res['reason']}")
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump({"pool_stats": pool_stats, "results": results}, f, ensure_ascii=False, indent=2)
    closed = [r for r in results if r["status"] == "closed"]
    print(f"\n=== Summary ===")
    print(f"Sampled: {len(results)}")
    print(f"Closed: {len(closed)}")
    print(f"Open: {sum(1 for r in results if r['status']=='open')}")
    print(f"Skip: {sum(1 for r in results if r['status']=='skip')}")
    print(f"Closed record_ids: {[r['record_id'] for r in closed]}")

if __name__ == "__main__":
    main()
