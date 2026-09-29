
"""
简历关键词结构化提取器 — 从简历文本 → LLM 解析 → 标准化归一化 → 结构化关键词列表。

复用现有 LLMClient(DeepSeek) + keyword_normalizer(同义词归一化)。
缓存:简历文本 hash → 解析结果 JSON,避免重复调用 LLM。

输出格式:List[Dict],与 UserProfile.structured_keywords 的 KeywordTag dataclass 对齐,
可直接 json.dumps 存入 users.json。
"""
import hashlib
import json
import logging
import os
from typing import Dict, List, Optional

from config import settings
from keyword_normalizer import normalize

logger = logging.getLogger(__name__)

_RESUME_CACHE_DIR = os.path.join(settings.DATA_DIR, "resume_cache")

_RESUME_PARSE_PROMPT = """你是校招简历解析专家。请从以下简历中提取用于岗位匹配的结构化关键词。

简历文本:
\"\"\"{resume_text}\"\"\"

请输出严格 JSON 数组(不要输出任何 JSON 以外的文字):
[
  {{
    "kw": "原始关键词(从简历中原样摘录,不要改写)",
    "category": "skill|hard_skill|soft_skill|tool|framework|domain|cert|education|city|role|project|language",
    "weight": 1.0 到 5.0 之间的浮点数,
    "resume_section": "education|experience|project|skill|summary|other",
    "inferred": false
  }}
]

提取规则(严格遵守,每条都是硬约束):
1. ★★ 推断补全规则(本 prompt 最核心) — 当简历中出现某框架/工具/技术产品时,必须**额外输出**其底层语言或关联技术,标记 "inferred": true:
   - Flask/Django/FastAPI/PyTorch/TensorFlow/NumPy/Pandas → 补 "Python" (hard_skill, inferred=true)
   - Spring/Spring Boot/Dubbo/Maven → 补 "Java" (hard_skill, inferred=true)
   - React/Vue/Angular/Next.js/TypeScript → 补 "JavaScript" (hard_skill, inferred=true)
   - NestJS/Express/Koa → 补 "Node.js" (hard_skill, inferred=true)
   - PyTorch/CUDA/GPU → 补 "机器学习" 或 "深度学习" (hard_skill, inferred=true)
   - TensorFlow Lite / TFLite / 量化 / INT8 → 补 "边缘AI" 或 "模型压缩" (skill, inferred=true)
   - Verilog/VHDL/Quartus → 补 "FPGA开发" (skill, inferred=true)
   - CMake/Makefile/GCC → 补 "C/C++" (hard_skill, inferred=true)
   - Keras/ONNX/HuggingFace → 补 "深度学习" (hard_skill, inferred=true)
   - SLAM/ROS/导航/路径规划 → 补 "机器人" 或 "自动驾驶" (domain 或 skill, inferred=true)
   ★ 推断补全的 weight = 该框架/工具 weight × 0.7 (因为是推断的,权重略低于显式声明)
   ★ 推断补全不要重复:如果 Python 已经显式出现过,不要再补一次

2. category 分类标准:
   - hard_skill: 编程语言/框架/技术栈/算法/专业技术,如 Python/Java/Spring/Docker/Kubernetes/React/Vue/机器学习/深度学习/嵌入式/信号处理/FPGA
     ★ 只放**可复用的标准技术术语**,不要放项目专属名词(如"EASY CODE""Semantic Compaction""TaskBudget"这类私有概念)
   - soft_skill: 沟通/团队/领导力/项目管理/敏捷方法
   - tool: 工具软件,如 Git/Jenkins/Postman/Figma
   - framework: 框架,如 Spring/Django/FastAPI/TensorFlow/PyTorch
   - domain: 行业领域(仅限),如 金融/电商/教育/医疗/智能制造/通信/物联网/5G/汽车
     ★ 严禁把**公司名/团队名/学校名**放入 domain!公司名、团队名属于 education/other
   - cert: 证书,如 CFA/CPA/法考/PMP/阿里云认证/英语四六级/GRE
   - education: 学校/专业/学历,如 清华大学/计算机科学与技术/硕士
   - city: 城市,如 北京/上海/深圳/杭州
   - role: 目标岗位/职业方向(标准化!),如 后端开发/数据分析师/产品经理/算法工程师/嵌入式AI开发/AI基础设施研发/软件测试/硬件工程师
     ★ 用通用岗位名称,不要用简历原文的长句
   - project: 项目名称,如 XX推荐系统/XX风控系统
   - skill: 通用能力关键词(不属于以上类别的技能),如 分布式缓存/微服务/敏捷开发/系统设计/性能优化
   - language: 语言能力,如 英语/日语/普通话

3. weight 赋值(1.0 到 5.0):
   - 项目经历中作为核心技能且出现多次:4.0-5.0
   - 简历技能列表中明确列出:3.0-4.0
   - 教育背景/实习经历中提到:2.0-3.0
   - 简历中只提一次且不突出:1.0-2.0

4. resume_section 标记关键词在简历中的出处段落
5. 数量控制:显式 25-40 + 推断补全 5-15 = 总计 30-50 个
6. 证书类关键词要写全称(CFA/CPA/法考/PMP),不要只写缩写
7. 城市只写明确提到的,不要猜测
8. role 关键词非常重要:从简历求职意向+项目方向推断 2-4 个最匹配的岗位名称(如"后端开发""算法工程师""嵌入式AI开发")
"""


def _resume_hash(text: str) -> str:
    key = text.strip()
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def _cache_path(h: str) -> str:
    return os.path.join(_RESUME_CACHE_DIR, f"{h}.json")


def _load_cache(h: str) -> Optional[List[Dict]]:
    path = _cache_path(h)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.debug(f"简历缓存读取失败: {e}")
    return None


def _save_cache(h: str, keywords: List[Dict]):
    os.makedirs(_RESUME_CACHE_DIR, exist_ok=True)
    try:
        with open(_cache_path(h), "w", encoding="utf-8") as f:
            json.dump(keywords, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"简历缓存写入失败: {e}")


def _parse_llm_output(text: str) -> List[Dict]:
    """兼容多种 LLM 输出格式(与 llm_enricher.py 的解析逻辑一致)"""
    if not text:
        return []
    text = text.strip()
    import re
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return [d for d in obj if isinstance(d, dict)]
        if isinstance(obj, dict):
            for wrap_key in ("positions", "jobs", "data", "items", "result", "keywords", "tags"):
                if wrap_key in obj and isinstance(obj[wrap_key], list):
                    return [d for d in obj[wrap_key] if isinstance(d, dict)]
            return [obj]
    except json.JSONDecodeError:
        pass

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except json.JSONDecodeError:
            pass

    return []


def _normalize_and_dedupe(raw_tags: List[Dict]) -> List[Dict]:
    """
    对 LLM 输出的原始 tags 做标准化 + 去重。
    去重规则:多个原始关键词归一化到同一个 canonical form 时,保留权重最高的那个。
    """
    dedupe_map: Dict[str, Dict] = {}

    for tag in raw_tags:
        kw = (tag.get("kw") or "").strip()
        if not kw:
            continue
        std, hit = normalize(kw)
        weight = float(tag.get("weight") or 1.0)
        category = tag.get("category") or "other"
        section = tag.get("resume_section") or "other"

        canonical = std if hit else kw.lower()

        existing = dedupe_map.get(canonical)
        if existing and existing["weight"] >= weight:
            continue

        dedupe_map[canonical] = {
            "kw": kw,
            "standard": std if hit else kw,
            "category": category,
            "weight": round(weight, 2),
            "resume_section": section,
            "source": "resume_llm",
        }

    return sorted(dedupe_map.values(), key=lambda x: -x["weight"])


def parse_resume_text(resume_text: str, llm_client=None) -> List[Dict]:
    """
    从简历文本解析生成结构化关键词列表。

    Args:
        resume_text: 简历纯文本(已从 PDF/DOCX 提取)
        llm_client: 复用项目的 LLMClient,默认自动创建

    Returns:
        List[Dict],每个 dict 包含 kw/standard/category/weight/resume_section/source
    """
    h = _resume_hash(resume_text)
    cached = _load_cache(h)
    if cached is not None:
        logger.info(f"简历关键词缓存命中: {len(cached)} 个")
        return cached

    from llm_client import LLMClient
    client = llm_client or LLMClient()

    prompt = _RESUME_PARSE_PROMPT.format(resume_text=resume_text[:12000])

    try:
        raw = client._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=8000,
        )
        raw_tags = _parse_llm_output(raw)
        if not raw_tags:
            logger.warning(f"简历 LLM 解析返回空: {raw[:200]}")
            return []

        normalized = _normalize_and_dedupe(raw_tags)
        _save_cache(h, normalized)
        logger.info(f"简历关键词解析完成: 原始 {len(raw_tags)} → 去重后 {len(normalized)}")
        return normalized

    except Exception as e:
        logger.error(f"简历 LLM 解析失败: {e}")
        return []


def apply_keywords_to_profile(profile, keywords: List[Dict]):
    """
    将解析好的结构化关键词应用到 UserProfile,同时同步更新旧字段(向后兼容)。

    - structured_keywords: 全部关键词(新版引擎)
    - core_skills: 合并 hard_skill/tool/framework 类关键词
    - direction_keywords: 按 role/category 分组写入
    """
    profile.structured_keywords = keywords

    core = []
    direction: Dict[str, List[str]] = {}

    for tag in keywords:
        cat = tag.get("category", "")
        std = tag.get("standard") or tag.get("kw", "")

        if cat in ("hard_skill", "tool", "framework"):
            core.append(std)
        elif cat in ("role",):
            direction.setdefault("role", []).append(std)
        elif cat in ("domain",):
            direction.setdefault("domain", []).append(std)
        elif cat in ("skill",):
            direction.setdefault("skill", []).append(std)

    profile.core_skills = list(dict.fromkeys(core))
    profile.direction_keywords = {k: list(dict.fromkeys(v)) for k, v in direction.items()}

    return profile
