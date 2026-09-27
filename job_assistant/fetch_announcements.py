"""
阶段一:并发抓取公告正文 + 图片 URL(不做 LLM 分析)。

设计目标:
- 把"慢"的 Playwright 抓取与"贵"的 LLM 分析解耦
- 多线程并发抓取(默认 4 个 worker),大幅提升吞吐
- 结果写入 JSONL(fetch_results.jsonl),支持断点续传
- 每条记录含 dedup_hash,便于阶段二关联回原岗位

输出文件格式(JSONL, 每行一条):
{
  "dedup_hash": "...",
  "company": "...",
  "job_title": "...",
  "url": "...",
  "text": "公告正文文字",
  "images": ["图片url1", ...],
  "status": "ok" | "blocked" | "fetch_failed" | "link_invalid" | "no_url",
  "is_wechat": true/false
}

运行: python3 fetch_announcements.py [--limit 200] [--workers 4]
"""
import os
import sys
import json
import time
import logging
import argparse
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ.setdefault("DATA_DIR", "/workspace/job_assistant/data")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-b62b83d5c36d4e6aa87925c8b66b4ab3")
sys.path.insert(0, "/workspace/job_assistant")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("/workspace/job_assistant/fetch_announcements.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

import job_db
job_db.init_db()
from collector import fetch_jd_by_source

FETCH_RESULTS_PATH = "/workspace/job_assistant/fetch_results.jsonl"

# WeChat UA
WECHAT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
             "AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/120.0.0.0 Safari/537.36")


def load_fetched_hashes() -> set:
    """加载已抓取的 dedup_hash 集合(断点续传)"""
    hashes = set()
    if os.path.exists(FETCH_RESULTS_PATH):
        with open(FETCH_RESULTS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    h = rec.get("dedup_hash")
                    if h:
                        hashes.add(h)
                except Exception:
                    continue
    return hashes


def append_result(rec: dict):
    """追加一条抓取结果到 JSONL"""
    with open(FETCH_RESULTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def check_link_valid(url: str, timeout: int = 10) -> bool:
    import requests
    if not url:
        return False
    try:
        headers = {"User-Agent": WECHAT_UA}
        resp = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200:
            return True
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
        return resp.status_code == 200
    except Exception:
        return False


def fetch_one(job: dict) -> dict:
    """
    抓取单条公告。线程安全:每个线程自己创建浏览器。
    返回 dict(写入 JSONL 的记录)。
    """
    dedup_hash = job_db.compute_dedup_hash(
        job["company"], job["job_title"], job.get("apply_url", "")
    )
    url = job.get("announcement_url") or job.get("apply_url") or ""
    company = job.get("company", "")
    job_title = job.get("job_title", "")

    base_rec = {
        "dedup_hash": dedup_hash,
        "company": company,
        "job_title": job_title,
        "url": url,
        "text": "",
        "images": [],
        "is_wechat": "mp.weixin.qq.com" in url,
    }

    if not url:
        return {**base_rec, "status": "no_url"}

    # 链接有效性快速检查
    if not check_link_valid(url):
        return {**base_rec, "status": "link_invalid"}

    is_wechat = "mp.weixin.qq.com" in url

    if is_wechat:
        # 微信公众号:用 Playwright 抓取(反爬需要渲染)
        text, images = fetch_with_playwright(url)
        if not text and not images:
            return {**base_rec, "status": "blocked"}
        return {**base_rec, "text": text, "images": images, "status": "ok"}
    else:
        # 非微信:requests 抓取
        text = fetch_jd_by_source(url, timeout=20)
        if not text or len(text.strip()) < 30:
            return {**base_rec, "status": "fetch_failed"}
        return {**base_rec, "text": text, "images": [], "status": "ok"}


def fetch_with_playwright(url: str):
    """
    用 Playwright 抓取微信公众号正文 + 图片。
    每个调用独立创建浏览器(线程隔离)。
    返回 (text, images)
    """
    from playwright.sync_api import sync_playwright

    text = ""
    images = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                user_agent=WECHAT_UA,
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                # 等待正文渲染
                time.sleep(random.uniform(2.5, 4.5))

                content = page.content()
                if "环境异常" in content:
                    logger.warning(f"反爬拦截: {url}")
                    browser.close()
                    return "", []

                text = page.evaluate("""() => {
                    const el = document.querySelector('#js_content');
                    if (el) {
                        el.querySelectorAll('script, style').forEach(s => s.remove());
                        return el.innerText.trim();
                    }
                    return document.body.innerText.trim();
                }""")

                images = page.evaluate("""() => {
                    const el = document.querySelector('#js_content') || document.body;
                    const imgs = el.querySelectorAll('img');
                    return Array.from(imgs)
                        .map(img => img.getAttribute('data-src') || img.src)
                        .filter(u => u && u.startsWith('http'));
                }""")
            except Exception as e:
                logger.error(f"Playwright 抓取失败 {url}: {e}")
            finally:
                browser.close()
    except Exception as e:
        logger.error(f"Playwright 启动失败: {e}")

    return text, images


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="本次最多抓取条数(0=不限制)")
    parser.add_argument("--workers", type=int, default=4,
                        help="并发抓取线程数")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("阶段一:公告抓取启动")
    logger.info(f"workers={args.workers}, limit={args.limit or '不限'}")
    logger.info("=" * 60)

    # 1. 加载已抓取记录(断点续传)
    fetched = load_fetched_hashes()
    logger.info(f"已抓取记录数: {len(fetched)}")

    # 2. 拉取待分析岗位
    jobs = job_db.get_unanalyzed_jobs(limit=10000)
    logger.info(f"数据库待分析岗位: {len(jobs)} 条")

    # 过滤掉已抓取的
    todo = []
    for j in jobs:
        h = job_db.compute_dedup_hash(j["company"], j["job_title"], j.get("apply_url", ""))
        if h not in fetched:
            todo.append(j)

    if args.limit > 0:
        todo = todo[:args.limit]

    logger.info(f"本次待抓取: {len(todo)} 条")

    if not todo:
        logger.info("没有需要抓取的岗位")
        return

    # 3. 并发抓取
    stats = {"ok": 0, "blocked": 0, "fetch_failed": 0, "link_invalid": 0, "no_url": 0}
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_one, j): j for j in todo}
        done_count = 0
        for fut in as_completed(futures):
            done_count += 1
            try:
                rec = fut.result()
                append_result(rec)
                status = rec["status"]
                stats[status] = stats.get(status, 0) + 1
            except Exception as e:
                logger.exception(f"抓取任务异常: {e}")
                stats["fetch_failed"] = stats.get("fetch_failed", 0) + 1

            if done_count % 10 == 0:
                elapsed = time.time() - start
                rate = done_count / elapsed if elapsed > 0 else 0
                logger.info(f"进度 {done_count}/{len(todo)} "
                            f"({rate:.1f}条/秒) stats={stats}")

    elapsed = time.time() - start
    logger.info("=" * 60)
    logger.info(f"阶段一完成: 共 {len(todo)} 条, 耗时 {elapsed:.1f}s")
    logger.info(f"统计: {stats}")
    logger.info(f"结果文件: {FETCH_RESULTS_PATH}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
