"""
岗位详情分析器 — 从飞书同步的"岗位大类"记录,抓取公告链接,
用 DeepSeek AI 解析出具体岗位列表,拆分为多条岗位记录。

核心价值:飞书表的"招聘岗位"字段是大类(如"研发类/销售类"),
用户需要的是具体岗位(如"Java开发工程师")。本模块负责这个转换。

流程:
1. 取 detail_analyzed=0 的岗位
2. 校验 announcement_url 有效性(HTTP 状态码)
3. 抓取公告正文
4. 校验是否本届校招(正文含"2027届"/"27届"等关键词,或无明确届数限制)
5. DeepSeek 解析具体岗位列表
6. 拆分为多条 job 记录入库,原记录标记已分析
"""
import logging
import re
import time
from typing import List, Dict

import requests

from llm_client import LLMClient
from collector import fetch_jd_by_source
import job_db

logger = logging.getLogger(__name__)

# 本届校招关键词(用于校验公告是否面向本届)
CURRENT_GRADE_KEYWORDS = [
    "2027届", "27届", "2027校园招聘", "2027校招",
    "2026届", "26届",  # 26届也可能可投(如春招补招面向26-27届)
]

# 非校招关键词(命中则排除)
NON_CAMPUS_KEYWORDS = [
    "社会招聘", "社招", "社会招聘", "experienced",
]


def check_link_valid(url: str, timeout: int = 10) -> bool:
    """检查链接是否有效(HTTP 200 或 3xx 跳转后 200)"""
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
        # HEAD 可能被拒,降级为 GET 检测
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
            return resp.status_code == 200
        except Exception:
            return False


def is_current_grade(text: str) -> bool:
    """校验公告正文是否面向本届校招(含 26/27 届关键词,或无明确届数限制)"""
    if not text:
        return False
    # 命中非校招关键词
    if any(kw in text for kw in NON_CAMPUS_KEYWORDS):
        # 但若同时有校招关键词,仍视为校招
        if not any(kw in text for kw in CURRENT_GRADE_KEYWORDS):
            return False
    # 有本届关键词 或 无明确届数限制(含"校招""校园招聘"等)
    campus_indicators = ["校招", "校园招聘", "应届", "毕业生", "应届生", "2027", "2026"]
    if any(kw in text for kw in campus_indicators):
        return True
    # 没有任何届数信息,保守起见视为有效(不排除)
    return True


def analyze_one_job(job: Dict, llm: LLMClient) -> Dict:
    """
    分析单条岗位(从公告解析具体岗位)。

    返回: {
        "status": "success" | "no_url" | "link_invalid" | "fetch_failed" | "not_current_grade" | "parse_empty",
        "specific_jobs": [...],   # 解析出的具体岗位列表
        "original_updated": {...} # 原记录需更新的字段
    }
    """
    url = job.get("announcement_url") or job.get("apply_url") or ""
    if not url:
        return {"status": "no_url", "specific_jobs": [], "original_updated": {}}

    # 链接有效性校验
    if not check_link_valid(url):
        return {"status": "link_invalid", "specific_jobs": [], "original_updated": {"link_valid": 0}}

    # 抓取公告正文
    text = fetch_jd_by_source(url, timeout=20)
    if not text or len(text.strip()) < 50:
        return {"status": "fetch_failed", "specific_jobs": [], "original_updated": {}}

    # 本届校验
    if not is_current_grade(text):
        return {"status": "not_current_grade", "specific_jobs": [], "original_updated": {"status": "已关闭"}}

    # AI 解析具体岗位
    specific_jobs = llm.parse_announcement_jobs(text, job.get("company", ""))
    if not specific_jobs:
        # 解析为空,降级:用原大类作为岗位标题,补全摘要
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

    返回统计: {"analyzed": N, "split_into": M, "link_invalid": N, ...}
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
                    }
                    if job_db.insert_job(new_job):
                        stats["new_jobs"] += 1
                # 原记录标记已分析(不再展示大类岗位)
                job_db.update_job_analysis(dedup_hash, jd_summary="(已拆分为具体岗位)")
                stats["analyzed"] += 1

            elif status == "parse_empty":
                # 解析失败,用摘要更新原记录
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

            else:  # no_url / fetch_failed
                job_db.update_job_analysis(dedup_hash)
                stats[status] = stats.get(status, 0) + 1
                stats["analyzed"] += 1

        except Exception as e:
            logger.exception(f"分析岗位失败 [{job.get('company')}]: {e}")
            stats["errors"] += 1
            # 标记已分析,避免重复处理
            try:
                job_db.update_job_analysis(dedup_hash)
            except Exception:
                pass

        time.sleep(0.5)  # 控制请求频率

    logger.info(f"分析完成: {stats}")
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    job_db.init_db()
    stats = run_analysis(batch_size=20)
    print(f"分析统计: {stats}")
