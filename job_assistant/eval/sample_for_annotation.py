"""
评测集抽样 — 从 498 条拆岗结果中分层抽样 25 条，生成人工标注模板。

分层维度:
  A. 单岗位公告（验证基础抽取能力）        5 条
  B. 多岗位公告 2-10 岗（核心场景）       10 条
  C. 超多岗位公告 10-25 岗（压力测试）     5 条
  D. 异常值 25+ 岗（误拆检测）             2 条
  E. 管培生公告（边界场景）                 3 条

用法:
    cd /workspace/job_assistant
    DATA_DIR=./data python3 eval/sample_for_annotation.py
"""
import json
import os
import sys
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LLM_CACHE_DIR = ROOT / "data" / "llm_cache"
CRAWL_CACHE_DIR = ROOT / "data" / "crawl_cache"
OUTPUT_DIR = ROOT / "eval"

# 可复现的随机种子
SEED = 42


def load_all_by_file():
    """按 source_file 分组加载所有拆岗结果。"""
    by_file = defaultdict(list)
    for f in sorted(LLM_CACHE_DIR.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                if isinstance(data, list):
                    for item in data:
                        by_file[f.name].append(item)
        except Exception:
            continue
    return by_file


import sqlite3

_DB_CACHE = {}


def find_crawl_content(source_filename):
    """通过 llm_cache_hash 从 jobs.db 反查公告正文和元数据。

    llm_cache 文件名 = content+company+title 的 md5
    jobs.db.announcements.llm_cache_hash 存的就是这个 hash
    """
    cache_hash = source_filename.replace(".json", "")
    if cache_hash in _DB_CACHE:
        return _DB_CACHE[cache_hash]

    db_path = ROOT / "data" / "jobs.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT company_name, announcement_title, content, recruit_type, "
            "location, education_req FROM announcements WHERE llm_cache_hash=?",
            (cache_hash,)
        ).fetchone()
        if row:
            content = row["content"] or ""
            excerpt = content[:2000] if len(content) > 2000 else content
            result = (
                f"[公司] {row['company_name']}\n"
                f"[标题] {row['announcement_title']}\n"
                f"[招聘类型] {row['recruit_type']}\n"
                f"[地点] {row['location']}\n"
                f"[学历] {row['education_req']}\n"
                f"[正文]\n{excerpt}"
            )
        else:
            result = "[数据库中未找到对应公告]"
    except Exception as e:
        result = f"[查询失败: {e}]"
    finally:
        conn.close()

    _DB_CACHE[cache_hash] = result
    return result


def stratified_sample(by_file):
    """分层抽样。"""
    random.seed(SEED)

    # 按拆岗数量分层
    buckets = {
        "A_single": [],      # 1 岗
        "B_multi": [],      # 2-10 岗
        "C_heavy": [],      # 10-25 岗
        "D_outlier": [],    # 25+ 岗
        "E_mt": [],         # 含管培生
    }

    for fname, jobs in by_file.items():
        n = len(jobs)
        has_mt = any(j.get("is_management_trainee") for j in jobs)

        if has_mt:
            buckets["E_mt"].append((fname, jobs))
        if n == 1:
            buckets["A_single"].append((fname, jobs))
        elif n <= 10:
            buckets["B_multi"].append((fname, jobs))
        elif n <= 25:
            buckets["C_heavy"].append((fname, jobs))
        else:
            buckets["D_outlier"].append((fname, jobs))

    # 各层抽样数量
    quota = {
        "A_single": 5,
        "B_multi": 10,
        "C_heavy": 5,
        "D_outlier": 2,
        "E_mt": 3,
    }

    samples = []
    for bucket_name, count in quota.items():
        pool = buckets.get(bucket_name, [])
        actual = min(count, len(pool))
        if actual > 0:
            picked = random.sample(pool, actual)
            for fname, jobs in picked:
                samples.append({
                    "bucket": bucket_name,
                    "source_file": fname,
                    "llm_position_count": len(jobs),
                    "llm_positions": jobs,
                    "crawl_content_excerpt": find_crawl_content(fname),
                })

    return samples, buckets


def generate_annotation_template(samples):
    """生成人工标注模板。"""
    evalset = []
    for i, s in enumerate(samples, 1):
        eval_item = {
            "id": f"EVAL-{i:03d}",
            "bucket": s["bucket"],
            "source_file": s["source_file"],
            "llm_position_count": s["llm_position_count"],
            "crawl_content_excerpt": s["crawl_content_excerpt"][:1500],

            # ===== 人工标注字段 =====
            "annotation": {
                # 1. 拆岗数量对错
                "correct_position_count": None,  # 实际应该拆几个
                "split_verdict": None,  # correct / under_split / over_split
                # 2. 漏拆的岗位名（应拆但没拆）
                "missed_positions": [],
                # 3. 误拆的岗位名（不该拆但拆了，幻觉）
                "hallucinated_positions": [],
                # 4. 岗位归类对错
                "category_errors": [],  # [{"position_title":"X","wrong_category":"Y","correct_category":"Z"}]
                # 5. 关键字段错误
                "field_errors": [],     # [{"position_title":"X","field":"city","wrong":"A","correct":"B"}]
                # 6. 整体质量评分（1-5）
                "overall_score": None,  # 1=完全错误 5=完美
                # 7. bad case 分类
                "bad_case_type": None,  # none / missed / hallucinated / wrong_category / wrong_field / format
                # 8. 备注
                "notes": "",
            },

            "llm_positions": s["llm_positions"],
        }
        evalset.append(eval_item)
    return evalset


def main():
    print("=" * 70)
    print("评测集抽样 — 分层抽样 25 条")
    print("=" * 70)

    by_file = load_all_by_file()
    print(f"[加载] {len(by_file)} 条公告\n")

    samples, buckets = stratified_sample(by_file)

    print("各分层统计:")
    for name, items in buckets.items():
        print(f"  {name}: 池子 {len(items)} 条, 抽样 {min(int({'A_single':5,'B_multi':10,'C_heavy':5,'D_outlier':2,'E_mt':3}[name]), len(items))} 条")

    print(f"\n实际抽样: {len(samples)} 条")

    evalset = generate_annotation_template(samples)

    output_path = OUTPUT_DIR / "evalset_positions.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(evalset, f, ensure_ascii=False, indent=2)

    print(f"\n[评测集已保存] {output_path}")
    print(f"\n下一步: 人工标注 {len(evalset)} 条样本")
    print(f"标注方法: 打开 evalset_positions.json，填写每个 item 的 annotation 字段")
    print(f"标注维度: 拆岗数量对错 / 漏拆 / 误拆 / 归类错误 / 字段错误 / 整体评分")

    # 同时输出一份精简版（只含标注字段，不含 LLM 原始输出，方便人工标注时对照原文）
    slim_path = OUTPUT_DIR / "evalset_positions_slim.json"
    slim = []
    for item in evalset:
        slim.append({
            "id": item["id"],
            "bucket": item["bucket"],
            "source_file": item["source_file"],
            "llm_position_count": item["llm_position_count"],
            "llm_position_titles": [p.get("position_title", "") for p in item["llm_positions"]],
            "llm_categories": [(p.get("job_category", ""), p.get("job_subcategory", "")) for p in item["llm_positions"]],
            "crawl_content_excerpt": item["crawl_content_excerpt"],
            "annotation": item["annotation"],
        })
    with open(slim_path, "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, indent=2)
    print(f"[精简版已保存] {slim_path}")


if __name__ == "__main__":
    main()
