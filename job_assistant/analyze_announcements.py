"""
阶段二:批量分析已抓取的公告内容,写入数据库。

读取 fetch_results.jsonl,对每条记录:
1. 若文字不足且有图片 → DeepSeek-VL 做图片 OCR
2. 本届校招校验
3. LLM 解析具体岗位(25+ 维度)
4. 新岗位入库 + 原记录标记已分析

支持断点续传:跳过 DB 中已 detail_analyzed=1 的 dedup_hash。

运行: python3 analyze_announcements.py [--limit 200]
"""
import os
import sys
import json
import time
import logging
import argparse
from typing import Dict, List

os.environ.setdefault("DATA_DIR", "/workspace/job_assistant/data")
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-b62b83d5c36d4e6aa87925c8b66b4ab3")
sys.path.insert(0, "/workspace/job_assistant")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("/workspace/job_assistant/analyze_announcements.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

import job_db
job_db.init_db()
from llm_client import LLMClient
from job_detail_analyzer import analyze_images_with_vl, is_current_grade

FETCH_RESULTS_PATH = "/workspace/job_assistant/fetch_results.jsonl"


def load_analyzed_hashes() -> set:
    """加载 DB 中已分析的 dedup_hash 集合(断点续传)"""
    import sqlite3
    conn = sqlite3.connect("/workspace/job_assistant/data/jobs.db")
    try:
        rows = conn.execute(
            "SELECT dedup_hash FROM jobs WHERE detail_analyzed = 1"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def load_fetch_results() -> List[Dict]:
    """加载所有抓取结果"""
    results = []
    if not os.path.exists(FETCH_RESULTS_PATH):
        return results
    with open(FETCH_RESULTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except Exception:
                continue
    return results


def build_original_job_map() -> Dict[str, Dict]:
    """从 DB 构建 dedup_hash -> 原始岗位记录 的映射"""
    import sqlite3
    conn = sqlite3.connect("/workspace/job_assistant/data/jobs.db")
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM jobs").fetchall()
        m = {}
        for r in rows:
            d = dict(r)
            h = job_db.compute_dedup_hash(
                d["company"], d["job_title"], d.get("apply_url", "")
            )
            m[h] = d
        return m
    finally:
        conn.close()


def analyze_one(rec: Dict, llm: LLMClient, original: Dict) -> Dict:
    """
    分析单条抓取结果,返回统计信息。
    """
    dedup_hash = rec["dedup_hash"]
    status = rec.get("status", "fetch_failed")
    text = rec.get("text", "")
    images = rec.get("images", [])
    company = rec.get("company", "")

    stats = {"new_jobs": 0, "parse_empty": 0, "not_current_grade": 0,
             "fetch_failed": 0, "link_invalid": 0, "no_url": 0, "blocked": 0}

    # 抓取阶段已失败的,直接标记
    if status in ("link_invalid", "no_url", "blocked", "fetch_failed"):
        if status == "link_invalid":
            job_db.update_job_analysis(dedup_hash, link_valid=0)
        elif status == "not_current_grade":
            job_db.update_job_analysis(dedup_hash, status="已关闭", link_valid=0)
        else:
            job_db.update_job_analysis(dedup_hash)
        stats[status] = stats.get(status, 0) + 1
        return stats

    # 文字不足但有图片 → VL OCR
    if len(text.strip()) < 50 and images:
        logger.info(f"文字不足({len(text)}字),VL 分析 {len(images)} 张图 [{company}]")
        image_text = analyze_images_with_vl(images, llm)
        if image_text:
            text = (text + "\n" + image_text).strip()

    if not text or len(text.strip()) < 30:
        job_db.update_job_analysis(dedup_hash)
        stats["fetch_failed"] += 1
        return stats

    # 本届校验
    if not is_current_grade(text):
        job_db.update_job_analysis(dedup_hash, status="已关闭", link_valid=0)
        stats["not_current_grade"] += 1
        return stats

    # LLM 解析具体岗位(增强版 25+ 维度)
    specific_jobs = llm.parse_announcement_jobs_enhanced(text, company)
    if not specific_jobs:
        specific_jobs = llm.parse_announcement_jobs(text, company)

    if not specific_jobs:
        summary = llm.generate_jd_summary(text, original.get("job_title", ""))
        job_db.update_job_analysis(dedup_hash, jd_summary=summary)
        stats["parse_empty"] += 1
        return stats

    # 拆分:为每个具体岗位创建新记录
    for sj in specific_jobs:
        new_job = {
            "company": original.get("company", company),
            "job_title": sj["job_title"],
            "department": sj.get("department", ""),
            "salary": sj.get("salary", ""),
            "education": sj.get("education", "") or original.get("education", ""),
            "locations": sj.get("locations", "") or original.get("locations", ""),
            "industry": original.get("industry", ""),
            "company_type": original.get("company_type", ""),
            "difficulty": original.get("difficulty", ""),
            "recruitment_stage": original.get("recruitment_stage", ""),
            "target_min_grade": original.get("target_min_grade"),
            "target_max_grade": original.get("target_max_grade"),
            "apply_url": original.get("apply_url", ""),
            "announcement_url": original.get("announcement_url", ""),
            "jd_summary": sj.get("jd_summary", ""),
            "publish_time": original.get("publish_time", ""),
            "deadline": original.get("deadline", ""),
            "is_fresh_graduate": sj.get("is_fresh_graduate", True),
            "mt_program": sj.get("mt_program", False),
            "source": original.get("source", "feishu"),
            "link_valid": 1,
            "detail_analyzed": True,
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
    return stats


def run_once(limit: int = 0) -> Dict:
    """执行一轮分析,返回统计"""
    llm = LLMClient()

    all_results = load_fetch_results()
    if not all_results:
        logger.info("没有抓取结果,跳过本轮")
        return {}

    analyzed = load_analyzed_hashes()
    original_map = build_original_job_map()

    todo = [r for r in all_results if r.get("dedup_hash") not in analyzed]
    if limit > 0:
        todo = todo[:limit]

    logger.info(f"本轮待分析: {len(todo)} 条 (抓取结果 {len(all_results)}, 已分析 {len(analyzed)})")

    if not todo:
        return {}

    total_stats = {"new_jobs": 0, "parse_empty": 0, "not_current_grade": 0,
                   "fetch_failed": 0, "link_invalid": 0, "no_url": 0, "blocked": 0}
    start = time.time()

    for i, rec in enumerate(todo, 1):
        h = rec.get("dedup_hash", "")
        original = original_map.get(h, {})
        try:
            stats = analyze_one(rec, llm, original)
            for k, v in stats.items():
                total_stats[k] = total_stats.get(k, 0) + v
        except Exception as e:
            logger.exception(f"分析失败 [{rec.get('company','')}]: {e}")
            try:
                job_db.update_job_analysis(h)
            except Exception:
                pass

        if i % 10 == 0:
            elapsed = time.time() - start
            rate = i / elapsed if elapsed > 0 else 0
            logger.info(f"进度 {i}/{len(todo)} ({rate:.2f}条/秒) stats={total_stats}")

    elapsed = time.time() - start
    rate = len(todo) / elapsed if elapsed > 0 else 0
    logger.info(f"本轮完成: {len(todo)} 条, 耗时 {elapsed:.1f}s ({rate:.2f}条/秒), stats={total_stats}")
    return total_stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="本次最多分析条数(0=不限制)")
    parser.add_argument("--watch", action="store_true",
                        help="持续监听模式:循环分析新抓取的记录,直到抓取结束")
    parser.add_argument("--interval", type=int, default=30,
                        help="watch 模式下每轮间隔秒数")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(f"阶段二:公告分析启动 (watch={args.watch})")
    logger.info("=" * 60)

    if not args.watch:
        run_once(limit=args.limit)
        return

    # watch 模式:持续循环
    round_num = 0
    idle_rounds = 0
    while True:
        round_num += 1
        logger.info(f"\n--- watch 第 {round_num} 轮 ---")

        stats = run_once(limit=args.limit)

        if not stats:
            idle_rounds += 1
            logger.info(f"本轮无新记录 (连续空转 {idle_rounds} 轮)")
        else:
            idle_rounds = 0

        # 检查抓取阶段是否已结束:若 fetch_results.jsonl 行数 2 分钟未增长,认为抓取结束
        if idle_rounds >= 3:
            logger.info("连续 3 轮无新记录,抓取可能已结束,退出 watch 模式")
            break

        time.sleep(args.interval)

    logger.info("watch 模式结束")


if __name__ == "__main__":
    main()
