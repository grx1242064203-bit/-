"""v2 Prompt 回归测试：从数据库读原始公告，用 v2 prompt 重新跑 25 条，对比 v1 vs v2。"""
import json
import os
import sys
import sqlite3
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 设置 API Key + DATA_DIR
os.environ["DEEPSEEK_API_KEY"] = "sk-b62b83d5c36d4e6aa87925c8b66b4ab3"
os.environ["DATA_DIR"] = str(PROJECT_ROOT / "data")

from llm_enricher import PositionEnricher, _content_hash, LLM_CACHE_DIR
from llm_client import LLMClient

# Monkey-patch: 绕过 v1 缓存，强制重新调用 LLM，结果存到 v2_cache
import llm_enricher as _le
_v2_cache_dir = os.path.join(PROJECT_ROOT, "eval", "v2_cache")
os.makedirs(_v2_cache_dir, exist_ok=True)

def _v2_get_cached(content_hash):
    path = os.path.join(_v2_cache_dir, f"{content_hash}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None  # 不读 v1 缓存

def _v2_save(content_hash, positions):
    path = os.path.join(_v2_cache_dir, f"{content_hash}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(positions, f, ensure_ascii=False)

_le._get_cached_llm_result = _v2_get_cached
_le._save_llm_result = _v2_save

EVALSET_PATH = Path(__file__).resolve().parent / "evalset_positions.json"
V2_CACHE_DIR = os.path.join(PROJECT_ROOT, "eval", "v2_cache")
V2_RESULTS_PATH = Path(__file__).resolve().parent / "v2_llm_results.json"
V2_REPORT_PATH = Path(__file__).resolve().parent / "v2_report.json"
DB_PATH = PROJECT_ROOT / "data" / "jobs.db"


def run_v2_on_evalset():
    """在 25 条评测集上跑 v2 LLM 拆岗。"""
    with open(EVALSET_PATH, "r", encoding="utf-8") as f:
        evalset = json.load(f)

    # 从数据库读所有公告，建立 cache_hash → announcement 映射
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM announcements WHERE llm_cache_hash IS NOT NULL")
    ann_map = {}
    for row in cursor.fetchall():
        ann_map[row["llm_cache_hash"]] = dict(row)
    conn.close()

    print(f"数据库中共 {len(ann_map)} 条有 cache_hash 的公告")

    # v2 独立缓存
    os.makedirs(V2_CACHE_DIR, exist_ok=True)

    enricher = PositionEnricher()
    results = []

    for i, item in enumerate(evalset):
        eid = item["id"]
        source_file = item.get("source_file", "").replace(".json", "")
        
        # 通过 source_file（即 cache_hash）匹配公告
        ann = ann_map.get(source_file)
        if not ann:
            # 尝试其他匹配方式
            print(f"[{i+1}/25] {eid} — cache_hash {source_file} 未在数据库中找到, 跳过")
            results.append({
                "id": eid,
                "v2_positions": item.get("llm_positions", []),
                "v2_position_count": item.get("llm_position_count", 0),
                "skipped": True,
            })
            continue

        content = ann.get("content", "")
        company = ann.get("company_name", "")
        title = ann.get("announcement_title", "")
        meta = {
            "recruit_type": ann.get("recruit_type", ""),
            "recruit_target": ann.get("recruit_target", ""),
            "min_grade": ann.get("min_grade"),
            "max_grade": ann.get("max_grade"),
            "industry_raw": ann.get("industry_raw", ""),
            "company_type_raw": ann.get("company_type_raw", ""),
            "location": ann.get("location", ""),
            "education_req": ann.get("education_req", ""),
        }

        print(f"[{i+1}/25] {eid} — {company[:15]} — {title[:30]}...")

        # 检查 v2 缓存
        c_hash = _content_hash(content, company=company, title=title)
        v2_cache_path = os.path.join(V2_CACHE_DIR, f"{c_hash}.json")
        
        if os.path.exists(v2_cache_path):
            with open(v2_cache_path, "r") as f:
                v2_positions = json.load(f)
            print(f"  v2 缓存命中: {len(v2_positions)} 岗位")
        else:
            # 调用 LLM v2
            try:
                v2_positions = enricher.extract_positions(
                    content=content, company=company, title=title, meta=meta
                )
                if v2_positions:
                    with open(v2_cache_path, "w") as f:
                        json.dump(v2_positions, f, ensure_ascii=False)
                    print(f"  v2 拆出 {len(v2_positions)} 岗位")
                else:
                    print(f"  v2 拆出 0 岗位（可能拒答）")
            except Exception as e:
                print(f"  v2 LLM 调用失败: {e}")
                v2_positions = []
            time.sleep(1)  # 避免 API 限流

        results.append({
            "id": eid,
            "company": company,
            "title": title,
            "v2_position_count": len(v2_positions),
            "v2_position_titles": [p.get("position_title", "") for p in v2_positions],
            "v2_positions": v2_positions,
            "skipped": False,
        })

    with open(V2_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nv2 结果已保存: {V2_RESULTS_PATH}")
    return results


def compare_v1_v2():
    """对比 v1 和 v2 结果。"""
    with open(EVALSET_PATH, "r", encoding="utf-8") as f:
        evalset = json.load(f)
    with open(V2_RESULTS_PATH, "r", encoding="utf-8") as f:
        v2_results = json.load(f)

    v2_map = {r["id"]: r for r in v2_results}

    # v1 指标
    v1_split_correct = sum(1 for i in evalset if i["annotation"]["split_verdict"] == "correct")
    v1_under = sum(1 for i in evalset if i["annotation"]["split_verdict"] == "under_split")
    v1_over = sum(1 for i in evalset if i["annotation"]["split_verdict"] == "over_split")
    v1_missed = sum(len(i["annotation"].get("missed_positions", [])) for i in evalset)
    v1_halluc = sum(len(i["annotation"].get("hallucinated_positions", [])) for i in evalset)
    v1_avg = sum(i["annotation"]["overall_score"] for i in evalset) / len(evalset)

    # v1 city 填充率
    v1_city_filled = 0
    v1_city_empty = 0
    for item in evalset:
        for pos in item.get("llm_positions", []):
            if pos.get("city"):
                v1_city_filled += 1
            else:
                v1_city_empty += 1
    v1_city_total = v1_city_filled + v1_city_empty
    v1_city_rate = v1_city_filled / v1_city_total * 100 if v1_city_total > 0 else 0

    # v2 指标
    v2_split_correct = 0
    v2_under = 0
    v2_over = 0
    v2_missed = 0
    v2_halluc = 0
    v2_city_filled = 0
    v2_city_empty = 0

    per_sample = []

    for item in evalset:
        eid = item["id"]
        ann = item["annotation"]
        correct_count = ann["correct_position_count"]
        v1_count = item["llm_position_count"]

        v2_data = v2_map.get(eid, {})
        v2_positions = v2_data.get("v2_positions", [])
        v2_count = v2_data.get("v2_position_count", len(v2_positions))
        skipped = v2_data.get("skipped", False)

        if skipped:
            v2_count = v1_count
            v2_positions = item.get("llm_positions", [])

        # 拆岗判定
        if v2_count == correct_count:
            v2_verdict = "correct"
            v2_split_correct += 1
        elif v2_count < correct_count:
            v2_verdict = "under_split"
            v2_under += 1
            v2_missed += (correct_count - v2_count)
        else:
            v2_verdict = "over_split"
            v2_over += 1
            v2_halluc += (v2_count - correct_count)

        # city 填充率
        for pos in v2_positions:
            if pos.get("city"):
                v2_city_filled += 1
            else:
                v2_city_empty += 1

        per_sample.append({
            "id": eid,
            "bucket": item["bucket"],
            "correct": correct_count,
            "v1": v1_count,
            "v2": v2_count,
            "v1_verdict": ann["split_verdict"],
            "v2_verdict": v2_verdict,
            "improved": v2_count > v1_count and v2_count <= correct_count,
            "regressed": v2_count < v1_count or v2_count > correct_count + 2,
            "skipped": skipped,
            "v2_titles": v2_data.get("v2_position_titles", []),
        })

    v2_city_total = v2_city_filled + v2_city_empty
    v2_city_rate = v2_city_filled / v2_city_total * 100 if v2_city_total > 0 else 0

    improved = sum(1 for s in per_sample if s["improved"])
    regressed = sum(1 for s in per_sample if s["regressed"])

    # 打印
    print("\n" + "=" * 80)
    print("v1 vs v2 对比报告")
    print("=" * 80)
    print(f"\n{'指标':<25} {'v1':>10} {'v2':>10} {'Δ':>10}")
    print("-" * 60)
    print(f"{'拆岗准确率':<25} {v1_split_correct/len(evalset)*100:>9.1f}% {v2_split_correct/len(evalset)*100:>9.1f}% {(v2_split_correct-v1_split_correct)/len(evalset)*100:>+9.1f}%")
    print(f"{'漏拆数':<25} {v1_missed:>10} {v2_missed:>10}")
    print(f"{'幻觉数':<25} {v1_halluc:>10} {v2_halluc:>10}")
    print(f"{'city填充率':<25} {v1_city_rate:>9.1f}% {v2_city_rate:>9.1f}% {v2_city_rate-v1_city_rate:>+9.1f}%")
    print(f"{'改进样本':<25} {'':>10} {improved:>10}")
    print(f"{'退化样本':<25} {'':>10} {regressed:>10}")

    print(f"\n{'ID':<10} {'分层':<10} {'实际':>4} {'v1':>4} {'v2':>4} {'v1判定':<12} {'v2判定':<12} {'变化':<6}")
    print("-" * 80)
    for s in per_sample:
        if s["skipped"]:
            delta = "跳过"
        elif s["improved"]:
            delta = "✓改进"
        elif s["regressed"]:
            delta = "✗退化"
        else:
            delta = "持平"
        print(f"{s['id']:<10} {s['bucket']:<10} {s['correct']:>4} {s['v1']:>4} {s['v2']:>4} {s['v1_verdict']:<12} {s['v2_verdict']:<12} {delta:<6}")

    # 保存报告
    report = {
        "v1": {
            "split_accuracy": v1_split_correct / len(evalset) * 100,
            "missed": v1_missed,
            "hallucinated": v1_halluc,
            "city_fill_rate": v1_city_rate,
        },
        "v2": {
            "split_accuracy": v2_split_correct / len(evalset) * 100,
            "missed": v2_missed,
            "hallucinated": v2_halluc,
            "city_fill_rate": v2_city_rate,
        },
        "improved": improved,
        "regressed": regressed,
        "per_sample": per_sample,
    }
    with open(V2_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: {V2_REPORT_PATH}")


if __name__ == "__main__":
    print("=" * 80)
    print("v2 Prompt 回归测试")
    print("=" * 80)
    print("\n[Step 1] 在 25 条评测集上运行 v2 LLM 拆岗...")
    run_v2_on_evalset()
    print("\n[Step 2] 对比 v1 vs v2...")
    compare_v1_v2()
