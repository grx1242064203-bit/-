"""
正文抓取器 — 从招聘公告 URL 抓取页面正文,供 LLM 拆岗。

设计原则(对抗性审查):
1. Playwright 优先(JS 渲染页面如微信公众号),降级 requests(静态页面)
2. 超时 30s + 重试 2 次,失败不阻塞(标记 failed,记录待重试)
3. 抓取内容缓存(URL hash → 文件),避免重复抓取
4. PDF 用 requests 下载 + pypdf 提取文本
5. Playwright 不可用时自动降级为 requests + BeautifulSoup

数据流:
  announcement_url → 判断类型(微信/普通/PDF)
  → Playwright 或 requests 抓取 → 提取正文文本 → 缓存 → 返回
"""
import hashlib
import json
import logging
import os
import random
import time
from typing import Optional, Dict, List, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from config import settings

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(settings.DATA_DIR, "crawl_cache")
FETCH_TIMEOUT = 30
MAX_RETRIES = 2
WECHAT_DOMAIN = "mp.weixin.qq.com"


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def _cache_path(url: str) -> str:
    return os.path.join(CACHE_DIR, f"{_url_hash(url)}.txt")


def get_cached_content(url: str) -> Optional[str]:
    """读取缓存的正文内容,不存在返回 None。"""
    path = _cache_path(url)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None
    return None


def _save_cache(url: str, content: str):
    """缓存正文内容到文件。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(_cache_path(url), "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        logger.warning(f"缓存写入失败 {url}: {e}")


def _is_pdf(url: str) -> bool:
    return url.lower().endswith(".pdf") or ".pdf?" in url.lower()


def _is_wechat(url: str) -> bool:
    return WECHAT_DOMAIN in urlparse(url).netloc


def _fetch_with_requests(url: str) -> str:
    """用 requests 抓取静态页面/PDF,返回纯文本。"""
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"),
    }
    resp = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT, allow_redirects=True)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")

    if _is_pdf(url) or "pdf" in content_type.lower():
        return _extract_pdf_text(resp.content)

    # HTML 页面:提取正文文本
    resp.encoding = resp.apparent_encoding or "utf-8"
    return _extract_html_text(resp.text)


def _extract_pdf_text(content: bytes) -> str:
    """从 PDF 二进制数据提取文本。"""
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        texts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                texts.append(text)
        return "\n".join(texts).strip()
    except Exception as e:
        logger.warning(f"PDF 文本提取失败: {e}")
        return ""


def _extract_html_text(html: str) -> str:
    """从 HTML 提取正文文本(去除脚本/样式/导航)。"""
    soup = BeautifulSoup(html, "html.parser")
    # 移除无关标签
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    # 微信公众号:优先提取 #js_content
    wechat_content = soup.find(id="js_content")
    if wechat_content:
        return wechat_content.get_text(separator="\n", strip=True)
    # 通用:提取 body 文本
    body = soup.find("body") or soup
    text = body.get_text(separator="\n", strip=True)
    # 压缩连续空行
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)


# 微信 Cookie(从浏览器复制,用于绕过微信反爬)
WECHAT_COOKIE = os.getenv("WECHAT_COOKIE", "")

# 微信内置浏览器 UA(更接近真实微信环境)
WECHAT_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7 Build/TQ3A.230805.001; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.5845.163 "
    "Mobile Safari/537.36 MMWEBID/1234 MicroMessenger/8.0.40.2420(0x28002837) "
    "WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64"
)

# 普通桌面浏览器 UA
DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

MAX_IMAGES = 4  # 最多提取 4 张图片


def _fetch_with_playwright(url: str) -> Tuple[str, List[str]]:
    """用 Playwright 抓取 JS 渲染页面,返回 (正文文本, 图片URL列表)。

    反检测措施(借鉴成熟方案):
    1. 微信公众号用微信内置浏览器 UA,普通页面用桌面 UA
    2. 禁用 navigator.webdriver 标志
    3. 随机延迟 2-5s(模拟人类操作)
    4. 微信公众号先访问主页建立会话
    5. 滚动触发懒加载后提取正文+图片
    """
    from playwright.sync_api import sync_playwright
    is_wechat = _is_wechat(url)
    ua = WECHAT_UA if is_wechat else DESKTOP_UA

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        try:
            context_kwargs = {
                "user_agent": ua,
                "viewport": {"width": 1920, "height": 1080} if not is_wechat else {"width": 390, "height": 844},
                "locale": "zh-CN",
            }
            # 微信公众号:添加 Cookie 绕过反爬
            if is_wechat and WECHAT_COOKIE:
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
                context_kwargs["cookies"] = cookies
            context = browser.new_context(**context_kwargs)
            # 禁用 webdriver 标志 + 模拟 chrome 属性
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                "Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});"
            )
            page = context.new_page()
            page.set_default_timeout(FETCH_TIMEOUT * 1000)
            page.set_extra_http_headers({
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })

            # 随机延迟 2-5s(模拟人类)
            time.sleep(random.uniform(2, 5))

            # 微信公众号:先访问 mp.weixin.qq.com 建立会话
            if is_wechat:
                try:
                    page.goto("https://mp.weixin.qq.com/", wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(random.uniform(1000, 2000))
                except Exception:
                    pass

            page.goto(url, wait_until="networkidle", timeout=FETCH_TIMEOUT * 1000)
            # 随机延迟
            page.wait_for_timeout(random.uniform(1500, 3000))

            image_urls = []
            # 微信公众号:等待正文加载并滚动触发懒加载
            if is_wechat:
                try:
                    page.wait_for_selector("#js_content", timeout=15000)
                    # 滚动到底部触发懒加载
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(random.uniform(1500, 2500))
                    # 提取正文图片(最多 MAX_IMAGES 张)
                    image_urls = page.evaluate("""
                        () => {
                            const imgs = document.querySelectorAll('#js_content img');
                            const urls = [];
                            for (const img of imgs) {
                                const src = img.getAttribute('data-src') || img.src;
                                if (src && src.startsWith('http')) {
                                    urls.push(src);
                                    if (urls.length >= %d) break;
                                }
                            }
                            return urls;
                        }
                    """ % MAX_IMAGES)
                except Exception:
                    pass  # 选择器未出现也继续
            else:
                # 普通页面:提取 body 内图片
                try:
                    image_urls = page.evaluate("""
                        () => {
                            const imgs = document.querySelectorAll('img');
                            const urls = [];
                            for (const img of imgs) {
                                const src = img.src;
                                if (src && src.startsWith('http') && !src.includes('logo') && !src.includes('icon')) {
                                    urls.push(src);
                                    if (urls.length >= %d) break;
                                }
                            }
                            return urls;
                        }
                    """ % MAX_IMAGES)
                except Exception:
                    pass

            html = page.content()
            text = _extract_html_text(html)
            return text, image_urls
        finally:
            browser.close()


def fetch_content(url: str, use_cache: bool = True) -> str:
    """抓取公告正文,返回纯文本。失败返回空字符串。"""
    result = fetch_content_full(url, use_cache=use_cache)
    return result["text"]


def fetch_content_full(url: str, use_cache: bool = True) -> Dict:
    """
    抓取公告正文,返回 {"text": str, "images": List[str]}。

    策略:
    1. 查缓存(命中直接返回)
    2. PDF → requests 下载 + pypdf
    3. 微信公众号/JS 页面 → Playwright(不可用降级 requests)
    4. 普通页面 → requests + BeautifulSoup
    5. 重试 2 次,成功后缓存
    """
    if not url or not url.strip():
        return {"text": "", "images": []}
    url = url.strip()

    # 1. 缓存
    if use_cache:
        cached = get_cached_content(url)
        if cached is not None:
            logger.debug(f"缓存命中: {url[:60]}")
            return {"text": cached, "images": []}

    # 2. 抓取(带重试)
    content = ""
    images: List[str] = []
    for attempt in range(MAX_RETRIES + 1):
        try:
            if _is_pdf(url):
                content = _fetch_with_requests(url)
            elif _is_wechat(url):
                # 微信优先 Playwright
                try:
                    result = _fetch_with_playwright(url)
                    content, images = result
                except ImportError:
                    logger.warning("Playwright 未安装,降级 requests 抓取微信文章")
                    content = _fetch_with_requests(url)
                except Exception as e:
                    logger.warning(f"Playwright 抓取失败,降级 requests: {e}")
                    content = _fetch_with_requests(url)
            else:
                # 普通页面:先试 requests(快),失败再试 Playwright
                try:
                    content = _fetch_with_requests(url)
                    if len(content) < 100:
                        raise ValueError("内容过少,尝试 Playwright")
                except Exception:
                    try:
                        result = _fetch_with_playwright(url)
                        content, images = result
                    except ImportError:
                        if not content:
                            raise
                    except Exception as e:
                        if not content:
                            raise
            if content:
                break
        except Exception as e:
            logger.warning(f"抓取失败(尝试 {attempt + 1}/{MAX_RETRIES + 1}) {url[:60]}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
            else:
                logger.error(f"抓取彻底失败 {url}: {e}")
                return {"text": "", "images": []}

    # 3. 缓存
    if content:
        _save_cache(url, content)
        logger.info(f"抓取成功: {url[:60]}... ({len(content)} 字符, {len(images)} 图)")

    return {"text": content, "images": images}


def fetch_announcement_contents(limit: int = 100) -> Dict:
    """
    批量抓取待处理公告的正文,更新 crawl_status。
    取 announcements WHERE crawl_status='pending'。

    Returns: {"total": N, "success": M, "failed": K}
    """
    import job_db
    announcements = job_db.get_announcements_for_crawl(limit=limit)
    total = len(announcements)
    success = 0
    failed = 0

    for ann in announcements:
        url = ann.get("announcement_url", "")
        result = fetch_content_full(url)
        content = result["text"]
        images = result["images"]
        if content and len(content) > 50:
            # 正文 + 图片URL存入 DB,避免重复爬取
            images_json = json.dumps(images, ensure_ascii=False) if images else ""
            job_db.update_crawl_status(ann["id"], "success", content=content)
            if images_json:
                job_db.update_announcement_images(ann["id"], images_json)
            success += 1
        else:
            job_db.update_crawl_status(ann["id"], "failed", error="内容为空或过短")
            failed += 1
        # 控制抓取节奏
        time.sleep(0.5)

    logger.info(f"正文抓取完成: 总计={total} 成功={success} 失败={failed}")
    return {"total": total, "success": success, "failed": failed}
