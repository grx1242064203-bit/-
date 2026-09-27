"""
归一化模块 — 行业/公司类型/届数/招聘类型的标准化处理。

设计原则:
1. 映射规则集中在 mappings.json(可编辑,无需改代码)
2. 关键词匹配:原始值含任一关键词即归入对应大类
3. 未命中归"其他"+ 日志告警,便于后续补充映射
4. 届数解析:正则提取 4 位年份后取后两位,无法解析用默认 25-27
"""
import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MAPPING_FILE = os.path.join(os.path.dirname(__file__), "mappings.json")

# 模块级缓存(首次加载后常驻,文件变更需重启或调 reload)
_mappings: Optional[Dict] = None
_unmapped_log: Dict[str, int] = {}  # 记录未命中的原始值及次数


def _load_mappings() -> Dict:
    """加载 mappings.json(带缓存)。"""
    global _mappings
    if _mappings is None:
        try:
            with open(MAPPING_FILE, "r", encoding="utf-8") as f:
                _mappings = json.load(f)
            logger.info(f"归一化映射已加载: {MAPPING_FILE}")
        except Exception as e:
            logger.error(f"加载映射文件失败 {MAPPING_FILE}: {e}")
            _mappings = {}
    return _mappings


def reload_mappings():
    """重新加载映射文件(配置变更后调用)。"""
    global _mappings, _unmapped_log
    _mappings = None
    _unmapped_log = {}
    _load_mappings()


def _match_category(raw: str, categories: List[Dict]) -> str:
    """
    关键词匹配归大类。
    raw 为空返回"其他"。逐个检查每个大类的 keywords,首个命中即返回。
    """
    if not raw or not raw.strip():
        return "其他"
    raw_lower = raw.strip().lower()
    for cat in categories:
        for kw in cat.get("keywords", []):
            if kw.lower() in raw_lower:
                return cat["name"]
    # 未命中
    _unmapped_log[raw] = _unmapped_log.get(raw, 0) + 1
    return "其他"


def normalize_industry(raw_industry: str) -> str:
    """行业归一化 → 12 大类之一。"""
    return _match_category(raw_industry, _load_mappings().get("industry_categories", []))


def normalize_company_type(raw_type: str) -> str:
    """公司类型归一化 → 5 大类之一。"""
    return _match_category(raw_type, _load_mappings().get("company_type_categories", []))


def is_campus_recruit_type(recruit_type: str) -> bool:
    """判断招聘类型是否为校招(5 类之一)。"""
    if not recruit_type:
        return False
    valid_types = _load_mappings().get("recruit_types", [])
    rt = recruit_type.strip()
    return rt in valid_types


def parse_grade_range(recruit_target: str) -> Tuple[int, int]:
    """
    解析招聘对象 → (min_grade, max_grade)。
    届数取年份后两位(2025→25, 2027→27)。

    示例:
      "2027届"          → (27, 27)
      "2025-2027届"     → (25, 27)
      "25-27届"         → (25, 27)
      "2026/2027届"     → (26, 27)
      "应届毕业生"       → (25, 27)  默认
      "class of 2027"   → (27, 27)
      "" / None          → (25, 27)  默认
    """
    defaults = _load_mappings().get("grade_defaults", {"min": 25, "max": 27})
    default_min = defaults.get("min", 25)
    default_max = defaults.get("max", 27)

    if not recruit_target or not recruit_target.strip():
        return (default_min, default_max)

    text = recruit_target.strip()

    # 提取所有 4 位年份(如 2025, 2026, 2027)
    years_4d = [int(y) for y in re.findall(r"20(\d{2})", text)]
    # 提取所有 2 位届数(如 25, 26, 27) — 排除已被4位匹配的部分
    # 先把4位年份替换掉,再找独立的2位数
    text_no_4d = re.sub(r"20\d{2}", "", text)
    years_2d = [int(y) for y in re.findall(r"(?<!\d)(2[5-9])(?!\d)", text_no_4d)]

    all_grades = years_4d + years_2d
    # 过滤合理范围(20-30 届)
    all_grades = [g for g in all_grades if 20 <= g <= 30]

    if all_grades:
        return (min(all_grades), max(all_grades))

    # "应届"/"毕业生" 等无具体年份 → 默认范围
    return (default_min, default_max)


def get_unmapped_stats() -> Dict[str, int]:
    """获取未命中归一化的原始值统计(用于告警和补充映射)。"""
    return dict(_unmapped_log)


def get_industry_options() -> List[str]:
    """获取行业 12 大类列表(供学生配置岗位时选择)。"""
    return [c["name"] for c in _load_mappings().get("industry_categories", [])]


def get_company_type_options() -> List[str]:
    """获取公司类型 5 大类列表(供学生配置岗位时选择)。"""
    return [c["name"] for c in _load_mappings().get("company_type_categories", [])]
