import sys
sys.path.insert(0, "/opt/job_assistant")
import os
os.environ["DATA_DIR"] = "/opt/job_assistant/data"
import time
import random

from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

# 从 .env 读取 Cookie
from dotenv import load_dotenv
load_dotenv("/opt/job_assistant/.env")
WECHAT_COOKIE = os.getenv("WECHAT_COOKIE", "")

def test_wechat(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        # 添加 Cookie
        if WECHAT_COOKIE:
            cookies = []
            for pair in WECHAT_COOKIE.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    name, value = pair.split("=", 1)
                    cookies.append({
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": ".qq.com",
                        "path": "/",
                    })
            context.add_cookies(cookies)

        page = context.new_page()
        # 应用 stealth
        stealth_sync(page)

        # 先访问微信主页建立会话
        try:
            page.goto("https://mp.weixin.qq.com/", timeout=15000)
            time.sleep(random.uniform(2, 4))
        except:
            pass

        # 访问目标文章
        try:
            page.goto(url, timeout=30000)
            time.sleep(random.uniform(3, 5))
        except Exception as e:
            print(f"  页面加载超时: {str(e)[:100]}")

        # 滚动触发懒加载
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 300)")
            time.sleep(0.5)

        # 提取正文
        text = page.evaluate("""() => {
            const el = document.querySelector('#js_content') || document.querySelector('.rich_media_content');
            if (el) return el.innerText || '';
            return document.body.innerText || '';
        }""")

        # 提取图片
        images = page.evaluate("""() => {
            const imgs = document.querySelectorAll('#js_content img');
            return Array.from(imgs).map(img => img.getAttribute('data-src') || img.src).filter(Boolean);
        }""")

        # 检查是否被风控
        if "环境异常" in text or "去验证" in text:
            print(f"  ❌ 被风控: 环境异常")
        else:
            print(f"  ✅ 正文长度: {len(text)}, 图片数: {len(images)}")
            if len(text) > 50:
                print(f"  正文前150字: {text[:150]}")

        browser.close()

# 测试3条
urls = [
    "https://mp.weixin.qq.com/s/nqP-jFgtwrG-ETi3BVAmMw",  # 东吴证券
    "https://mp.weixin.qq.com/s/YRvDNDiUfHOXVRLwkyrWGg",  # 方田教育
]
for url in urls:
    print(f"[测试] {url}")
    try:
        test_wechat(url)
    except Exception as e:
        print(f"  异常: {str(e)[:150]}")
    print()
