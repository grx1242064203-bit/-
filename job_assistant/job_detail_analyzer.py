"""
岗位详情分析器 — 从飞书同步的"岗位大类"记录,抓取公告链接,
用 DeepSeek AI 解析出具体岗位列表,拆分为多条岗位记录。

核心价值:飞书表的"招聘岗位"字段是大类(如"研发类/销售类"),
用户需要的是具体岗位(如"Java开发工程师")。本模块负责这个转换。

技术方案:
1. 微信公众号链接:用 Playwright 绕过反爬,提取正文文字 + 图片
2. 图片用 DeepSeek-VL 做 OCR/理解,提取岗位信息
3. 文字+图片识别结果合并,用 DeepSeek 拆分具体岗位(25+ 维度)
4. 非微信链接:用 requests 直接抓取文字内容
"""
import logging
import re
import time
import base64
import io
from typing import List, Dict, Optional

import requests

from llm_client import LLMClient
from collector import fetch_jd_by_source
import job_db

logger = logging.getLogger(__name__)

# 本届校招关键词
CURRENT_GRADE_KEYWORDS = [
    "2027届", "27届", "2027校园招聘", "2027校招",
    "2026届", "26届",
]

NON_CAMPUS_KEYWORDS = ["社会招聘", "社招", "experienced"]

# Playwright 是否可用(服务器内存不够时不可用)
_PLAYWRIGHT_AVAILABLE = None


def _is_playwright_available() -> bool:
    """检测 Playwright + Chromium 是否可用"""
    global _PLAYWRIGHT_AVAILABLE
    if _PLAYWRIGHT_AVAILABLE is not None:
        return _PLAYWRIGHT_AVAILABLE
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        _PLAYWRIGHT_AVAILABLE = True
    except Exception as e:
        logger.warning(f"Playwright 不可用: {e}")
        _PLAYWRIGHT_AVAILABLE = False
    return _PLAYWRIGHT_AVAILABLE


def check_link_valid(url: str, timeout: int = 10) -> bool:
    """检查链接是否有效"""
    if not url:
        return False
    try:
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
        }
        resp = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        return resp.status_code == 200
    except Exception:
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
            return resp.status_code == 200
        except Exception:
            return False


def is_current_grade(text: str) -> bool:
    """校验公告正文是否面向本届校招"""
    if not text:
        return False
    if any(kw in text for kw in NON_CAMPUS_KEYWORDS):
        if not any(kw in text for kw in CURRENT_GRADE_KEYWORDS):
            return False
    campus_indicators = ["校招", "校园招聘", "应届", "毕业生", "应届生", "2027", "2026"]
    if any(kw in text for kw in campus_indicators):
        return True
    return True


def fetch_with_playwright(url: str) -> Dict:
    """
    用 Playwright 抓取网页内容(主要用于微信公众号)。

    返回: {"text": 正文文字, "images": [图片url列表], "title": 标题}
    """
    from playwright.sync_api import sync_playwright
    from PIL import Image

    result = {"text": "", "images": [], "title": ""}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            time.sleep(3)

            # 检查是否被反爬拦截
            content = page.content()
            if "环境异常" in content:
                logger.warning(f"Playwright 仍被反爬拦截: {url}")
                browser.close()
                return result

            # 提取标题
            result["title"] = page.evaluate(
                "() => document.querySelector('#activity-name')?.textContent?.trim() || document.title || ''"
            )

            # 提取正文文字
            result["text"] = page.evaluate("""() => {
                const el = document.querySelector('#js_content');
                if (el) {
                    el.querySelectorAll('script, style').forEach(s => s.remove());
                    return el.innerText.trim();
                }
                return document.body.innerText.trim();
            }""")

            # 提取正文中的图片
            result["images"] = page.evaluate("""() => {
                const el = document.querySelector('#js_content') || document.body;
                const imgs = el.querySelectorAll('img');
                return Array.from(imgs)
                    .map(img => img.getAttribute('data-src') || img.src)
                    .filter(u => u && u.startsWith('http'));
            }""")

        except Exception as e:
            logger.error(f"Playwright 抓取失败: {e}")
        finally:
            browser.close()

    return result


def compress_image(image_bytes: bytes, max_width: int = 800, quality: int = 70) -> Optional[bytes]:
    """压缩图片,返回 JPEG 字节流(适配 DeepSeek 视觉 API)"""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if w > max_width:
            new_h = int(h * max_width / w)
            img = img.resize((max_width, new_h), Image.LANCZOS)
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=quality)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"图片压缩失败: {e}")
        return None


def analyze_images_with_vl(image_urls: List[str], llm: LLMClient) -> str:
    """
    用 DeepSeek-VL 分析多张图片,提取招聘岗位文字信息。

    返回: 所有图片中提取的文字内容拼接
    """
    if not image_urls or not llm.api_key:
        return ""

    all_text = []
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"),
        "Referer": "https://mp.weixin.qq.com/",
    }

    for img_url in image_urls[:4]:  # 最多分析4张图(平衡速度和覆盖率)
        for attempt in range(2):  # 失败重试1次
            try:
                resp = requests.get(img_url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    break

                # 压缩图片(更激进,避免 API 400)
                compressed = compress_image(resp.content, max_width=600, quality=60)
                if not compressed:
                    break

                # 检查压缩后大小(base64 后不超过 3MB)
                b64 = base64.b64encode(compressed).decode("utf-8")
                if len(b64) > 3 * 1024 * 1024:
                    logger.warning(f"图片过大({len(b64)}b),跳过")
                    break
                data_url = f"data:image/jpeg;base64,{b64}"

                prompt = """这是一张校园招聘公告图片。请提取图片中所有招聘岗位相关信息,包括:
1. 所有岗位名称
2. 每个岗位的工作地点、学历要求、专业要求
3. 招聘人数
4. 岗位职责和任职要求
5. 其他招聘相关信息

请完整提取,用中文输出。"""

                vl_resp = requests.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={
                        "Authorization": f"Bearer {llm.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": llm.model,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        }],
                        "temperature": 0.1,
                        "max_tokens": 2000,
                    },
                    timeout=90,
                )
                if vl_resp.status_code == 400:
                    err_body = vl_resp.text[:300]
                    logger.warning(f"VL API 400 错误: {err_body}")
                    if attempt == 0:
                        time.sleep(2)
                        continue
                    break
                vl_resp.raise_for_status()
                text = vl_resp.json()["choices"][0]["message"]["content"]
                all_text.append(text)
                logger.info(f"图片分析成功,提取 {len(text)} 字符")
                break

            except Exception as e:
                logger.warning(f"图片分析失败(attempt {attempt+1}): {e}")
                if attempt == 0:
                    time.sleep(2)
                    continue
                break

    return "\n".join(all_text)


def analyze_one_job(job: Dict, llm: LLMClient) -> Dict:
    """
    分析单条岗位(从公告解析具体岗位)。

    返回: {
        "status": "success" | "no_url" | "link_invalid" | "fetch_failed" | "not_current_grade" | "parse_empty",
        "specific_jobs": [...],   # 解析出的具体岗位列表(含全部维度)
        "original_updated": {...} # 原记录需更新的字段
    }
    """
    url = job.get("announcement_url") or job.get("apply_url") or ""
    if not url:
        return {"status": "no_url", "specific_jobs": [], "original_updated": {}}

    if not check_link_valid(url):
        return {"status": "link_invalid", "specific_jobs": [], "original_updated": {"link_valid": 0}}

    # 根据链接类型选择抓取方式
    is_wechat = "mp.weixin.qq.com" in url
    text = ""
    images = []

    if is_wechat and _is_playwright_available():
        # 微信公众号:用 Playwright 抓取
        pw_result = fetch_with_playwright(url)
        text = pw_result.get("text", "")
        images = pw_result.get("images", [])
        logger.info(f"Playwright 抓取: 文字{len(text)}字, 图片{len(images)}张")

        # 如果文字很少但有图片,用 VL 分析图片
        if len(text.strip()) < 50 and images:
            logger.info(f"文字不足,用 DeepSeek-VL 分析 {len(images)} 张图片")
            image_text = analyze_images_with_vl(images, llm)
            if image_text:
                text = (text + "\n" + image_text).strip()
    else:
        # 非微信链接或 Playwright 不可用:用 requests 抓取
        text = fetch_jd_by_source(url, timeout=20)

    if not text or len(text.strip()) < 30:
        return {"status": "fetch_failed", "specific_jobs": [], "original_updated": {}}

    # 本届校验
    if not is_current_grade(text):
        return {"status": "not_current_grade", "specific_jobs": [], "original_updated": {"status": "已关闭"}}

    # AI 解析具体岗位(增强版:25+ 维度)
    specific_jobs = llm.parse_announcement_jobs_enhanced(text, job.get("company", ""))
    if not specific_jobs:
        # 降级用普通版
        specific_jobs = llm.parse_announcement_jobs(text, job.get("company", ""))

    if not specific_jobs:
        summary = llm.generate_jd_summary(text, job.get("job_title", ""))
        return {
            "status": "parse_empty",
            "specific_jobs": [],
            "original_updated": {"jd_summary": summary},
        }

    return {
        "status": "success",
        "specific_jobs": specific_jobs,
        "original_updated": {},
    }


def run_analysis(batch_size: int = 50, llm: LLMClient = None) -> Dict:
    """
    批量分析未分析的岗位。
    返回统计: {"analyzed": N, "new_jobs": M, "link_invalid": N, ...}
    """
    if llm is None:
        llm = LLMClient()

    stats = {"analyzed": 0, "new_jobs": 0, "link_invalid": 0,
             "fetch_failed": 0, "not_current_grade": 0, "parse_empty": 0, "errors": 0}

    jobs = job_db.get_unanalyzed_jobs(limit=batch_size)
    logger.info(f"待分析岗位: {len(jobs)} 条")

    for job in jobs:
        dedup_hash = job_db.compute_dedup_hash(
            job["company"], job["job_title"], job.get("apply_url", "")
        )
        try:
            result = analyze_one_job(job, llm)
            status = result["status"]

            if status == "success":
                # 拆分:为每个具体岗位创建新记录,继承原记录的公司/行业/性质等
                for sj in result["specific_jobs"]:
                    new_job = {
                        "company": job["company"],
                        "job_title": sj["job_title"],
                        "department": sj.get("department", ""),
                        "salary": sj.get("salary", ""),
                        "education": sj.get("education", "") or job.get("education", ""),
                        "locations": sj.get("locations", "") or job.get("locations", ""),
                        "industry": job.get("industry", ""),
                        "company_type": job.get("company_type", ""),
                        "difficulty": job.get("difficulty", ""),
                        "recruitment_stage": job.get("recruitment_stage", ""),
                        "target_min_grade": job.get("target_min_grade"),
                        "target_max_grade": job.get("target_max_grade"),
                        "apply_url": job.get("apply_url", ""),
                        "announcement_url": job.get("announcement_url", ""),
                        "jd_summary": sj.get("jd_summary", ""),
                        "publish_time": job.get("publish_time", ""),
                        "deadline": job.get("deadline", ""),
                        "is_fresh_graduate": sj.get("is_fresh_graduate", True),
                        "mt_program": sj.get("mt_program", False),
                        "source": job.get("source", "feishu"),
                        "link_valid": 1,
                        "detail_analyzed": True,
                        # 精准匹配扩展字段
                        "job_category": sj.get("job_category", ""),
                        "job_subcategory": sj.get("job_subcategory", ""),
                        "hard_skills": sj.get("hard_skills", ""),
                        "soft_skills": sj.get("soft_skills", ""),
                        "certifications": sj.get("certifications", ""),
                        "languages": sj.get("languages", ""),
                        "major_required": sj.get("major_required", ""),
                        "major_category": sj.get("major_category", ""),
                        "min_education": sj.get("min_education", ""),
                        "education_preference": sj.get("education_preference", ""),
                        "city": sj.get("city", ""),
                        "province": sj.get("province", ""),
                        "is_remote": sj.get("is_remote", False),
                        "career_track": sj.get("career_track", ""),
                        "career_level": sj.get("career_level", ""),
                        "travel_frequency": sj.get("travel_frequency", ""),
                        "overtime_level": sj.get("overtime_level", ""),
                        "recruitment_process": sj.get("recruitment_process", ""),
                        "has_written_test": sj.get("has_written_test", False),
                        "headcount": sj.get("headcount", ""),
                        "responsibilities": sj.get("responsibilities", ""),
                        "requirements": sj.get("requirements", ""),
                        "bonus_points": sj.get("bonus_points", ""),
                        "keywords": sj.get("keywords", ""),
                    }
                    if job_db.insert_job(new_job):
                        stats["new_jobs"] += 1
                # 原记录标记已分析
                job_db.update_job_analysis(dedup_hash, jd_summary="(已拆分为具体岗位)")
                stats["analyzed"] += 1

            elif status == "parse_empty":
                upd = result["original_updated"]
                if upd:
                    job_db.update_job_analysis(dedup_hash, **upd)
                else:
                    job_db.update_job_analysis(dedup_hash)
                stats["parse_empty"] += 1
                stats["analyzed"] += 1

            elif status == "link_invalid":
                job_db.update_job_analysis(dedup_hash, link_valid=0)
                stats["link_invalid"] += 1
                stats["analyzed"] += 1

            elif status == "not_current_grade":
                job_db.update_job_analysis(dedup_hash, status="已关闭", link_valid=0)
                stats["not_current_grade"] += 1
                stats["analyzed"] += 1

            else:
                job_db.update_job_analysis(dedup_hash)
                stats[status] = stats.get(status, 0) + 1
                stats["analyzed"] += 1

        except Exception as e:
            logger.exception(f"分析岗位失败 [{job.get('company')}]: {e}")
            stats["errors"] += 1
            try:
                job_db.update_job_analysis(dedup_hash)
            except Exception:
                pass

        time.sleep(0.5)

    logger.info(f"分析完成: {stats}")
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    job_db.init_db()
    stats = run_analysis(batch_size=20)
    print(f"分析统计: {stats}")
