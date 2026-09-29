"""
岗位类型树工具 — 加载 job_category_tree.json,提供 prompt 注入块与规则查找。

职责(单一):
- get_tree()              加载树(进程内缓存)
- prompt_block()          生成注入 LLM prompt 的紧凑树文本
- resolve(value)          子类名/别名 精确解析 → (cat_key, sub_key, 子类名, 大类名)
- match_title(title)      岗位名最长别名匹配(规则兜底,LLM 归类为主路径)
- SAME_CATEGORY_FACTOR    同大类得分系数 0.6

设计原则:树文件是唯一事实源,本模块只读不写;
scorer/enricher/resume_parser 共用,避免三处各维护一份映射。
"""
import json
import logging
import os
import threading
from typing import Dict, List, Optional, Tuple

from config import settings

logger = logging.getLogger(__name__)

TREE_PATH = os.path.join(settings.DATA_DIR, "job_category_tree.json")

# 匹配规则系数(与树文件 matching_rules 对齐)
EXACT_SUBCATEGORY_FACTOR = 1.0
SAME_CATEGORY_FACTOR = 0.6

_lock = threading.Lock()
_cache: Dict = {}


def get_tree() -> Dict:
    """加载岗位类型树(进程内缓存,线程安全)。"""
    with _lock:
        if "tree" not in _cache:
            with open(TREE_PATH, "r", encoding="utf-8") as f:
                _cache["tree"] = json.load(f)
        return _cache["tree"]


def _build_indexes():
    """构建 别名→子类 / 子类名→子类 两张索引(进程内缓存)。"""
    with _lock:
        if "alias_idx" in _cache:
            return _cache["alias_idx"]
        tree = get_tree()
        alias_idx: Dict[str, Tuple[str, str, str, str]] = {}
        for ck, c in tree["categories"].items():
            for sk, s in c["subcategories"].items():
                entry = (ck, sk, s["name"], c["name"])
                # 子类名优先注册(树已保证零冲突,setdefault 保留先注册者)
                alias_idx.setdefault(s["name"], entry)
                for a in s.get("aliases", []):
                    alias_idx.setdefault(a, entry)
        # 别名按长度降序缓存,供 match_title 最长优先
        _cache["alias_idx"] = alias_idx
        _cache["alias_sorted"] = sorted(alias_idx.keys(), key=lambda x: -len(x))
        return alias_idx


def resolve(value: str) -> Optional[Tuple[str, str, str, str]]:
    """精确解析子类名/别名 → (cat_key, sub_key, 子类名, 大类名);未命中返回 None。"""
    if not value:
        return None
    idx = _build_indexes()
    v = value.strip()
    if v in idx:
        return idx[v]
    # 容错:去掉常见后缀再试(如 "后端开发工程师" → "后端开发")
    for suffix in ("工程师", "岗", "方向", "类", "生"):
        if v.endswith(suffix) and len(v) > len(suffix) + 1:
            if v[: -len(suffix)] in idx:
                return idx[v[: -len(suffix)]]
    return None


def match_title(title: str) -> Optional[Tuple[str, str, str, str]]:
    """岗位名规则匹配:最长别名优先的子串命中(规则兜底路径)。

    注意:仅作降级/补全用,主路径是 enricher LLM 归类。
    """
    if not title:
        return None
    _build_indexes()
    t = title.strip()
    for alias in _cache["alias_sorted"]:
        if alias in t:
            return _cache["alias_idx"][alias]
    return None


def resolve_job(job: Dict) -> Optional[Tuple[str, str, str, str]]:
    """解析岗位 dict 的树归属:job_subcategory 字段优先,title 规则兜底。"""
    entry = resolve((job.get("job_subcategory") or "").strip())
    if entry is None:
        entry = match_title(job.get("position_title") or "")
    return entry


def prompt_block() -> str:
    """生成注入 LLM prompt 的紧凑树文本(大类: 子类1, 子类2, ...)。"""
    tree = get_tree()
    lines = []
    for c in tree["categories"].values():
        subs = ", ".join(s["name"] for s in c["subcategories"].values())
        lines.append(f"- {c['name']}: {subs}")
    return "\n".join(lines)


def all_subcategory_names() -> List[str]:
    """全部子类名列表(校验/测试用)。"""
    tree = get_tree()
    return [s["name"] for c in tree["categories"].values() for s in c["subcategories"].values()]


def score_fit(fit_entry, job_entry) -> float:
    """单个候选人方向 × 岗位树归属 → 匹配系数(1.0/0.6/0)。

    fit_entry/job_entry 均为 resolve() 返回的 (cat_key, sub_key, 子类名, 大类名)。
    """
    if not fit_entry or not job_entry:
        return 0.0
    if fit_entry[1] == job_entry[1]:
        return EXACT_SUBCATEGORY_FACTOR
    if fit_entry[0] == job_entry[0]:
        return SAME_CATEGORY_FACTOR
    return 0.0
