"""
LLM 岗位拆分器 — 从招聘公告正文用 DeepSeek 提取结构化岗位列表。

设计原则(对抗性审查):
1. LLM 唯一职责:公告正文 → 岗位列表(非结构化→结构化)
2. 缓存:内容 hash → LLM 结果文件,避免重复调用(成本控制)
3. 增量:只处理 crawl_status=success 且 llm_status=pending 的公告
4. 降级:LLM 失败时用公告标题作为单一岗位,不阻塞管线
5. 限速 + 重试上限 3 次,控制成本

数据流:
  announcement(crawl_status=success) → 读缓存正文
  → DeepSeek 拆岗 → 写 positions 表 → 更新 llm_status=success
"""
import hashlib
import json
import logging
import os
import time
from typing import Dict, List, Optional, Tuple

from config import settings
from llm_client import LLMClient
import job_db
import job_tree
from content_fetcher import get_cached_content, fetch_content, fetch_content_full

logger = logging.getLogger(__name__)

LLM_CACHE_DIR = os.path.join(settings.DATA_DIR, "llm_cache")
MAX_RETRIES = 3
API_INTERVAL = 1.0  # 秒,LLM 调用间隔(控成本+避限流)

POSITION_EXTRACT_PROMPT = """你是校招信息解析专家。请从以下招聘公告中提取所有可独立投递的具体岗位,并填入结构化字段。

公司: {company}
公告标题: {title}

【源表元数据 — 仅供参考,若与公告正文冲突以正文为准】
招聘类型: {recruit_type}
招聘对象: {recruit_target}
届数范围: {grade_range}
行业: {industry}
公司类型: {company_type}
招聘地点: {location}
学历要求: {education_req}

公告内容:
\"\"\"{content}\"\"\"

请输出 JSON 数组(严格 JSON,不要输出任何 JSON 以外的文字):
[
  {{
    "position_title": "岗位名称(具体岗位名,如:Java开发工程师/产品经理/管培生,不要用公告标题)",
    "job_category": "岗位大类(从下方岗位类型树的大类名选1个最贴切的)",
    "job_subcategory": "岗位子类(从下方岗位类型树的子类名选1个最贴切的;若岗位描述不具体无法确定子类,填所属大类名;实在无法判断填空字符串)",
    "hard_skills": ["硬技能列表,如:Python/Java/SQL/机器学习,无则空数组"],
    "soft_skills": ["软技能列表,如:沟通/团队协作,无则空数组"],
    "certifications": ["证书要求,如:CFA/CPA/法律职业资格,无则空数组"],
    "languages": ["语言要求,如:英语CET-6,无则空数组"],
    "major_required": "具体专业要求(如:计算机科学与技术/软件工程,无明确要求填'不限')",
    "major_category": "专业大类(工科/理科/商科/文科/医科/农学/艺术/不限,选1个)",
    "min_education": "最低学历(大专/本科/硕士/博士/不限)",
    "city": "工作城市(如:北京/上海/深圳,多个用逗号分隔,无则空字符串)",
    "province": "工作省份(如:广东/浙江,无则空字符串)",
    "has_written_test": false,
    "responsibilities": "岗位职责(100字内,无则空字符串)",
    "requirements": "任职要求(100字内,无则空字符串)",
    "bonus_points": "加分项(50字内,无则空字符串)",
    "keywords": ["关键词标签,用于匹配,如:Python/机器学习/大厂,提取3-8个"],
    "jd_summary": "岗位摘要(60字内)",
    "is_management_trainee": false,
    "difficulty": "难度(最激烈/较为激烈/中等难度/较低难度)",
    "company_tier": "公司行业地位(顶/中/保底,根据公司在行业内的知名度、规模、招聘竞争度判断;不确定填'中')",
    "apply_url": "独立投递链接(无则空字符串)"
  }}
]

提取规则(严格遵守):

【岗位类型树 — job_category / job_subcategory 取值依据】
{job_tree_block}

★ job_category 必须填上面的大类名;job_subcategory 优先填子类名,若岗位描述不具体无法确定子类则填所属大类名,实在无法判断填空。不要填树以外的自造词。

0. 【核心铁律】只提取公告内容/标题中明确出现的岗位。严禁编造、推断、补充任何未在正文中出现的岗位名称。若正文/标题中没有具体岗位名,输出空数组 []。
1. 识别所有可独立投递的具体岗位;每个岗位必须是数组中的一个独立对象,严禁把多个岗位名拼成一个字符串。若只有大类无具体岗位名,拆为"通用校招岗"。
2. is_management_trainee: 管培生/管理培训生/MT/培训生 标记为 true
3. difficulty: 头部互联网/金融/知名外企=最激烈;中型公司=较为激烈;普通=中等;冷门=较低
4. keywords 必须包含岗位核心技能/方向词,用于后续匹配
5. min_education 取最低可投递学历(如"本科及以上"填"本科")
6. company_tier: 根据公司在行业内的知名度/规模/招聘竞争度判断公司地位
   - 顶: 行业头部(如BAT/华为/大疆/中金/高盛/宁德时代等),校招竞争极激烈
   - 中: 行业内有一定知名度的中型公司
   - 保底: 普通中小公司
   - 不确定时填"中"

7. 【字段填充策略】分三个层次处理,最大化字段填充率:
   a) 明确信息:正文/标题中明确提到的,直接提取
   b) 合理推断(允许):根据岗位类型和上下文可合理推断的,填入并标注
      - 校招岗位学历通常为"本科"(除非明确要求硕士/博士,或明确写"专业不限"),可填"本科"
      - 技术研发类岗位专业大类通常为"工科",金融类为"商科",设计类为"艺术"
      - 岗位所在城市可从公司总部或招聘地点推断
      - 岗位职责可根据岗位名称做简要概括(如"负责Java后端开发工作")
   c) 无法推断:确实无法确定的,留空(字符串字段)或空数组(数组字段)

7. major_required: 有明确专业要求就填具体专业;没有明确要求但岗位有倾向性(如研发岗),填"计算机相关"等合理范围;完全无要求填"不限"。
8. responsibilities: 有明确职责就摘录;无明确职责但可从岗位名推断的,写一句简要职责(如"负责产品设计与迭代");完全无法推断才留空。
9. jd_summary: 基于岗位名+已提取的职责/要求,生成60字内摘要,不要留空。
10. hard_skills: 从职责/要求中提取技能关键词;无明确技能但可从岗位推断的(如Java岗→["Java"]);完全无法推断才空数组。
"""


# 源表岗位名填字段 prompt:输入是源表「招聘岗位」字段(已是岗位/类别列表),
# 无需 LLM 从长文"提取"岗位名,只需解析列表并填充结构化字段。
POSITION_FILL_PROMPT = """你是校招信息解析专家。以下是某公司招聘公告源表中的「招聘岗位」字段内容,
该字段可能包含:具体岗位名、岗位类别(如"技术类")、岗位方向(如"AI方向")、招聘专业列表等。
请解析其中的岗位信息,并为每个岗位填入结构化字段。

公司: {company}
招聘岗位字段原文: {title}

【源表元数据 — 用于辅助填充字段】
招聘类型: {recruit_type}
招聘对象: {recruit_target}
届数范围: {grade_range}
行业: {industry}
公司类型: {company_type}
招聘地点: {location}
学历要求: {education_req}

招聘岗位字段内容:
\"\"\"{content}\"\"\"

请输出 JSON 数组(严格 JSON,不要输出任何 JSON 以外的文字):
[
  {{
    "position_title": "岗位名称(具体岗位名,如:Java开发工程师/产品经理/管培生)",
    "job_category": "岗位大类(从下方岗位类型树的大类名选1个最贴切的)",
    "job_subcategory": "岗位子类(从下方岗位类型树的子类名选1个最贴切的;若岗位描述不具体无法确定子类,填所属大类名;实在无法判断填空字符串)",
    "hard_skills": ["硬技能列表,如:Python/Java/SQL/机器学习,无则空数组"],
    "soft_skills": ["软技能列表,如:沟通/团队协作,无则空数组"],
    "certifications": ["证书要求,如:CFA/CPA/法律职业资格,无则空数组"],
    "languages": ["语言要求,如:英语CET-6,无则空数组"],
    "major_required": "具体专业要求(如:计算机科学与技术/软件工程,无明确要求填'不限')",
    "major_category": "专业大类(工科/理科/商科/文科/医科/农学/艺术/不限,选1个)",
    "min_education": "最低学历(大专/本科/硕士/博士/不限)",
    "city": "工作城市(如:北京/上海/深圳,多个用逗号分隔,无则空字符串)",
    "province": "工作省份(如:广东/浙江,无则空字符串)",
    "has_written_test": false,
    "responsibilities": "岗位职责(100字内,无则空字符串)",
    "requirements": "任职要求(100字内,无则空字符串)",
    "bonus_points": "加分项(50字内,无则空字符串)",
    "keywords": ["关键词标签,用于匹配,如:Python/机器学习/大厂,提取3-8个"],
    "jd_summary": "岗位摘要(60字内)",
    "is_management_trainee": false,
    "difficulty": "难度(最激烈/较为激烈/中等难度/较低难度)",
    "company_tier": "公司行业地位(顶/中/保底,根据公司在行业内的知名度、规模、招聘竞争度判断;不确定填'中')",
    "apply_url": "独立投递链接(无则空字符串)"
  }}
]

解析与填充规则(严格遵守):

【岗位类型树 — job_category / job_subcategory 取值依据】
{job_tree_block}

★ job_category 必须填上面的大类名;job_subcategory 优先填子类名,若岗位描述不具体无法确定子类则填所属大类名,实在无法判断填空。不要填树以外的自造词。

0. 【核心任务】解析「招聘岗位」字段,识别其中所有可投递的岗位/类别,每个输出为数组中的独立对象。
   - 字段中可能用空格、顿号(、)、逗号(,)、分号(;)、斜杠(/)分隔多个岗位,请逐个拆分。
   - 若字段内容是岗位类别(如"技术类""产品类""运营类"),请展开为该类别下的具体岗位名(如"技术类"→"技术研发工程师",结合公司行业判断)。
   - 若字段内容是专业列表(如"计算机、软件工程、电子信息"),这是招聘专业而非岗位,请结合公司行业推断对应岗位(如"计算机"→"软件开发工程师"),并把专业填入 major_required。
   - 若字段内容模糊或重定向(如"详见附件""具体岗位见链接""未明确""高校毕业生"),输出一个"通用校招岗"。
   - 严禁输出空数组 []。至少输出一个岗位(实在无法判断时输出"通用校招岗")。

1. is_management_trainee: 管培生/管理培训生/MT/培训生 标记为 true
2. difficulty: 头部互联网/金融/知名外企=最激烈;中型公司=较为激烈;普通=中等;冷门=较低
3. keywords 必须包含岗位核心技能/方向词,用于后续匹配
4. min_education 取最低可投递学历(如"本科及以上"填"本科"),无明确要求填"本科"(校招默认)
5. company_tier: 根据公司在行业内的知名度/规模/招聘竞争度判断公司地位
   - 顶: 行业头部(如BAT/华为/大疆/中金/高盛/宁德时代等),校招竞争极激烈
   - 中: 行业内有一定知名度的中型公司
   - 保底: 普通中小公司
   - 不确定时填"中"

6. 【字段填充策略】分三个层次处理,最大化字段填充率:
   a) 明确信息:字段中明确提到的,直接提取
   b) 合理推断(允许):根据岗位类型和公司信息可合理推断的,填入
      - 校招岗位学历通常为"本科"(除非明确要求硕士/博士)
      - 技术研发类岗位专业大类通常为"工科",金融类为"商科",设计类为"艺术"
      - 岗位所在城市可从招聘地点推断
      - 岗位职责可根据岗位名称做简要概括(如"负责Java后端开发工作")
   c) 无法推断:确实无法确定的,留空(字符串字段)或空数组(数组字段)

7. major_required: 有明确专业要求就填具体专业;没有明确要求但岗位有倾向性(如研发岗),填"计算机相关"等合理范围;完全无要求填"不限"。
8. responsibilities: 无明确职责但可从岗位名推断的,写一句简要职责;完全无法推断才留空。
9. jd_summary: 基于岗位名+公司信息,生成60字内摘要,不要留空。
10. hard_skills: 可从岗位推断的(如Java岗→["Java"]);完全无法推断才空数组。
"""


def _content_hash(content: str, company: str = "", title: str = "") -> str:
    """计算内容 hash,作为 LLM 缓存键。

    关键设计: hash 必须包含 company 和 title,而非仅 content。
    原因:微信反爬会导致大量公告的 content 完全相同(都是"环境异常"垃圾页),
    若仅按 content 缓存,不同公司会共用同一份 LLM 结果,造成跨公司岗位污染。
    """
    key = f"{company}||{title}||{content}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()


# 垃圾内容特征(微信反爬/UI噪声),命中则视为无正文
_GARBAGE_CONTENT_MARKERS = [
    "环境异常", "当前环境异常", "完成验证后即可继续访问", "去验证",
    "点击公众号下方菜单栏", "轻点两下取消赞", "轻点两下取消在看",
]


def _is_garbage_content(content: str) -> bool:
    """判断 content 是否为反爬垃圾/UI噪声,不能作为拆岗依据。"""
    if not content or len(content.strip()) < 10:
        return True
    for marker in _GARBAGE_CONTENT_MARKERS:
        if marker in content:
            return True
    return False


def _llm_cache_path(content_hash: str) -> str:
    return os.path.join(LLM_CACHE_DIR, f"{content_hash}.json")


def _get_cached_llm_result(content_hash: str) -> Optional[List[Dict]]:
    """读取 LLM 结果缓存。"""
    path = _llm_cache_path(content_hash)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _save_llm_result(content_hash: str, positions: List[Dict]):
    """缓存 LLM 结果。"""
    os.makedirs(LLM_CACHE_DIR, exist_ok=True)
    try:
        with open(_llm_cache_path(content_hash), "w", encoding="utf-8") as f:
            json.dump(positions, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"LLM 结果缓存失败: {e}")


class PositionEnricher:
    """LLM 岗位拆分器。"""

    def __init__(self, llm_client: LLMClient = None):
        self.llm = llm_client or LLMClient()

    def extract_positions(self, content: str, company: str = "",
                          title: str = "", meta: Optional[Dict] = None) -> List[Dict]:
        """
        从公告正文用 LLM 提取岗位列表。
        带缓存:相同 (company+title+content) hash 不重复调用。
        失败返回空列表(由调用方降级处理)。

        关键防幻觉设计:
        1. 缓存键包含 company+title+content,防止不同公司共用垃圾内容的缓存
        2. 提取后校验岗位名是否出现在源文本中,过滤纯幻觉岗位

        Args:
            meta: 源表元数据 dict,可选字段: recruit_type, recruit_target,
                  min_grade, max_grade, industry_raw, company_type_raw,
                  location, education_req
        """
        if not content or len(content.strip()) < 30:
            return []

        meta = meta or {}
        # 源文本(用于岗位名回查校验,防止 LLM 编造不存在的岗位)
        source_text = f"{title}\n{content}"

        c_hash = _content_hash(content, company=company, title=title)

        # 1. 查缓存
        cached = _get_cached_llm_result(c_hash)
        if cached is not None:
            logger.debug(f"LLM 缓存命中: {company} ({len(cached)} 岗位)")
            return self._validate_positions(cached, source_text)

        # 2. 构建源表元数据字符串(注入 prompt,辅助 LLM 理解公告上下文)
        min_g = meta.get("min_grade")
        max_g = meta.get("max_grade")
        if min_g and max_g:
            grade_range = f"{min_g}-{max_g}届" if min_g != max_g else f"{min_g}届"
        elif min_g:
            grade_range = f"{min_g}届起"
        elif max_g:
            grade_range = f"{max_g}届止"
        else:
            grade_range = "不限"

        # 3. 调用 LLM(带重试)
        prompt = POSITION_EXTRACT_PROMPT.format(
            company=company or "未知",
            title=title or "",
            recruit_type=meta.get("recruit_type", "") or "—",
            recruit_target=meta.get("recruit_target", "") or "—",
            grade_range=grade_range,
            industry=meta.get("industry_raw", "") or meta.get("industry", "") or "—",
            company_type=meta.get("company_type_raw", "") or meta.get("company_type", "") or "—",
            location=meta.get("location", "") or "—",
            education_req=meta.get("education_req", "") or "—",
            content=content[:8000],  # 截断控制成本(校招公告通常 2000-6000 字)
            job_tree_block=job_tree.prompt_block(),
        )

        for attempt in range(MAX_RETRIES):
            try:
                result_text = self.llm._chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.1, max_tokens=16000,
                )
                if not result_text:
                    raise ValueError("LLM 返回空")

                positions = self._parse_positions(result_text)
                if positions:
                    # 校验岗位名是否出现在源文本中,过滤幻觉
                    positions = self._validate_positions(positions, source_text)
                    if positions:
                        _save_llm_result(c_hash, positions)
                        return positions
                    logger.warning(f"LLM 提取岗位全部未通过源文本校验(尝试 {attempt + 1})")
                else:
                    # 解析为空,可能是 LLM 输出异常,重试
                    logger.warning(f"LLM 输出解析为空(尝试 {attempt + 1}): {result_text[:200]}")
            except Exception as e:
                logger.warning(f"LLM 拆岗失败(尝试 {attempt + 1}/{MAX_RETRIES}) [{company}]: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"LLM 拆岗彻底失败 [{company}]")
                    return []

        return []

    def extract_positions_from_title(self, position_text: str, company: str = "",
                                     title: str = "", meta: Optional[Dict] = None) -> List[Dict]:
        """从源表「招聘岗位」字段解析并填充岗位字段。

        与 extract_positions 的区别:
        - 输入是源表已有的岗位/类别列表,不是公告正文,无需"提取"岗位名
        - 不设 30 字长度门槛(岗位名可能很短)
        - 使用 POSITION_FILL_PROMPT(解析列表 + 填字段)
        - 校验更宽松(允许类别展开,如"技术类"→"技术研发工程师")
        - 长标题(>500字)分块处理,避免 LLM 输出超长被截断

        Args:
            position_text: 源表「招聘岗位」字段原文
            meta: 源表元数据 dict
        """
        if not position_text or len(position_text.strip()) < 1:
            return []

        meta = meta or {}
        source_text = f"{title}\n{position_text}"

        c_hash = _content_hash(position_text, company=company, title=title)

        # 1. 查缓存
        cached = _get_cached_llm_result(c_hash)
        if cached is not None:
            logger.debug(f"标题填字段缓存命中: {company} ({len(cached)} 岗位)")
            return self._validate_positions_from_title(cached, source_text)

        # 2. 构建元数据字符串
        min_g = meta.get("min_grade")
        max_g = meta.get("max_grade")
        if min_g and max_g:
            grade_range = f"{min_g}-{max_g}届" if min_g != max_g else f"{min_g}届"
        elif min_g:
            grade_range = f"{min_g}届起"
        elif max_g:
            grade_range = f"{max_g}届止"
        else:
            grade_range = "不限"

        meta_kwargs = dict(
            company=company or "未知",
            title=title or "",
            recruit_type=meta.get("recruit_type", "") or "—",
            recruit_target=meta.get("recruit_target", "") or "—",
            grade_range=grade_range,
            industry=meta.get("industry_raw", "") or meta.get("industry", "") or "—",
            company_type=meta.get("company_type_raw", "") or meta.get("company_type", "") or "—",
            location=meta.get("location", "") or "—",
            education_req=meta.get("education_req", "") or "—",
            job_tree_block=job_tree.prompt_block(),
        )

        # 3. 长标题分块:>500字时按分隔符切成 ~400字的块,逐块调 LLM
        if len(position_text) > 500:
            chunks = self._split_title_chunks(position_text, max_len=400)
            logger.info(f"公告标题过长({len(position_text)}字),分 {len(chunks)} 块处理")
            all_positions = []
            for chunk in chunks:
                positions = self._call_fill_llm(chunk, source_text, meta_kwargs)
                all_positions.extend(positions)
            if all_positions:
                all_positions = self._validate_positions_from_title(all_positions, source_text)
            if all_positions:
                _save_llm_result(c_hash, all_positions)
                return all_positions
            return []

        # 4. 普通标题:单次调用
        positions = self._call_fill_llm(position_text, source_text, meta_kwargs)
        if positions:
            positions = self._validate_positions_from_title(positions, source_text)
        if positions:
            _save_llm_result(c_hash, positions)
            return positions
        return []

    @staticmethod
    def _split_title_chunks(text: str, max_len: int = 400) -> List[str]:
        """将长标题按分隔符切成不超过 max_len 的块。"""
        import re
        # 按常见分隔符切分,保留分隔符
        parts = re.split(r'([、,，;；\n])', text)
        chunks = []
        current = ""
        for part in parts:
            if len(current) + len(part) > max_len and current.strip():
                chunks.append(current.strip())
                current = part
            else:
                current += part
        if current.strip():
            chunks.append(current.strip())
        return chunks

    def _call_fill_llm(self, position_text: str, source_text: str,
                       meta_kwargs: Dict) -> List[Dict]:
        """单次调用 LLM 填字段,带重试。返回解析后的岗位列表(未校验)。"""
        for attempt in range(MAX_RETRIES):
            try:
                prompt = POSITION_FILL_PROMPT.format(
                    content=position_text[:4000],
                    **meta_kwargs,
                )
                result_text = self.llm._chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.1, max_tokens=32000,
                )
                if not result_text:
                    raise ValueError("LLM 返回空")
                positions = self._parse_positions(result_text)
                if positions:
                    return positions
                logger.warning(f"标题填字段解析为空(尝试 {attempt + 1}): {result_text[:200]}")
            except Exception as e:
                logger.warning(f"标题填字段失败(尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
        return []

    @staticmethod
    def _validate_positions_from_title(positions: List[Dict], source_text: str) -> List[Dict]:
        """源表标题路径的岗位校验。

        岗位名来自标题本身,LLM 只是解析+展开,幻觉风险较低。
        策略:
        - 源文本较短(<15字)时跳过校验:短标题常被 LLM 合理展开
          (如"人资岗"→"人力资源岗"),严格校验会误杀。
        - 源文本较长时:岗位名整体/片段/2字子串出现在源文本中才通过,
          防止 LLM 从长标题中凭空编造无关岗位。
        - "通用校招岗"始终通过(模糊标题的兜底)。
        """
        if not positions:
            return []
        text_norm = source_text.replace(" ", "").replace("\u3000", "").replace("\n", "")
        # 短标题:跳过严格校验,允许 LLM 展开
        if len(text_norm) < 15:
            return positions
        valid = []
        for pos in positions:
            ptitle = (pos.get("position_title") or "").strip()
            if not ptitle:
                continue
            if ptitle in ("通用校招岗", "校招岗位"):
                valid.append(pos)
                continue
            ptitle_norm = ptitle.replace(" ", "").replace("\u3000", "")
            # 整体匹配
            if ptitle_norm in text_norm:
                valid.append(pos)
                continue
            # 拆分匹配
            parts = [p for p in ptitle_norm.replace("、", "/").replace(",", "/").split("/") if p]
            if any(p and len(p) >= 2 and p in text_norm for p in parts):
                valid.append(pos)
                continue
            # 子串重叠匹配
            _overlap = False
            for i in range(len(ptitle_norm) - 1):
                sub = ptitle_norm[i:i + 2]
                if sub in text_norm:
                    _overlap = True
                    break
            if _overlap:
                valid.append(pos)
                continue
            logger.debug(f"过滤幻觉岗位(标题路径): {ptitle} (与源文本无重叠)")
        return valid

    @staticmethod
    def _validate_positions(positions: List[Dict], source_text: str) -> List[Dict]:
        """校验岗位名是否出现在源文本中,过滤 LLM 编造的幻觉岗位。

        策略:
        - 岗位名必须在 source_text(title+content) 中出现(子串匹配)
        - 允许"通用校招岗"通过(这是降级兜底,非幻觉)
        - 岗位名中常见分隔符(、/,)拆分后,只要任一片段命中即通过
          (因为 LLM 可能输出"Java开发工程师"而原文是"Java 开发工程师")
        """
        if not positions:
            return []
        # 预处理源文本:去空白,方便匹配
        text_norm = source_text.replace(" ", "").replace("\u3000", "").replace("\n", "")
        valid = []
        for pos in positions:
            title = (pos.get("position_title") or "").strip()
            if not title:
                continue
            # 兜底岗位直接通过
            if title in ("通用校招岗", "校招岗位"):
                valid.append(pos)
                continue
            # 去掉常见后缀再匹配
            title_norm = title.replace(" ", "").replace("\u3000", "")
            # 整体匹配
            if title_norm in text_norm:
                valid.append(pos)
                continue
            # 拆分匹配(、/, 等分隔符)
            parts = [p for p in title_norm.replace("、", "/").replace(",", "/").split("/") if p]
            if any(p and len(p) >= 2 and p in text_norm for p in parts):
                valid.append(pos)
                continue
            # 未命中源文本 → 幻觉,丢弃
            logger.debug(f"过滤幻觉岗位: {title} (未在源文本中找到)")
        return valid

    @staticmethod
    def _parse_positions(text: str) -> List[Dict]:
        """解析 LLM 输出为岗位列表。

        兼容多种返回格式:
        1. 直接 JSON 数组: [{...}, {...}]
        2. 单 JSON 对象: {...}
        3. DeepSeek json_object 信封: {"type":"json_object","content":"[{...}]"}
        4. DeepSeek json_object 信封: {"type":"json_object","value":[{...}]}
        """
        if not text:
            return []
        text = text.strip()
        # 去除 markdown 包裹
        import re
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        # 先尝试整体解析为 JSON(处理信封格式)
        try:
            obj = json.loads(text)
            if isinstance(obj, list):
                return [d for d in obj if isinstance(d, dict)]
            if isinstance(obj, dict):
                # 信封格式: {"type":"json_object","content":[...]} (content 直接是数组)
                if "content" in obj:
                    c = obj["content"]
                    if isinstance(c, list):
                        return [d for d in c if isinstance(d, dict)]
                    if isinstance(c, dict):
                        # content 内部可能还有 positions/jobs/data 包裹
                        for wrap_key in ("positions", "jobs", "data", "items", "result"):
                            if wrap_key in c:
                                val = c[wrap_key]
                                if isinstance(val, list):
                                    return [d for d in val if isinstance(d, dict)]
                                if isinstance(val, dict):
                                    return [val]
                        return [c]
                    if isinstance(c, str):
                        inner = json.loads(c)
                        if isinstance(inner, list):
                            return [d for d in inner if isinstance(d, dict)]
                        if isinstance(inner, dict):
                            return [inner]
                # 信封格式: {"type":"json_object","value":[...]}
                if "value" in obj:
                    val = obj["value"]
                    if isinstance(val, list):
                        return [d for d in val if isinstance(d, dict)]
                    if isinstance(val, dict):
                        return [val]
                # LLM 包裹格式: {"positions": [...]} 或 {"jobs": [...]} 或 {"data": [...]}
                for wrap_key in ("positions", "jobs", "data", "items", "result"):
                    if wrap_key in obj:
                        val = obj[wrap_key]
                        if isinstance(val, list):
                            return [d for d in val if isinstance(d, dict)]
                        if isinstance(val, dict):
                            return [val]
                # 普通单对象
                return [obj]
        except json.JSONDecodeError:
            pass  # 整体解析失败,尝试提取数组

        # 提取 JSON 数组
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
                if isinstance(data, list):
                    return [d for d in data if isinstance(d, dict)]
                if isinstance(data, dict):
                    return [data]
            except json.JSONDecodeError:
                pass

        # 提取单 JSON 对象
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                obj = json.loads(text[start:end + 1])
                if isinstance(obj, dict):
                    # 再次检查信封(content 可能是 list/dict/str)
                    if "content" in obj:
                        c = obj["content"]
                        if isinstance(c, list):
                            return [d for d in c if isinstance(d, dict)]
                        if isinstance(c, dict):
                            return [c]
                        if isinstance(c, str):
                            try:
                                inner = json.loads(c)
                                if isinstance(inner, list):
                                    return [d for d in inner if isinstance(d, dict)]
                                if isinstance(inner, dict):
                                    return [inner]
                            except json.JSONDecodeError:
                                pass
                    if "value" in obj:
                        val = obj["value"]
                        if isinstance(val, list):
                            return [d for d in val if isinstance(d, dict)]
                    return [obj]
            except json.JSONDecodeError:
                pass

        return []

    def _degrade_to_single_position(self, announcement: Dict) -> List[Dict]:
        """
        降级:LLM 失败时,用公告标题作为单一岗位。
        保证管线不中断,后续可重试 LLM。
        """
        title = announcement.get("announcement_title", "") or "通用校招岗"
        return [{
            "position_title": title.strip()[:100] or "通用校招岗",
            "location": announcement.get("location", ""),
            "education_req": announcement.get("education_req", ""),
            "major_req": "",
            "jd_summary": "",
            "is_management_trainee": False,
            "difficulty": "",
            "company_tier": "",
            "apply_url": announcement.get("apply_url", ""),
        }]

    def enrich_announcement(self, announcement: Dict) -> int:
        """
        处理单条公告:用源表岗位名填字段 → LLM 拆岗 → 写 positions → 更新状态。
        返回插入的岗位数。
        """
        ann_id = announcement["id"]
        company_name = announcement.get("company_name", "")
        ann_title = announcement.get("announcement_title", "")
        ann_url = announcement.get("announcement_url", "")

        # 1. 直接用源表岗位名填字段（源表「招聘岗位」字段已含岗位列表,无需抓正文）
        content = ""
        images_json = ""

        # 1.5 图片不抓取（源表模式不需要）
        local_images = []
        all_images = []

        # 2. 源表模式:直接用「招聘岗位」字段填字段,不走正文/VL
        job_db.update_vl_status(ann_id, "not_needed")
        content_is_garbage = False

        # 直接用源表岗位名填字段
        if ann_title:
            logger.info(f"公告 {ann_id} [{company_name}] 源表岗位名填字段")
            positions = self.extract_positions_from_title(
                ann_title, company=company_name, title=ann_title, meta=announcement
            )
            c_hash = _content_hash(ann_title, company=company_name, title=ann_title)
        else:
            positions = []
            c_hash = ""

        if not positions:
            # LLM 失败,降级
            positions = self._degrade_to_single_position(announcement)
            # 降级岗位也应用字段兜底(避免空字段)
            self._apply_field_fallback(positions, announcement)
            job_db.insert_positions(
                ann_id, announcement["company_id"], company_name,
                positions, source_url=ann_url,
            )
            job_db.update_llm_status(ann_id, "skipped", positions_count=len(positions),
                                     cache_hash="degraded")
            logger.warning(f"公告 {ann_id} [{company_name}] LLM 拆岗失败,降级")
            return len(positions)

        # 2.5 字段兜底:VL/正文成功拆出岗位后,若部分字段公告中确实没有,
        #     用公告级数据或统一话术填充,避免空字段影响匹配。
        self._apply_field_fallback(positions, announcement)

        # 3. 写 positions 表
        # 补充投递链接(岗位无独立链接时用公告链接)
        ann_apply_url = announcement.get("apply_url", "")
        for pos in positions:
            if not pos.get("apply_url") and ann_apply_url:
                pos["apply_url"] = ann_apply_url

        inserted = job_db.insert_positions(
            ann_id, announcement["company_id"], company_name,
            positions, source_url=ann_url,
        )
        job_db.update_llm_status(ann_id, "success", positions_count=inserted,
                                 cache_hash=c_hash)
        logger.info(f"公告 {ann_id} [{company_name}] 拆出 {inserted} 个岗位")
        return inserted

    @staticmethod
    def _apply_field_fallback(positions: List[Dict], announcement: Dict):
        """字段兜底:岗位部分字段为空时,用公告级数据或统一话术填充。

        填充规则:
        - city 空 → 公告级 location
        - min_education 空 → 公告级 education_req
        - major_required 空 → "无明确专业要求"
        - requirements 空 → "详见招聘公告"(避免空字段影响匹配与展示)
        """
        ann_location = announcement.get("location", "") or ""
        ann_education = announcement.get("education_req", "") or ""
        for pos in positions:
            if not pos.get("city") and ann_location:
                pos["city"] = ann_location
            if not pos.get("min_education") and ann_education:
                pos["min_education"] = ann_education
            if not pos.get("major_required"):
                pos["major_required"] = "无明确专业要求"
            if not pos.get("requirements"):
                pos["requirements"] = "详见招聘公告"

    def run(self, limit: int = 100, max_workers: int = 5) -> Dict:
        """
        批量处理待 LLM 拆岗的公告。
        limit=100 用于试跑验证(首次全量前先验证效果)。
        max_workers: 并发线程数,1=串行,>1=线程池并发。

        Returns: {"total": N, "success": M, "degraded": K, "failed": L}
        """
        announcements = job_db.get_announcements_for_llm(limit=limit)
        total = len(announcements)

        def _process_one(ann) -> Tuple[str, int]:
            """处理单条公告,返回 (状态标签, 岗位数)。"""
            try:
                count = self.enrich_announcement(ann)
                if count > 0:
                    ann_after = job_db.get_announcement_by_id(ann["id"])
                    if ann_after and ann_after.get("llm_status") == "success":
                        return ("success", count)
                    return ("degraded", count)
                return ("failed", 0)
            except Exception as e:
                logger.error(f"公告 {ann['id']} 处理异常: {e}")
                job_db.update_llm_status(ann["id"], "failed", positions_count=0)
                return ("failed", 0)

        success = degraded = failed = 0

        if max_workers <= 1:
            # 串行模式
            for ann in announcements:
                label, _ = _process_one(ann)
                if label == "success":
                    success += 1
                elif label == "degraded":
                    degraded += 1
                else:
                    failed += 1
                time.sleep(API_INTERVAL)
        else:
            # 并发模式:线程池
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_process_one, ann): ann for ann in announcements}
                for future in as_completed(futures):
                    label, _ = future.result()
                    if label == "success":
                        success += 1
                    elif label == "degraded":
                        degraded += 1
                    else:
                        failed += 1

        logger.info(
            f"LLM 拆岗完成: 总计={total} 成功={success} 降级={degraded} 失败={failed} (workers={max_workers})"
        )
        return {"total": total, "success": success, "degraded": degraded, "failed": failed}


def run_enrichment(limit: int = 100, max_workers: int = 5) -> Dict:
    """便捷函数:批量 LLM 拆岗。limit 默认 100(试跑验证)。max_workers 并发线程数。"""
    enricher = PositionEnricher()
    return enricher.run(limit=limit, max_workers=max_workers)


def run_skipped_reprocess(limit: int = 100, max_workers: int = 5) -> Dict:
    """重处理 llm_status=skipped 的公告。

    流程:取 skipped 公告 → 删旧降级岗位 → 重置为 pending → 走 enrich_announcement
    (正文缺失时会用源表岗位名填字段路径)。

    Args:
        limit: 处理条数上限
        max_workers: 并发线程数
    Returns: {"total": N, "success": M, "degraded": K, "failed": L}
    """
    enricher = PositionEnricher()
    announcements = job_db.get_announcements_by_status("skipped", limit=limit)
    total = len(announcements)

    def _process_one(ann) -> Tuple[str, int]:
        ann_id = ann["id"]
        try:
            # 清理旧的降级岗位,避免重复
            job_db.delete_positions_by_announcement(ann_id)
            # 重置为 pending,让 enrich_announcement 正常处理
            job_db.update_llm_status(ann_id, "pending", positions_count=0, cache_hash="")
            count = enricher.enrich_announcement(ann)
            if count > 0:
                ann_after = job_db.get_announcement_by_id(ann_id)
                if ann_after and ann_after.get("llm_status") == "success":
                    return ("success", count)
                return ("degraded", count)
            return ("failed", 0)
        except Exception as e:
            logger.error(f"重处理公告 {ann_id} 异常: {e}")
            job_db.update_llm_status(ann_id, "failed", positions_count=0)
            return ("failed", 0)

    success = degraded = failed = 0
    if max_workers <= 1:
        for ann in announcements:
            label, _ = _process_one(ann)
            if label == "success":
                success += 1
            elif label == "degraded":
                degraded += 1
            else:
                failed += 1
            time.sleep(API_INTERVAL)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_one, ann): ann for ann in announcements}
            for future in as_completed(futures):
                label, _ = future.result()
                if label == "success":
                    success += 1
                elif label == "degraded":
                    degraded += 1
                else:
                    failed += 1

    logger.info(
        f"skipped 重处理完成: 总计={total} 成功={success} 降级={degraded} 失败={failed} (workers={max_workers})"
    )
    return {"total": total, "success": success, "degraded": degraded, "failed": failed}
