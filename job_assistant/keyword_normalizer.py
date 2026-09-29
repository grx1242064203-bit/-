
"""
关键词标准化归一化模块 — 同义词/缩写/中英文统一。

设计原则:
1. 同义词词典 JSON 热加载:文件 mtime 变化自动重载,无需重启
2. 反向索引:别名(小写去空格)→ canonical form, O(1) 查找
3. 不可命中词典的关键词保持原样返回,不做强制修改
"""
import json
import logging
import os
import time
from typing import List, Tuple, Optional

from config import settings

logger = logging.getLogger(__name__)

_DICT_PATH = os.path.join(settings.DATA_DIR, "kw_dict.json")
_RELOAD_INTERVAL = 30.0  # 秒,两次检查词典文件 mtime 的间隔

_cache = {"data": {}, "reverse": {}, "last_check": 0.0, "mtime": 0.0}


def _build_reverse_index(data: dict) -> dict:
    rev = {}
    for canonical, aliases in data.items():
        norm = canonical.lower().replace(" ", "").replace("_", "")
        rev[norm] = canonical
        for alias in aliases:
            norm_alias = alias.lower().replace(" ", "").replace("-", "")
            rev[norm_alias] = canonical
    return rev


def _maybe_reload():
    now = time.time()
    if now - _cache["last_check"] < _RELOAD_INTERVAL:
        return
    _cache["last_check"] = now

    if not os.path.exists(_DICT_PATH):
        logger.warning(f"同义词词典不存在: {_DICT_PATH}")
        return

    try:
        mtime = os.path.getmtime(_DICT_PATH)
        if mtime == _cache["mtime"]:
            return
        with open(_DICT_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        data = {k: v for k, v in raw.items() if not k.startswith("_")}
        _cache["data"] = data
        _cache["reverse"] = _build_reverse_index(data)
        _cache["mtime"] = mtime
        logger.info(f"同义词词典已加载: {len(data)} 组 canonical, {len(_cache['reverse'])} 条索引")
    except Exception as e:
        logger.error(f"同义词词典加载失败: {e}")


def normalize(kw: str) -> Tuple[str, bool]:
    """
    将关键词归一化为 canonical form。

    Returns:
        (canonical, found) — found=True 表示命中词典,
        found=False 表示未命中,此时 canonical 就是原始 kw
    """
    _maybe_reload()
    if not kw:
        return "", False

    norm = kw.lower().strip().replace(" ", "").replace("-", "").replace("_", "")
    if norm in _cache["reverse"]:
        return _cache["reverse"][norm], True
    return kw.strip(), False


def batch_normalize(kws: List[str]) -> List[Tuple[str, bool]]:
    """批量归一化"""
    return [normalize(kw) for kw in kws]


def match_score(a: str, b: str) -> float:
    """
    计算两个关键词的匹配分。

    0.0  = 完全不匹配
    1.0  = 命中同一个 canonical form (同义词/别名)
    0.8  = 互为包含 (Redis ==> RedisCluster)
    0.5  = 共享词根 (Python vs PyTorch 共享 "Py")
    """
    if not a or not b:
        return 0.0
    a_std, a_hit = normalize(a)
    b_std, b_hit = normalize(b)

    if a_std and b_std and a_std == b_std:
        return 1.0

    a_l, b_l = a.lower(), b.lower()
    if a_l == b_l:
        return 1.0

    if a_l in b_l or b_l in a_l:
        return 0.8

    a_tokens = set(a_l.replace("-", " ").replace("_", " ").split())
    b_tokens = set(b_l.replace("-", " ").replace("_", " ").split())
    common = a_tokens & b_tokens
    if common and len(common) / max(len(a_tokens), len(b_tokens)) >= 0.5:
        return 0.5

    return 0.0


def keyword_set_overlap(user_kws: List[str], job_kws: List[str]) -> Tuple[int, float, List[Tuple[str, str]]]:
    """
    计算两组关键词的重叠度。

    Returns:
        (命中数, Jaccard 相似度, 命中对列表)
    """
    if not user_kws or not job_kws:
        return 0, 0.0, []

    hits: List[Tuple[str, str]] = []
    matched_job_idx = set()
    for uk in user_kws:
        for i, jk in enumerate(job_kws):
            if i in matched_job_idx:
                continue
            if match_score(uk, jk) >= 0.8:
                hits.append((uk, jk))
                matched_job_idx.add(i)
                break

    union_size = len(set(user_kws) | set(job_kws))
    jaccard = len(set(h[0] for h in hits)) / union_size if union_size > 0 else 0.0
    return len(hits), jaccard, hits
