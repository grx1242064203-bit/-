#!/usr/bin/env python3
"""严格复查初步判定为 closed 的 8 条,只保留明确字样匹配或 HTTP 404/410。"""
import json
import subprocess
import re

RESULTS_PATH = "/workspace/.run/recheck_results.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# 严格明确字样(任务原文要求)
STRICT_PATTERNS = [
    "职位已关闭", "已下线", "职位已下线", "该职位已关闭", "该职位已下线",
    "position closed", "position is closed",
    "no longer available", "no longer accepting applications",
    "expired", "job closed", "job has expired",
    "the position you are looking for is no longer",
    "job not found", "job does not exist",
]

with open(RESULTS_PATH, encoding="utf-8") as f:
    data = json.load(f)

closed = [r for r in data["results"] if r["status"] == "closed"]
print(f"Re-verifying {len(closed)} closed candidates with strict patterns\n")

verified = []
for r in closed:
    url = r["url"]
    print(f"=== {r['record_id']} | {r['company']} | {url[:90]}")
    # 重新 curl
    cmd = ["curl", "-sL", "--max-time", "15", "-A", UA,
           "-o", "/tmp/v_page.html", "-w", "%{http_code}|%{url_effective}", url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except Exception as e:
        print(f"  curl error: {e}")
        continue
    out = proc.stdout.strip() if proc.stdout else ""
    parts = out.split("|")
    http_code = parts[0]
    final_url = parts[1] if len(parts) > 1 else ""
    try:
        content = open("/tmp/v_page.html", encoding="utf-8", errors="ignore").read()
    except Exception:
        content = ""
    body_lower = content.lower()
    print(f"  HTTP: {http_code}, final: {final_url[:90]}, body_len: {len(content)}")

    is_closed = False
    reason = ""
    # 1. HTTP 404/410
    if http_code in ("404", "410"):
        is_closed = True
        reason = f"http_{http_code}"
    # 2. 严格字样
    if not is_closed:
        for p in STRICT_PATTERNS:
            if p.lower() in body_lower:
                is_closed = True
                reason = f"strict_text: {p}"
                break
    # 显示页面上下文帮助判断
    if is_closed:
        # 找到匹配位置,打印上下文
        for p in STRICT_PATTERNS:
            idx = body_lower.find(p.lower())
            if idx >= 0:
                ctx = content[max(0,idx-60):idx+80].replace("\n", " ")
                print(f"  CTX: ...{ctx}...")
                break
        print(f"  => CLOSED: {reason}")
        verified.append({**r, "verify_status": "closed", "verify_reason": reason,
                         "verify_http": http_code, "verify_final_url": final_url})
    else:
        print(f"  => NOT CLOSED (ambiguous)")
        verified.append({**r, "verify_status": "ambiguous", "verify_reason": "no_strict_match",
                         "verify_http": http_code, "verify_final_url": final_url})
    print()

# 保存严格复查结果
with open("/workspace/.run/recheck_verified.json", "w", encoding="utf-8") as f:
    json.dump(verified, f, ensure_ascii=False, indent=2)

truly_closed = [v for v in verified if v["verify_status"] == "closed"]
print(f"=== Final strict closed: {len(truly_closed)} ===")
for v in truly_closed:
    print(f"  {v['record_id']} | {v['company']} | {v['verify_reason']}")
print(f"\nAmbiguous (not archived): {sum(1 for v in verified if v['verify_status']=='ambiguous')}")
