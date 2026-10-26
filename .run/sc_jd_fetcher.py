#!/usr/bin/env python3
"""Parallel fetch Standard Chartered JD pages and extract structured JD text."""
import json
import re
import subprocess
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape

with open("/workspace/.run/sc_priority_list.json", encoding="utf-8") as f:
    priority_list = json.load(f)

# Take top 20 (mix of grad + investment + RM + markets)
# Filter out IT/data engineering/Dev only
EXCLUDE_PATTERNS = [
    "AI-Data-Engineer", "Lead-AI-Data", "Sr_-Assoc%2C-Business-Analyst",
    "Business-Analyst%2C-FM", "Development-Analyst", "Country-CDD-Analyst",
    "CDD-Analyst",
]

# Take grad programs + investment strategist + markets + relationship manager
KEEP_PRIORITIES = ["graduate_programme", "investment_finance", "markets_trading", "RM"]

final_list = []
for entry in priority_list:
    if any(p in entry["url"] for p in EXCLUDE_PATTERNS):
        continue
    if entry["bucket"] in KEEP_PRIORITIES:
        final_list.append(entry)
    if len(final_list) >= 25:
        break

print(f"Fetching {len(final_list)} SC JD pages in parallel...")

def strip_html(text):
    """Strip HTML tags and decode entities."""
    # Remove script/style
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.I)
    # Replace br/p with newline
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"</li>", "\n", text, flags=re.I)
    text = re.sub(r"</div>", "\n", text, flags=re.I)
    # Strip all remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()

def fetch_one(entry):
    url = entry["url"]
    try:
        # First fetch to follow redirects
        result = subprocess.run(
            ["curl", "-sL", "--max-time", "20", "-A", "Mozilla/5.0",
             "-b", "/workspace/.run/sc_cookies.txt",
             "-c", "/workspace/.run/sc_cookies.txt",
             url],
            capture_output=True, text=True, timeout=25
        )
        html = result.stdout
        if not html or len(html) < 1000:
            return {"url": url, "error": "empty_response", "bucket": entry["bucket"]}
        
        # Title
        title_m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        title = title_m.group(1).strip() if title_m else ""
        
        # Meta description
        meta_m = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html, re.I)
        meta_desc = meta_m.group(1) if meta_m else ""
        
        # Find job ID in URL
        job_id_m = re.search(r"/(\d+)/?$", url)
        job_id = job_id_m.group(1) if job_id_m else ""
        
        # Find posted date - search for "Posted on", "Date Posted", "Posted:"
        posted_date = ""
        for pattern in [r"Posted\s*(?:on|:)\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
                        r"Posted\s*(?:on|:)\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
                        r"Date\s*Posted[:\s]+([0-9]{4}-[0-9]{2}-[0-9]{2})",
                        r"Posted[:\s]+(\d+\s*\w+\s*\d+)",
                        r'"datePosted"\s*:\s*"([^"]+)"']:
            m = re.search(pattern, html, re.I)
            if m:
                posted_date = m.group(1)
                break
        
        # Find location (often in breadcrumb or page heading)
        loc_m = re.search(r'property="og:[^"]*location[^"]*"\s+content="([^"]+)"', html, re.I)
        location = loc_m.group(1) if loc_m else ""
        if not location:
            # Extract from URL
            url_city_m = re.search(r"/job/([A-Za-z\-]+?)-", url)
            location = url_city_m.group(1).replace("-", " ") if url_city_m else ""
        
        # Find the JD content section - look for the main job description div
        # SC uses style="font-size:10.0pt;font-family:arial, helvetica, sans-serif" pattern
        # Extract the larger content block with these styles
        jd_blocks = re.findall(
            r'<span style="font-size:10\.0pt[^"]*">([^<]+)</span>',
            html
        )
        jd_text = "\n".join(b.strip() for b in jd_blocks if b.strip())
        # Clean up
        jd_text = unescape(jd_text)
        # Truncate if too long
        if len(jd_text) > 5000:
            jd_text = jd_text[:5000] + "..."
        
        # If no JD text found, try general extraction
        if not jd_text:
            # Find body content
            body_m = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.I)
            if body_m:
                body = body_m.group(1)
                # Strip nav/header/footer
                body = re.sub(r"<nav[^>]*>.*?</nav>", "", body, flags=re.DOTALL | re.I)
                body = re.sub(r"<header[^>]*>.*?</header>", "", body, flags=re.DOTALL | re.I)
                body = re.sub(r"<footer[^>]*>.*?</footer>", "", body, flags=re.DOTALL | re.I)
                body = re.sub(r"<script[^>]*>.*?</script>", "", body, flags=re.DOTALL | re.I)
                body = re.sub(r"<style[^>]*>.*?</style>", "", body, flags=re.DOTALL | re.I)
                jd_text = strip_html(body)[:5000]
        
        # Check for "Apply" button or closed status
        is_closed = bool(re.search(r"job no longer available|position closed|no longer accepting|expired|已关闭|职位已下线", html, re.I))
        has_apply = bool(re.search(r"apply", html, re.I))
        
        # Determine title from URL or title tag
        if not title:
            t_m = re.search(r"/job/[^/]+-([^/]+)/\d+", url)
            title = t_m.group(1).replace("-", " ") if t_m else ""
        
        # Extract posted date from header if available (SC sometimes shows "Posted X days ago")
        rel_date_m = re.search(r"Posted\s*(\d+)\s*days?\s*ago", html, re.I)
        rel_date = rel_date_m.group(0) if rel_date_m else ""
        
        return {
            "url": url,
            "job_id": job_id,
            "title": title,
            "location": location,
            "meta_desc": meta_desc,
            "jd_text": jd_text,
            "posted_date": posted_date,
            "relative_date": rel_date,
            "is_closed": is_closed,
            "has_apply": has_apply,
            "bucket": entry["bucket"],
            "fetch_success": True,
        }
    except Exception as e:
        return {"url": url, "error": str(e), "bucket": entry["bucket"], "fetch_success": False}

results = []
with ThreadPoolExecutor(max_workers=8) as executor:
    futures = {executor.submit(fetch_one, e): e for e in final_list}
    for future in as_completed(futures):
        r = future.result()
        results.append(r)
        status = "OK" if r.get("fetch_success") else "FAIL"
        print(f"  [{status}] {r.get('url', '')[:80]} -> title={r.get('title', r.get('error', ''))[:60]}")

# Save
with open("/workspace/.run/sc_jds.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n=== Total fetched: {len(results)} ===")
print(f"Success: {sum(1 for r in results if r.get('fetch_success'))}")
print(f"Failed: {sum(1 for r in results if not r.get('fetch_success'))}")
print(f"Closed: {sum(1 for r in results if r.get('is_closed'))}")
print(f"With JD text: {sum(1 for r in results if r.get('jd_text'))}")
print(f"File: /workspace/.run/sc_jds.json")
