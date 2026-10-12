"""
拆岗效果基线评测 — 程序硬指标层（无需 LLM API）。

评测维度:
1. JSON 合法率（输出格式合规性）
2. 字段填充率（关键字段非空率）
3. 岗位树命中率（job_category/job_subcategory 是否在受控词表内）
4. 拆岗数量分布（每公告平均拆几个岗位，异常值检测）
5. 枚举字段值分布（difficulty/company_tier/min_education 等是否合理）
6. 幻觉代理指标（position_title 为空 / job_category 为自造词）

用法:
    cd /workspace/job_assistant
    python3 eval/baseline_eval.py
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import job_tree

LLM_CACHE_DIR = ROOT / "data" / "llm_cache"


def load_all_results():
    """加载所有 LLM 拆岗缓存结果。"""
    results = []
    for f in sorted(LLM_CACHE_DIR.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                if isinstance(data, list):
                    for item in data:
                        item["_source_file"] = f.name
                        results.append(item)
                elif isinstance(data, dict):
                    data["_source_file"] = f.name
                    results.append(data)
        except (json.JSONDecodeError, Exception) as e:
            results.append({"_source_file": f.name, "_parse_error": str(e)})
    return results


def eval_json_validity(results):
    """维度1: JSON 合法率。"""
    total = len(results)
    errors = [r for r in results if "_parse_error" in r]
    valid = total - len(errors)
    rate = valid / total * 100 if total else 0
    return {
        "total_files": total,
        "valid_json": valid,
        "parse_errors": len(errors),
        "json_validity_rate": f"{rate:.1f}%",
    }


def eval_field_fill_rate(results):
    """维度2: 字段填充率（关键字段非空率）。"""
    # 关键字段定义
    key_fields = [
        "position_title", "job_category", "job_subcategory",
        "hard_skills", "soft_skills", "major_required", "major_category",
        "min_education", "city", "responsibilities", "requirements",
        "keywords", "jd_summary", "difficulty", "company_tier",
        "is_management_trainee", "apply_url",
    ]
    valid_results = [r for r in results if "_parse_error" not in r]
    total = len(valid_results)

    fill_stats = {}
    for field in key_fields:
        filled = 0
        for r in valid_results:
            val = r.get(field)
            if isinstance(val, list):
                if len(val) > 0:
                    filled += 1
            elif isinstance(val, bool):
                filled += 1  # bool 字段总有值
            elif val:  # 非空字符串
                filled += 1
        rate = filled / total * 100 if total else 0
        fill_stats[field] = {
            "filled": filled,
            "total": total,
            "fill_rate": f"{rate:.1f}%",
        }
    return fill_stats


def eval_tree_hit_rate(results):
    """维度3: 岗位树命中率。"""
    valid_results = [r for r in results if "_parse_error" not in r]
    all_cats = set(job_tree.all_category_names())
    all_subs = set(job_tree.all_subcategory_names())

    cat_hit = 0
    sub_hit = 0
    sub_is_cat = 0  # 子类填了大类名（允许但降级）
    cat_miss = 0
    sub_miss = 0  # 子类是自造词（不在树里）
    empty_cat = 0
    empty_sub = 0

    for r in valid_results:
        cat = (r.get("job_category") or "").strip()
        sub = (r.get("job_subcategory") or "").strip()

        if not cat:
            empty_cat += 1
        elif cat in all_cats:
            cat_hit += 1
        else:
            cat_miss += 1

        if not sub:
            empty_sub += 1
        elif sub in all_subs:
            sub_hit += 1
        elif sub in all_cats:
            sub_is_cat += 1  # 填了大类名，允许
        else:
            sub_miss += 1  # 自造词

    total = len(valid_results)
    return {
        "total": total,
        "category_hit": cat_hit,
        "category_miss_self_coined": cat_miss,
        "category_empty": empty_cat,
        "category_hit_rate": f"{cat_hit / total * 100:.1f}%" if total else "N/A",
        "subcategory_hit": sub_hit,
        "subcategory_is_category": sub_is_cat,
        "subcategory_miss_self_coined": sub_miss,
        "subcategory_empty": empty_sub,
        "subcategory_valid_rate": f"{(sub_hit + sub_is_cat) / total * 100:.1f}%" if total else "N/A",
        "self_coined_examples": list({
            r.get("job_subcategory") for r in valid_results
            if r.get("job_subcategory", "").strip()
            and r.get("job_subcategory", "").strip() not in all_subs
            and r.get("job_subcategory", "").strip() not in all_cats
        })[:15],
    }


def eval_split_count_distribution(results):
    """维度4: 每公告拆岗数量分布。"""
    # 按 source_file 分组
    from collections import defaultdict
    by_file = defaultdict(list)
    for r in results:
        if "_parse_error" not in r:
            by_file[r.get("_source_file", "unknown")].append(r)

    counts = [len(jobs) for jobs in by_file.values()]
    if not counts:
        return {"error": "no data"}

    counter = Counter(counts)
    return {
        "total_announcements": len(counts),
        "total_positions": sum(counts),
        "avg_positions_per_announcement": f"{sum(counts) / len(counts):.2f}",
        "max_positions": max(counts),
        "min_positions": min(counts),
        "distribution": {str(k): v for k, v in sorted(counter.items())},
        "single_position_announcements": counter.get(1, 0),
        "single_position_rate": f"{counter.get(1, 0) / len(counts) * 100:.1f}%",
    }


def eval_enum_distribution(results):
    """维度5: 枚举字段值分布（检测是否过度集中）。"""
    valid_results = [r for r in results if "_parse_error" not in r]

    def dist(field):
        c = Counter(r.get(field, "") for r in valid_results if r.get(field))
        return dict(c.most_common(10))

    return {
        "difficulty": dist("difficulty"),
        "company_tier": dist("company_tier"),
        "min_education": dist("min_education"),
        "major_category": dist("major_category"),
    }


def eval_hallusion_proxy(results):
    """维度6: 幻觉代理指标（position_title 空 / 极短 / 岗位名不在公告里）。"""
    valid_results = [r for r in results if "_parse_error" not in r]
    total = len(valid_results)

    empty_title = sum(1 for r in valid_results if not r.get("position_title", "").strip())
    short_title = sum(1 for r in valid_results if 0 < len(r.get("position_title", "").strip()) <= 2)
    is_mt = sum(1 for r in valid_results if r.get("is_management_trainee") is True)

    return {
        "total": total,
        "empty_position_title": empty_title,
        "empty_title_rate": f"{empty_title / total * 100:.1f}%" if total else "N/A",
        "ultra_short_title_2char": short_title,
        "management_trainee_count": is_mt,
        "mt_rate": f"{is_mt / total * 100:.1f}%" if total else "N/A",
    }


def run_baseline():
    """跑全部基线评测。"""
    print("=" * 70)
    print("拆岗效果基线评测 — 程序硬指标层")
    print(f"数据源: {LLM_CACHE_DIR}")
    print("=" * 70)

    results = load_all_results()
    print(f"\n[加载] 共 {len(results)} 条岗位记录\n")

    print("-" * 70)
    print("【维度1】JSON 合法率")
    r1 = eval_json_validity(results)
    for k, v in r1.items():
        print(f"  {k}: {v}")

    print("\n" + "-" * 70)
    print("【维度2】字段填充率")
    r2 = eval_field_fill_rate(results)
    # 按填充率排序
    sorted_fields = sorted(r2.items(), key=lambda x: float(x[1]["fill_rate"].rstrip("%")))
    print(f"  {'字段':<25} {'已填':>6} / {'总数':>6}  填充率")
    for field, stats in sorted_fields:
        print(f"  {field:<25} {stats['filled']:>5} / {stats['total']:>5}  {stats['fill_rate']}")

    print("\n" + "-" * 70)
    print("【维度3】岗位树命中率（受控词表约束）")
    r3 = eval_tree_hit_rate(results)
    for k, v in r3.items():
        if k == "self_coined_examples":
            print(f"  自造子类示例: {v}")
        else:
            print(f"  {k}: {v}")

    print("\n" + "-" * 70)
    print("【维度4】拆岗数量分布")
    r4 = eval_split_count_distribution(results)
    for k, v in r4.items():
        print(f"  {k}: {v}")

    print("\n" + "-" * 70)
    print("【维度5】枚举字段值分布")
    r5 = eval_enum_distribution(results)
    for field, dist in r5.items():
        print(f"  {field}:")
        for val, cnt in dist.items():
            print(f"    {val}: {cnt}")

    print("\n" + "-" * 70)
    print("【维度6】幻觉代理指标")
    r6 = eval_hallusion_proxy(results)
    for k, v in r6.items():
        print(f"  {k}: {v}")

    # 保存完整结果
    report = {
        "dimension_1_json_validity": r1,
        "dimension_2_field_fill_rate": r2,
        "dimension_3_tree_hit_rate": r3,
        "dimension_4_split_count": r4,
        "dimension_5_enum_distribution": r5,
        "dimension_6_hallusion_proxy": r6,
    }
    report_path = ROOT / "eval" / "baseline_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[报告已保存] {report_path}")

    return report


if __name__ == "__main__":
    run_baseline()
