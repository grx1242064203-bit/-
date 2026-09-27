"""
阶段二(守护模式):持续消费 fetch_results.jsonl,与阶段一(抓取)并行运行。

与 analyze_announcements.py 的区别:
- analyze_announcements.py: 一次性读取全部 JSONL 后分析(适用于抓取已完成)
- 本脚本: tail -f 模式持续读取新行,边抓取边分析

运行: python3 analyze_daemon.py
停止: 阶段一结束 + 60s 无新记录后自动退出
"""
import os
import sys
import json
import time
import logging
import sqlite3
from typing import Dict

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
DB_PATH = "/workspace/job_assistant/data/jobs.db"
IDLE_TIMEOUT = 120  # 无新记录且阶段一已结束时,等待多久后退出(秒)
POLL_INTERVAL = 2  # 轮询新记录的间隔(秒)


def load_analyzed_hashes() -> set:
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT dedup_hash FROM jobs WHERE detail_analyzed = 1"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def build_original_job_map() -> Dict[str, Dict]:
    conn = sqlite3.connect(DB_PATH)
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


def is_fetch_process_running() -> bool:
    """检查阶段一(抓取)是否还在运行"""
    import subprocess
    try:
        out = subprocess.run(
            ["pgrep", "-f", "fetch_announcements.py"],
            capture_output=True, text=True, timeout=5,
        )
        return out.returncode == 0 and bool(out.stdout.strip())
    except Exception:
        return False


def analyze_one(rec: Dict, llm: LLMClient, original: Dict) -> Dict:
    dedup_hash = rec["dedup_hash"]
    status = rec.get("status", "fetch_failed")
    text = rec.get("text", "")
    images = rec.get("images", [])
    company = rec.get("company", "")

    stats = {"new_jobs": 0, "parse_empty": 0, "not_current_grade": 0,
             "fetch_failed": 0, "link_invalid": 0, "no_url": 0, "blocked": 0}

    if status in ("link_invalid", "no_url", "blocked", "fetch_failed"):
        if status == "link_invalid":
            job_db.update_job_analysis(dedup_hash, link_valid=0)
        else:
            job_db.update_job_analysis(dedup_hash)
        stats[status] = stats.get(status, 0) + 1
        return stats

    if len(text.strip()) < 50 and images:
        logger.info(f"文字不足({len(text)}字),VL分析 {len(images)} 张图 [{company}]")
        image_text = analyze_images_with_vl(images, llm)
        if image_text:
            text = (text + "\n" + image_text).strip()

    if not text or len(text.strip()) < 30:
        job_db.update_job_analysis(dedup_hash)
        stats["fetch_failed"] += 1
        return stats

    if not is_current_grade(text):
        job_db.update_job_analysis(dedup_hash, status="已关闭", link_valid=0)
        stats["not_current_grade"] += 1
        return stats

    specific_jobs = llm.parse_announcement_jobs_enhanced(text, company)
    if not specific_jobs:
        specific_jobs = llm.parse_announcement_jobs(text, company)

    if not specific_jobs:
        summary = llm.generate_jd_summary(text, original.get("job_title", ""))
        job_db.update_job_analysis(dedup_hash, jd_summary=summary)
        stats["parse_empty"] += 1
        return stats

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

    job_db.update_job_analysis(dedup_hash, jd_summary="(已拆分为具体岗位)")
    return stats


def tail_jsonl(path, analyzed_hashes: set):
    """
    生成器:持续读取 JSONL 文件,逐行 yield 新记录(已跳过已分析的)。
    处理半行:JSON 解析失败时跳过(下次轮询重试)。
    """
    # 先定位到文件末尾,但需要先处理已有的未分析记录
    # 策略:从头扫描,跳过已分析的,然后持续 tail
    with open(path, "r", encoding="utf-8") as f:
        # 第一遍:读取所有已有行
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                h = rec.get("dedup_hash")
                if h and h not in analyzed_hashes:
                    yield rec
                    analyzed_hashes.add(h)
            except json.JSONDecodeError:
                continue  # 半行,跳过

        # 持续 tail
        last_no_new = time.time()
        while True:
            line = f.readline()
            if line:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    h = rec.get("dedup_hash")
                    if h and h not in analyzed_hashes:
                        yield rec
                        analyzed_hashes.add(h)
                        last_no_new = time.time()
                except json.JSONDecodeError:
                    # 可能是半行,稍后重试
                    f.seek(f.tell() - len(line))
                    time.sleep(POLL_INTERVAL)
                    continue
            else:
                # 没有新行,检查是否该退出
                if not is_fetch_process_running():
                    # 阶段一已结束,等待 IDLE_TIMEOUT 确认无新记录
                    if time.time() - last_no_new > IDLE_TIMEOUT:
                        logger.info("阶段一已结束且无新记录,分析守护进程退出")
                        return
                time.sleep(POLL_INTERVAL)


def main():
    logger.info("=" * 60)
    logger.info("阶段二(守护模式)启动:与抓取并行,持续消费新记录")
    logger.info("=" * 60)

    llm = LLMClient()

    # 加载已分析 hash
    analyzed_hashes = load_analyzed_hashes()
    logger.info(f"已分析记录数: {len(analyzed_hashes)}")

    # 构建原始岗位映射(每 100 条刷新一次,因为阶段一不写 DB,映射基本不变)
    original_map = build_original_job_map()
    logger.info(f"DB 岗位记录数: {len(original_map)}")

    total_stats = {"new_jobs": 0, "parse_empty": 0, "not_current_grade": 0,
                   "fetch_failed": 0, "link_invalid": 0, "no_url": 0, "blocked": 0}
    processed = 0
    start = time.time()

    for rec in tail_jsonl(FETCH_RESULTS_PATH, analyzed_hashes):
        h = rec.get("dedup_hash", "")
        original = original_map.get(h, {})
        try:
            stats = analyze_one(rec, llm, original)
            for k, v in stats.items():
                total_stats[k] = total_stats.get(k, 0) + v
            processed += 1
        except Exception as e:
            logger.exception(f"分析失败 [{rec.get('company','')}]: {e}")
            try:
                job_db.update_job_analysis(h)
            except Exception:
                pass

        if processed % 5 == 0:
            elapsed = time.time() - start
            rate = processed / elapsed if elapsed > 0 else 0
            logger.info(f"已分析 {processed} 条 ({rate:.2f}条/秒) stats={total_stats}")

    elapsed = time.time() - start
    logger.info("=" * 60)
    logger.info(f"分析守护进程结束: 共分析 {processed} 条, 耗时 {elapsed:.1f}s")
    logger.info(f"统计: {total_stats}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
