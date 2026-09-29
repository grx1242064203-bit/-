"""
简历关键词结构化提取器 — 从简历文本 → LLM 解析 → 标准化归一化 → 结构化关键词 + 适配岗位方向。

复用现有 LLMClient(DeepSeek) + keyword_normalizer(同义词归一化) + job_tree(岗位类型树)。
缓存:简历文本 hash → 解析结果 JSON,避免重复调用 LLM。

输出:{"keywords": [...], "fit_directions": [...]}
- keywords: List[Dict],与 UserProfile.structured_keywords 的 KeywordTag 对齐
- fit_directions: List[Dict],候选人适配的岗位子类及权重,供 scorer role 维度使用
"""
import hashlib
import json
import logging
import os
from typing import Dict, List, Optional, Tuple

from config import settings
from keyword_normalizer import normalize
import job_tree

logger = logging.getLogger(__name__)

_RESUME_CACHE_DIR = os.path.join(settings.DATA_DIR, "resume_cache")
_CACHE_VERSION = "v2"  # 升版本强制重跑(新增 fit_directions)

_RESUME_PARSE_PROMPT = """你是校招简历解析专家。请从以下简历中提取用于岗位匹配的结构化关键词,并判断该候选人适配的岗位方向。

简历文本:
\"\"\"{resume_text}\"\"\"

岗位类型树(大类: 子类列表):
{job_tree_block}

请输出严格 JSON 对象(不要输出任何 JSON 以外的文字):
{{
  "keywords": [
    {{
      "kw": "原始关键词(从简历中原样摘录,不要改写)",
      "category": "skill|hard_skill|soft_skill|tool|framework|domain|cert|education|city|role|project|language",
      "weight": 1.0 到 5.0 之间的浮点数,
      "resume_section": "education|experience|project|skill|summary|other",
      "inferred": false
    }}
  ],
  "fit_directions": [
    {{
      "direction": "必须从上面岗位类型树的子类名中选(如\"AI Agent开发\"),不要自己造词",
      "weight": 0.0 到 1.0 之间的浮点数,表示该候选人对该方向的适配度,
      "evidence": "一句话说明依据(项目/实习/技能/学历)"
    }}
  ]
}}

提取规则(严格遵守):

【keywords 部分】
1. ★★ 推断补全规则 — 当简历中出现某框架/工具时,必须额外输出其底层语言或关联技术,标记 inferred=true:
   - Flask/Django/FastAPI/PyTorch/TensorFlow/NumPy/Pandas → 补 "Python"
   - Spring/Spring Boot/Dubbo/Maven → 补 "Java"
   - React/Vue/Angular/Next.js/TypeScript → 补 "JavaScript"
   - NestJS/Express/Koa → 补 "Node.js"
   - PyTorch/CUDA/GPU → 补 "机器学习" 或 "深度学习"
   - TFLite/量化/INT8 → 补 "边缘AI" 或 "模型压缩"
   - Verilog/VHDL/Quartus → 补 "FPGA开发"
   - CMake/Makefile/GCC → 补 "C/C++"
   - Keras/ONNX/HuggingFace → 补 "深度学习"
   - SLAM/ROS/导航/路径规划 → 补 "机器人" 或 "自动驾驶"
   推断补全的 weight = 该框架 weight × 0.7;不要重复补已显式出现的词。

2. category 分类:
   - hard_skill: 编程语言/框架/技术栈/算法(可复用标准术语,不放项目专属名词)
   - soft_skill: 沟通/团队/领导力/项目管理/敏捷
   - tool: Git/Jenkins/Postman/Figma
   - framework: Spring/Django/FastAPI/TensorFlow/PyTorch
   - domain: 行业领域(金融/电商/教育/医疗/制造/通信/物联网/5G/汽车),不放公司/学校名
   - cert: CFA/CPA/法考/PMP/英语四六级
   - education: 学校/专业/学历
   - city: 明确提到的城市
   - role: 目标岗位方向(标准化通用名)
   - project: 项目名称
   - skill: 通用能力(分布式缓存/微服务/系统设计/性能优化)
   - language: 语言能力

3. weight: 核心技能多次出现4-5,技能列表3-4,背景实习2-3,提一次1-2
4. 显式25-40 + 推断补全5-15 = 总计30-50个
5. 证书写全称;城市不猜测

【fit_directions 部分 ★ 核心】
6. 从岗位类型树的子类名中选 3-6 个最匹配的方向,按适配度从高到低排列
7. weight 赋值依据:
   - 0.9-1.0: 有对口核心项目/实习,技能栈高度匹配
   - 0.7-0.9: 有相关项目或技能,方向明确
   - 0.5-0.7: 技能部分匹配,可转型
   - 0.3-0.5: 仅弱相关,需要较多补课
   - <0.3: 不要列入
8. evidence 必须具体,引用简历中的项目/实习/技能/学历作为依据
9. direction 只能是树中的子类名(如"AI Agent开发""后端开发""边缘AI/嵌入式AI"),不允许填大类名或自造词
"""


def _resume_hash(text: str) -> str:
    key = f"{_CACHE_VERSION}:{text.strip()}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


def _cache_path(h: str) -> str:
    return os.path.join(_RESUME_CACHE_DIR, f"{h}.json")


def _load_cache(h: str) -> Optional[Dict]:
    path = _cache_path(h)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "keywords" in data:
                    return data
        except Exception as e:
            logger.debug(f"简历缓存读取失败: {e}")
    return None


def _save_cache(h: str, result: Dict):
    os.makedirs(_RESUME_CACHE_DIR, exist_ok=True)
    try:
        with open(_cache_path(h), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"简历缓存写入失败: {e}")


def _parse_llm_output(text: str) -> Tuple[List[Dict], List[Dict]]:
    """解析 LLM 输出 → (keywords, fit_directions)。兼容多种格式。"""
    if not text:
        return [], []
    import re
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    obj = None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                obj = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

    keywords: List[Dict] = []
    fit_dirs: List[Dict] = []
    if isinstance(obj, dict):
        keywords = [d for d in (obj.get("keywords") or []) if isinstance(d, dict)]
        fit_dirs = [d for d in (obj.get("fit_directions") or []) if isinstance(d, dict)]
        # 兜底:如果 LLM 只返回了数组(旧格式),当 keywords 处理
        if not keywords and not fit_dirs:
            for wrap_key in ("positions", "jobs", "data", "items", "result", "tags"):
                if isinstance(obj.get(wrap_key), list):
                    keywords = [d for d in obj[wrap_key] if isinstance(d, dict)]
                    break
    elif isinstance(obj, list):
        keywords = [d for d in obj if isinstance(d, dict)]
    return keywords, fit_dirs


def _normalize_keywords(raw_tags: List[Dict]) -> List[Dict]:
    """对 keywords 做标准化 + 去重(同 canonical 保留权重最高者)。"""
    dedupe_map: Dict[str, Dict] = {}
    for tag in raw_tags:
        kw = (tag.get("kw") or "").strip()
        if not kw:
            continue
        std, hit = normalize(kw)
        weight = float(tag.get("weight") or 1.0)
        canonical = std if hit else kw.lower()
        existing = dedupe_map.get(canonical)
        if existing and existing["weight"] >= weight:
            continue
        dedupe_map[canonical] = {
            "kw": kw,
            "standard": std if hit else kw,
            "category": tag.get("category") or "other",
            "weight": round(weight, 2),
            "resume_section": tag.get("resume_section") or "other",
            "source": "resume_llm",
        }
    return sorted(dedupe_map.values(), key=lambda x: -x["weight"])


def _validate_fit_directions(raw_dirs: List[Dict]) -> List[Dict]:
    """校验 fit_directions 的 direction 必须是树中子类名;非法的丢弃并记日志。"""
    valid = []
    for d in raw_dirs:
        direction = (d.get("direction") or "").strip()
        if not direction:
            continue
        entry = job_tree.resolve(direction)
        if entry is None or entry.get("type") != "subcategory":
            logger.warning(f"fit_directions 非法 direction 丢弃: {direction!r} (非树中子类)")
            continue
        try:
            weight = float(d.get("weight") or 0.0)
        except (TypeError, ValueError):
            weight = 0.0
        weight = max(0.0, min(1.0, weight))
        if weight < 0.3:
            continue
        valid.append({
            "direction": entry["sub_name"],  # 标准化为树中的子类名
            "cat_key": entry["cat_key"],
            "sub_key": entry["sub_key"],
            "category_name": entry["category_name"],
            "weight": round(weight, 2),
            "evidence": (d.get("evidence") or "").strip()[:200],
        })
    # 按权重降序,最多保留 8 个
    valid.sort(key=lambda x: -x["weight"])
    return valid[:8]


def parse_resume_text(resume_text: str, llm_client=None) -> Dict:
    """
    从简历文本解析生成结构化关键词 + 适配岗位方向。

    Returns:
        {"keywords": List[Dict], "fit_directions": List[Dict]}
        keywords: 每个 dict 含 kw/standard/category/weight/resume_section/source
        fit_directions: 每个 dict 含 direction/cat_key/sub_key/category_name/weight/evidence
    """
    h = _resume_hash(resume_text)
    cached = _load_cache(h)
    if cached is not None:
        logger.info(f"简历缓存命中: keywords={len(cached.get('keywords', []))} "
                    f"fit_directions={len(cached.get('fit_directions', []))}")
        return cached

    from llm_client import LLMClient
    client = llm_client or LLMClient()

    prompt = _RESUME_PARSE_PROMPT.format(
        resume_text=resume_text[:12000],
        job_tree_block=job_tree.prompt_block(),
    )

    try:
        raw = client._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=8000,
        )
        raw_keywords, raw_dirs = _parse_llm_output(raw)
        if not raw_keywords and not raw_dirs:
            logger.warning(f"简历 LLM 解析返回空: {raw[:200]}")
            return {"keywords": [], "fit_directions": []}

        keywords = _normalize_keywords(raw_keywords)
        fit_directions = _validate_fit_directions(raw_dirs)
        result = {"keywords": keywords, "fit_directions": fit_directions}
        _save_cache(h, result)
        logger.info(f"简历解析完成: keywords {len(raw_keywords)}→{len(keywords)}, "
                    f"fit_directions {len(raw_dirs)}→{len(fit_directions)}")
        return result

    except Exception as e:
        logger.error(f"简历 LLM 解析失败: {e}")
        return {"keywords": [], "fit_directions": []}


def apply_keywords_to_profile(profile, result: Dict):
    """
    将解析结果应用到 UserProfile。

    result: {"keywords": [...], "fit_directions": [...]}
    - structured_keywords: keywords 列表
    - fit_directions: 适配岗位方向列表(新版 role 维度)
    - core_skills / direction_keywords: 旧字段向后兼容
    """
    keywords = result.get("keywords", []) if isinstance(result, dict) else result
    profile.structured_keywords = keywords

    # 新版:适配方向
    if isinstance(result, dict):
        profile.fit_directions = result.get("fit_directions", [])
    else:
        profile.fit_directions = getattr(profile, "fit_directions", []) or []

    # 旧字段向后兼容
    core = []
    direction: Dict[str, List[str]] = {}
    for tag in keywords:
        cat = tag.get("category", "")
        std = tag.get("standard") or tag.get("kw", "")
        if cat in ("hard_skill", "tool", "framework"):
            core.append(std)
        elif cat == "role":
            direction.setdefault("role", []).append(std)
        elif cat == "domain":
            direction.setdefault("domain", []).append(std)
        elif cat == "skill":
            direction.setdefault("skill", []).append(std)

    profile.core_skills = list(dict.fromkeys(core))
    profile.direction_keywords = {k: list(dict.fromkeys(v)) for k, v in direction.items()}
    return profile
