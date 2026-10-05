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


def _validate_fit_directions(raw_dirs: List[Dict], allow_category: bool = False) -> List[Dict]:
    """校验 fit_directions 的 direction 必须是树中子类名(或大类名,allow_category=True 时)。

    非法的丢弃并记日志。
    - 子类命中: cat_key + sub_key 都有
    - 大类命中: 只有 cat_key,sub_key=None(同大类匹配系数 0.6)
    """
    valid = []
    for d in raw_dirs:
        direction = (d.get("direction") or "").strip()
        if not direction:
            continue
        entry = job_tree.resolve(direction, allow_category=allow_category)
        if entry is None:
            logger.warning(f"fit_directions 非法 direction 丢弃: {direction!r} (不在树中)")
            continue
        if entry.get("type") not in ("subcategory", "category"):
            logger.warning(f"fit_directions 非法 type 丢弃: {direction!r}")
            continue
        try:
            weight = float(d.get("weight") or 0.0)
        except (TypeError, ValueError):
            weight = 0.0
        weight = max(0.0, min(1.0, weight))
        if weight < 0.3:
            continue
        item = {
            "direction": entry.get("sub_name") or entry.get("category_name") or direction,
            "cat_key": entry["cat_key"],
            "sub_key": entry.get("sub_key"),  # 大类时为 None
            "category_name": entry.get("category_name", ""),
            "weight": round(weight, 2),
            "evidence": (d.get("evidence") or "").strip()[:200],
        }
        valid.append(item)
    # 按权重降序,最多保留 8 个
    valid.sort(key=lambda x: -x["weight"])
    return valid[:8]


def parse_resume_text(resume_text: str, llm_client=None,
                      raise_on_error: bool = False) -> Dict:
    """
    从简历文本解析生成结构化关键词 + 适配岗位方向。

    Args:
        resume_text: 简历原文
        llm_client: LLMClient 实例(None 则新建)
        raise_on_error: True 时 LLM 调用失败/返回空 抛 RuntimeError,
            供云端 API 路由层映射为 503;False(默认)时兼容旧脚本,
            失败返回空 {"keywords": [], "fit_directions": []}。

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

    # LLM 调用失败时 _chat 返回 None
    def _fail(msg: str) -> Dict:
        if raise_on_error:
            raise RuntimeError(msg)
        return {"keywords": [], "fit_directions": []}

    try:
        raw = client._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=8000,
        )
    except Exception as e:
        logger.error(f"简历 LLM 解析异常: {e}")
        return _fail(f"简历 LLM 解析异常: {e}")

    if raw is None:
        logger.error("简历 LLM 解析失败: API 返回空(可能 API Key 无效或服务不可用)")
        return _fail("简历 LLM 解析失败: API 返回空(可能 API Key 无效或服务不可用)")

    try:
        raw_keywords, raw_dirs = _parse_llm_output(raw)
    except Exception as e:
        logger.error(f"简历 LLM 输出解析失败: {e}; raw={raw[:200]}")
        return _fail(f"简历 LLM 输出解析失败: {e}")

    if not raw_keywords and not raw_dirs:
        logger.warning(f"简历 LLM 解析返回空: {raw[:200]}")
        return _fail("简历 LLM 解析返回空结果(可能简历内容不足)")

    keywords = _normalize_keywords(raw_keywords)
    fit_directions = _validate_fit_directions(raw_dirs)
    result = {"keywords": keywords, "fit_directions": fit_directions}
    _save_cache(h, result)
    logger.info(f"简历解析完成: keywords {len(raw_keywords)}→{len(keywords)}, "
                f"fit_directions {len(raw_dirs)}→{len(fit_directions)}")
    return result


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


def supplement_profile(user_edited: Dict, resume_text: str = "",
                       llm_client=None, raise_on_error: bool = False) -> Dict:
    """第二轮:根据用户编辑后的完整画像,AI 补充分析方向 + 硬技能。

    流程:
    1. 从 user_edited 提取用户编辑后的完整画像(方向/技能/公司/城市/行业)
    2. 只要用户有方向,就调用 LLM supplement_from_edits 做补充分析
       (不要求必须有新增方向,编辑技能/公司/城市也会触发补充技能推荐)
    3. 校验方向合法性(允许大类),合并去重
    4. 把新硬技能并入 structured_keywords(去重,标记 source=ai_supplemented)

    Args:
        user_edited: 用户编辑后的画像 dict,含 directions(List[str])、
                     fit_directions(List[Dict])、structured_keywords(List[Dict])、
                     skills(List[str])、companies(List[str])、cities(List[str])
        resume_text: 原始简历文本
        llm_client: LLMClient 实例

    Returns:
        {"fit_directions": [...], "structured_keywords": [...],
         "new_directions": [...], "new_skills": [...]}
    """
    directions = user_edited.get("directions") or []
    existing_dirs = user_edited.get("fit_directions") or []
    existing_keywords = user_edited.get("structured_keywords") or []

    # 没有方向则无法补充
    if not directions:
        return {
            "fit_directions": existing_dirs,
            "structured_keywords": existing_keywords,
            "new_directions": [],
            "new_skills": [],
        }

    from llm_client import LLMClient
    client = llm_client or LLMClient()

    # 基于用户完整编辑后的画像做补充分析(方向/技能/公司/城市都会被考虑)
    result = client.supplement_from_edits(
        user_edited=user_edited,
        resume_text=resume_text,
        raise_on_error=raise_on_error,
    )

    # 校验新方向(允许大类)
    new_dirs = _validate_fit_directions(result.get("fit_directions", []),
                                        allow_category=True)

    # 合并 fit_directions:已有 + 新增(按 direction 去重,保留权重大的)
    merged_dirs = {d["direction"]: d for d in existing_dirs if isinstance(d, dict)}
    for nd in new_dirs:
        name = nd["direction"]
        if name in merged_dirs:
            if nd["weight"] > merged_dirs[name]["weight"]:
                merged_dirs[name] = nd
        else:
            merged_dirs[name] = nd
    final_dirs = sorted(merged_dirs.values(), key=lambda x: -x["weight"])

    # 合并 hard_skills 到 structured_keywords
    existing_kw_set = set()
    for k in existing_keywords:
        if isinstance(k, dict):
            existing_kw_set.add((k.get("standard") or k.get("kw", "")).lower())

    new_skills = []
    for s in result.get("hard_skills", []):
        kw = (s.get("kw") or "").strip()
        if not kw:
            continue
        std, hit = keyword_normalizer_normalize(kw)
        canonical = std if hit else kw.lower()
        if canonical in existing_kw_set:
            continue
        existing_kw_set.add(canonical)
        tag = {
            "kw": kw,
            "standard": std if hit else kw,
            "category": "hard_skill",
            "weight": round(float(s.get("weight") or 2.5), 2),
            "resume_section": "other",
            "source": "ai_supplemented",
        }
        new_skills.append(tag)

    final_keywords = list(existing_keywords) + new_skills

    return {
        "fit_directions": final_dirs,
        "structured_keywords": final_keywords,
        "new_directions": new_dirs,
        "new_skills": new_skills,
    }


def keyword_normalizer_normalize(kw: str):
    """封装 keyword_normalizer.normalize,避免顶层循环 import。"""
    from keyword_normalizer import normalize
    return normalize(kw)
