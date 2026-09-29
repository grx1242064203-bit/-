"""
全量匹配脚本 — 2 份测试简历 × 全部岗位,输出 Top 推荐结果与维度拆解。

用法:
    python3 run_full_match.py
"""
import json
import os
import sys
import time
from typing import Dict, List

from config import settings
from models import UserProfile
from resume_parser import parse_resume_text
from job_db import get_all_positions_for_export
from scorer import score_job

RESUMES = [
    ("resume1_AI_Agent_Infra", os.path.join(settings.DATA_DIR, "test_resume_1.txt")),
    ("resume2_嵌入式AI",       os.path.join(settings.DATA_DIR, "test_resume_2.txt")),
]

OUT_DIR = os.path.join(settings.DATA_DIR, "full_match")
os.makedirs(OUT_DIR, exist_ok=True)


def build_profile(name: str, resume_text: str) -> UserProfile:
    """从简历文本构造 UserProfile:LLM 解析 → structured_keywords → profile。"""
    print(f"\n[{name}] 解析简历 (text len={len(resume_text)}) ...", flush=True)
    keywords = parse_resume_text(resume_text)
    print(f"[{name}] 关键词数: {len(keywords)}", flush=True)

    p = UserProfile()
    p.role = "campus"
    p.resume_text = resume_text
    p.structured_keywords = keywords

    # 从关键词中推断 degree / major / target_cities(轻量补全,不调 LLM)
    for tag in keywords:
        cat = tag.get("category", "")
        std = tag.get("standard") or tag.get("kw", "")
        if cat == "education" and not p.degree:
            for lv in ("博士", "硕士", "本科", "大专"):
                if lv in std:
                    p.degree = lv
                    break
        if cat == "education" and not p.major and std and not any(
            lv in std for lv in ("博士", "硕士", "本科", "大专", "大学", "学院")
        ):
            p.major = std
        if cat == "city" and std not in p.target_cities:
            p.target_cities.append(std)

    # 兜底:简历1/2 都明确写了硕士
    if not p.degree:
        if "硕士" in resume_text:
            p.degree = "硕士"
        elif "本科" in resume_text:
            p.degree = "本科"

    print(f"[{name}] degree={p.degree!r} major={p.major!r} cities={p.target_cities}", flush=True)
    return p


def run_match_for_resume(name: str, profile: UserProfile, jobs: List[Dict]) -> List[Dict]:
    """对一份简历跑全量岗位评分,返回按分数降序的结果列表。"""
    t0 = time.time()
    scored: List[Dict] = []
    n = len(jobs)
    for i, job in enumerate(jobs, 1):
        try:
            result = score_job(job, profile)
        except Exception as e:
            result = {"相关性评分": 0.0, "综合推荐度": "错误", "匹配理由": [f"[error] {e}"], "维度分": {}}
        scored.append({**job, **result})
        if i % 300 == 0 or i == n:
            dt = time.time() - t0
            print(f"  [{name}] {i}/{n}  elapsed={dt:.1f}s  avg={dt/i*1000:.1f}ms/job", flush=True)
    scored.sort(key=lambda x: x.get("相关性评分", 0), reverse=True)
    print(f"[{name}] 完成: {n} 岗位,耗时 {time.time()-t0:.1f}s,Top1={scored[0].get('相关性评分')}", flush=True)
    return scored


def dump_result(name: str, profile: UserProfile, scored: List[Dict]):
    """输出 Top 推荐 + 维度拆解到 JSON + Markdown。"""
    out_json = os.path.join(OUT_DIR, f"{name}_top50.json")
    out_md = os.path.join(OUT_DIR, f"{name}_top50.md")

    top50 = scored[:50]
    slim = []
    for s in top50:
        slim.append({
            "rank": len(slim) + 1,
            "score": s.get("相关性评分"),
            "recommend": s.get("综合推荐度"),
            "company": s.get("company_name"),
            "position": s.get("position_title"),
            "city": s.get("location") or s.get("city"),
            "job_category": s.get("job_category"),
            "education_req": s.get("education_req") or s.get("min_education"),
            "deadline": s.get("deadline"),
            "apply_url": s.get("apply_url") or s.get("announcement_url"),
            "dims": s.get("维度分", {}),
            "reasons": s.get("匹配理由", []),
            "hard_skills": s.get("hard_skills", [])[:8],
            "keywords": s.get("keywords", [])[:8],
        })
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "resume": name,
            "degree": profile.degree,
            "major": profile.major,
            "target_cities": profile.target_cities,
            "kw_count": len(profile.structured_keywords),
            "total_jobs": len(scored),
            "top50": slim,
        }, f, ensure_ascii=False, indent=2)

    # Markdown 报告
    lines = []
    lines.append(f"# {name} — 全量匹配 Top 50\n")
    lines.append(f"- 简历关键词数: {len(profile.structured_keywords)}")
    lines.append(f"- 学历: {profile.degree}  专业: {profile.major}  目标城市: {profile.target_cities}")
    lines.append(f"- 全量岗位: {len(scored)}  跑分耗时见日志\n")
    lines.append("## 维度权重\n")
    from scorer import DIMENSION_WEIGHTS
    for k, v in DIMENSION_WEIGHTS.items():
        lines.append(f"- {k}: {v}")
    lines.append("\n## Top 50 推荐\n")
    lines.append("| # | 分数 | 推荐度 | 公司 | 岗位 | 城市 | 方向 | 学历 | skill | hard | role | city | edu |")
    lines.append("|---|------|--------|------|------|------|------|------|-------|------|------|------|-----|")
    for s in slim:
        d = s["dims"]
        lines.append(
            f"| {s['rank']} | {s['score']:.1f} | {s['recommend']} | {s['company']} | "
            f"{s['position']} | {s['city'] or '-'} | {s['job_category'] or '-'} | "
            f"{s['education_req'] or '-'} | "
            f"{d.get('skill',0):.0f} | {d.get('hard_skill',0):.0f} | "
            f"{d.get('role',0):.0f} | {d.get('city',0):.0f} | {d.get('education',0):.0f} |"
        )

    lines.append("\n## Top 10 维度拆解(详细匹配理由)\n")
    for s in slim[:10]:
        lines.append(f"### #{s['rank']}  {s['score']:.1f}  {s['company']} — {s['position']}\n")
        lines.append(f"- 城市方向: {s['city'] or '-'} / {s['job_category'] or '-'}")
        lines.append(f"- 岗位硬技能: {', '.join(s['hard_skills']) or '-'}")
        lines.append(f"- 岗位关键词: {', '.join(s['keywords']) or '-'}")
        lines.append(f"- 申请链接: {s['apply_url'] or '-'}")
        lines.append("- 匹配理由:")
        for r in s["reasons"]:
            lines.append(f"  - {r}")
        lines.append("")

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[{name}] 报告已写: {out_md}", flush=True)
    print(f"[{name}] JSON  已写: {out_json}", flush=True)


def main():
    print("=" * 70, flush=True)
    print("全量匹配: 2 简历 × 全部岗位", flush=True)
    print("=" * 70, flush=True)

    print("\n[STEP 1] 加载全量岗位 ...", flush=True)
    jobs = get_all_positions_for_export()
    print(f"  共 {len(jobs)} 个岗位", flush=True)

    print("\n[STEP 2] 解析简历 + 构造 UserProfile ...", flush=True)
    profiles = []
    for name, path in RESUMES:
        if not os.path.exists(path):
            print(f"  [skip] 简历不存在: {path}", flush=True)
            continue
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        p = build_profile(name, text)
        profiles.append((name, p))

    print("\n[STEP 3] 跑全量评分 ...", flush=True)
    for name, p in profiles:
        scored = run_match_for_resume(name, p, jobs)
        dump_result(name, p, scored)

    print("\n[DONE] 全部完成。", flush=True)


if __name__ == "__main__":
    main()
