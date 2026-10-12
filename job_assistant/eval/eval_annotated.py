"""
标注后评测 — 读取人工标注结果，算出漏拆率/误拆率/归类准确率。

前置条件:
    你已完成 eval/evalset_positions_slim.json 的 annotation 字段标注。

评测指标:
1. 漏拆率 = 漏拆岗位总数 ÷ 实际岗位总数
2. 误拆率 = 误拆(幻觉)岗位数 ÷ LLM拆出岗位数
3. 拆岗数量准确率 = 拆对数量的样本 ÷ 总样本数
4. 归类准确率 = 归类正确的岗位 ÷ 总岗位数（基于标注的 category_errors）
5. 整体质量评分分布（1-5）
6. Bad case 分类统计

用法:
    cd /workspace/job_assistant
    python3 eval/eval_annotated.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALSET_PATH = ROOT / "eval" / "evalset_positions_slim.json"


def load_evalset():
    """加载标注后的评测集。"""
    if not EVALSET_PATH.exists():
        print(f"[错误] 评测集不存在: {EVALSET_PATH}")
        print("请先运行: python3 eval/sample_for_annotation.py")
        sys.exit(1)

    with open(EVALSET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def is_annotated(item):
    """检查一条样本是否已完成标注。"""
    ann = item.get("annotation", {})
    return ann.get("correct_position_count") is not None


def eval_split_accuracy(evalset):
    """维度1: 拆岗数量准确率 + 漏拆/误拆。"""
    annotated = [item for item in evalset if is_annotated(item)]
    total = len(annotated)
    if total == 0:
        return {"error": "没有已完成标注的样本，请先标注 evalset_positions_slim.json"}

    correct_count = 0
    under_split = 0
    over_split = 0
    total_missed = 0
    total_correct_positions = 0
    total_hallucinated = 0
    total_llm_positions = 0

    for item in annotated:
        ann = item["annotation"]
        llm_count = item["llm_position_count"]
        correct_c = ann.get("correct_position_count", 0)
        verdict = ann.get("split_verdict")
        missed = ann.get("missed_positions", [])
        hallucinated = ann.get("hallucinated_positions", [])

        total_correct_positions += correct_c
        total_missed += len(missed)
        total_hallucinated += len(hallucinated)
        total_llm_positions += llm_count

        if verdict == "correct":
            correct_count += 1
        elif verdict == "under_split":
            under_split += 1
        elif verdict == "over_split":
            over_split += 1

    return {
        "annotated_count": total,
        "split_correct": correct_count,
        "split_under": under_split,
        "split_over": over_split,
        "split_accuracy": f"{correct_count / total * 100:.1f}%" if total else "N/A",
        "under_split_rate": f"{under_split / total * 100:.1f}%" if total else "N/A",
        "total_correct_positions": total_correct_positions,
        "total_llm_positions": total_llm_positions,
        "total_missed": total_missed,
        "total_hallucinated": total_hallucinated,
        "miss_rate": f"{total_missed / total_correct_positions * 100:.1f}%" if total_correct_positions else "N/A",
        "hallucination_rate": f"{total_hallucinated / total_llm_positions * 100:.1f}%" if total_llm_positions else "N/A",
    }


def eval_category_accuracy(evalset):
    """维度2: 归类准确率。"""
    annotated = [item for item in evalset if is_annotated(item)]
    total_errors = 0
    total_positions = 0

    for item in annotated:
        ann = item["annotation"]
        errors = ann.get("category_errors", [])
        total_errors += len(errors)
        total_positions += item["llm_position_count"]

    correct = total_positions - total_errors
    return {
        "total_positions": total_positions,
        "category_errors": total_errors,
        "category_correct": correct,
        "category_accuracy": f"{correct / total_positions * 100:.1f}%" if total_positions else "N/A",
    }


def eval_field_accuracy(evalset):
    """维度3: 关键字段准确率。"""
    annotated = [item for item in evalset if is_annotated(item)]
    total_errors = 0
    error_fields = Counter()

    for item in annotated:
        ann = item["annotation"]
        errors = ann.get("field_errors", [])
        total_errors += len(errors)
        for e in errors:
            error_fields[e.get("field", "unknown")] += 1

    return {
        "total_field_errors": total_errors,
        "error_by_field": dict(error_fields.most_common()),
    }


def eval_score_distribution(evalset):
    """维度4: 整体质量评分分布。"""
    annotated = [item for item in evalset if is_annotated(item)]
    scores = [item["annotation"].get("overall_score") for item in annotated
              if item["annotation"].get("overall_score") is not None]

    if not scores:
        return {"error": "没有评分数据"}

    counter = Counter(scores)
    avg = sum(scores) / len(scores)
    return {
        "total_scored": len(scores),
        "avg_score": f"{avg:.2f}",
        "score_5": counter.get(5, 0),
        "score_4": counter.get(4, 0),
        "score_3": counter.get(3, 0),
        "score_2": counter.get(2, 0),
        "score_1": counter.get(1, 0),
        "pass_rate_ge4": f"{(counter.get(4, 0) + counter.get(5, 0)) / len(scores) * 100:.1f}%",
    }


def eval_badcase_distribution(evalset):
    """维度5: Bad case 分类统计。"""
    annotated = [item for item in evalset if is_annotated(item)]
    types = Counter()
    for item in annotated:
        bc = item["annotation"].get("bad_case_type")
        if bc:
            types[bc] += 1

    return {
        "total_annotated": len(annotated),
        "bad_case_distribution": dict(types.most_common()),
        "clean_rate": f"{(len(annotated) - types.get('none', 0)) / len(annotated) * 100:.1f}%" if annotated else "N/A",
    }


def run_eval():
    print("=" * 70)
    print("标注后评测 — 漏拆率/误拆率/准确率")
    print(f"评测集: {EVALSET_PATH}")
    print("=" * 70)

    evalset = load_evalset()
    annotated = [item for item in evalset if is_annotated(item)]
    print(f"\n[加载] 评测集 {len(evalset)} 条, 已标注 {len(annotated)} 条\n")

    if len(annotated) == 0:
        print("[提示] 还没有标注任何样本。")
        print("标注方法: 打开 eval/evalset_positions_slim.json")
        print("对每条样本填写 annotation 字段:")
        print("  correct_position_count: 实际应该拆几个岗位 (整数)")
        print("  split_verdict: correct/under_split/over_split")
        print("  missed_positions: [漏拆的岗位名列表]")
        print("  hallucinated_positions: [误拆的不存在岗位名列表]")
        print("  overall_score: 1-5 整体评分")
        print("  bad_case_type: none/missed/hallucinated/wrong_category/wrong_field")
        return

    print("-" * 70)
    print("【维度1】拆岗数量准确率 + 漏拆/误拆")
    r1 = eval_split_accuracy(evalset)
    for k, v in r1.items():
        print(f"  {k}: {v}")

    print("\n" + "-" * 70)
    print("【维度2】岗位归类准确率")
    r2 = eval_category_accuracy(evalset)
    for k, v in r2.items():
        print(f"  {k}: {v}")

    print("\n" + "-" * 70)
    print("【维度3】关键字段准确率")
    r3 = eval_field_accuracy(evalset)
    for k, v in r3.items():
        print(f"  {k}: {v}")

    print("\n" + "-" * 70)
    print("【维度4】整体质量评分分布")
    r4 = eval_score_distribution(evalset)
    for k, v in r4.items():
        print(f"  {k}: {v}")

    print("\n" + "-" * 70)
    print("【维度5】Bad case 分类统计")
    r5 = eval_badcase_distribution(evalset)
    for k, v in r5.items():
        print(f"  {k}: {v}")

    # 保存报告
    report = {
        "dimension_1_split": r1,
        "dimension_2_category": r2,
        "dimension_3_field": r3,
        "dimension_4_score": r4,
        "dimension_5_badcase": r5,
    }
    report_path = ROOT / "eval" / "annotated_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[报告已保存] {report_path}")


if __name__ == "__main__":
    run_eval()
