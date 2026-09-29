"""
岗位类型树工具 — 加载 job_category_tree.json,提供 prompt 注入块与规则查找。

职责(单一):
- get_tree()              加载树(进程内缓存)
- prompt_block()          生成注入 LLM prompt 的紧凑树文本
- resolve(value)          子类名/别名/大类名 解析 → dict(type=subcategory|category)
- match_title(title)      岗位名最长别名匹配(规则兜底,LLM 归类为主路径)
- resolve_job(job)        岗位 dict 树归属:job_subcategory(允大类)优先,title 兜底
- score_fit(fit, job)     候选人方向 × 岗位树归属 → 匹配系数(1.0/0.6/0)
- SAME_CATEGORY_FACTOR    同大类得分系数 0.6

设计原则:树文件是唯一事实源,本模块只读不写;
scorer/enricher/resume_parser 共用,避免三处各维护一份映射。

岗位侧 job_subcategory 取值规则:
  - JD 有明确方向 → 填子类名(如 "AI Agent开发")
  - JD 方向不具体 → 填大类名(如 "算法"),不强制猜子类
"""
import json
import logging
import os
import threading
from typing import Dict, List, Optional

from config import settings

logger = logging.getLogger(__name__)

TREE_PATH = os.path.join(settings.DATA_DIR, "job_category_tree.json")

# 匹配规则系数(与树文件 matching_rules 对齐)
EXACT_SUBCATEGORY_FACTOR = 1.0
SAME_CATEGORY_FACTOR = 0.6

_lock = threading.RLock()
_cache: Dict = {}


def get_tree() -> Dict:
    """加载岗位类型树(进程内缓存,线程安全)。"""
    with _lock:
        if "tree" not in _cache:
            with open(TREE_PATH, "r", encoding="utf-8") as f:
                _cache["tree"] = json.load(f)
        return _cache["tree"]


def _build_indexes():
    """构建 别名→子类 / 子类名→子类 / 大类名→大类 三张索引(进程内缓存)。"""
    with _lock:
        if "alias_idx" in _cache:
            return _cache["alias_idx"]
        tree = get_tree()
        alias_idx: Dict[str, Dict] = {}
        cat_idx: Dict[str, Dict] = {}
        for ck, c in tree["categories"].items():
            sub_names = [s["name"] for s in c["subcategories"].values()]
            cat_idx[c["name"]] = {"cat_key": ck, "category_name": c["name"], "sub_names": sub_names}
            for sk, s in c["subcategories"].items():
                entry = {"type": "subcategory", "cat_key": ck, "sub_key": sk,
                         "sub_name": s["name"], "category_name": c["name"]}
                # 子类名优先注册(树已保证零冲突,setdefault 保留先注册者)
                alias_idx.setdefault(s["name"], entry)
                for a in s.get("aliases", []):
                    alias_idx.setdefault(a, entry)
        _cache["alias_idx"] = alias_idx
        _cache["cat_idx"] = cat_idx
        _cache["alias_sorted"] = sorted(alias_idx.keys(), key=lambda x: -len(x))
        return alias_idx


def resolve(value: str, allow_category: bool = False) -> Optional[Dict]:
    """解析 value → 子类或大类。

    返回 dict:
      {type:'subcategory', cat_key, sub_key, sub_name, category_name}
      {type:'category',   cat_key, category_name}
      None(未命中)

    allow_category=True 时大类名也算命中;否则只识别子类/别名。
    """
    if not value:
        return None
    _build_indexes()
    v = value.strip()
    # allow_category 时大类名优先于子类别名匹配(避免"算法"被当成子类别名)
    if allow_category and v in _cache["cat_idx"]:
        return {"type": "category", **_cache["cat_idx"][v]}
    if v in _cache["alias_idx"]:
        return dict(_cache["alias_idx"][v])
    # 容错:去常见后缀(如 "后端开发工程师" → "后端开发")
    for suffix in ("工程师", "岗", "方向", "类", "生"):
        if v.endswith(suffix) and len(v) > len(suffix) + 1:
            return resolve(v[: -len(suffix)], allow_category=allow_category)
    return None


def match_title(title: str, allow_category: bool = True) -> Optional[Dict]:
    """岗位名规则匹配:最长别名优先的子串命中(规则兜底路径)。

    子串命中子类时 type='subcategory';仅大类命中时 type='category'。
    注意:仅作降级/补全用,主路径是 enricher LLM 归类。
    """
    if not title:
        return None
    _build_indexes()
    t = title.strip()
    for alias in _cache["alias_sorted"]:
        if alias in t:
            return dict(_cache["alias_idx"][alias])
    if allow_category:
        for cn in _cache["cat_idx"]:
            if cn in t:
                return {"type": "category", **_cache["cat_idx"][cn]}
    return None


def resolve_job(job: Dict) -> Optional[Dict]:
    """解析岗位 dict 的树归属:job_subcategory 字段(允大类)优先,title 规则兜底。"""
    entry = resolve(job.get("job_subcategory") or "", allow_category=True)
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


def all_category_names() -> List[str]:
    """全部大类名列表(校验/测试用)。"""
    tree = get_tree()
    return [c["name"] for c in tree["categories"].values()]


def score_fit(fit_entry: Optional[Dict], job_entry: Optional[Dict]) -> float:
    """单个候选人方向 × 岗位树归属 → 匹配系数(1.0/0.6/0)。

    规则:
    - 两者都是子类且 sub_key 相同 → 1.0
    - 两者 cat_key 相同(同大类) → 0.6(含岗位是大类的情况)
    - 否则 → 0
    """
    if not fit_entry or not job_entry:
        return 0.0
    if (fit_entry.get("type") == "subcategory" and job_entry.get("type") == "subcategory"
            and fit_entry.get("sub_key") == job_entry.get("sub_key")):
        return EXACT_SUBCATEGORY_FACTOR
    if fit_entry.get("cat_key") == job_entry.get("cat_key"):
        return SAME_CATEGORY_FACTOR
    return 0.0
