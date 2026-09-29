import sys
sys.path.insert(0, "/opt/job_assistant")
import os
os.environ["DATA_DIR"] = "/opt/job_assistant/data"
from content_fetcher import fetch_content_full
import job_db

anns = job_db.get_announcements_for_llm(limit=3)
print(f"测试 {len(anns)} 条公告")
for a in anns:
    url = a.get("announcement_url")
    if not url or "weixin.qq.com" not in url:
        continue
    print(f"[测试] {a['company_name']}: {url[:70]}")
    result = fetch_content_full(url)
    text_len = len(result.get("text") or "")
    img_count = len(result.get("images") or [])
    print(f"  正文长度: {text_len}, 图片数: {img_count}")
    if result.get("error"):
        print(f"  错误: {result['error'][:150]}")
    if text_len > 0:
        print(f"  正文前100字: {result['text'][:100]}")
    print()
