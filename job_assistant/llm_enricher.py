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
from typing import Dict, List, Optional

from config import settings
from llm_client import LLMClient
import job_db
from content_fetcher import get_cached_content, fetch_content, fetch_content_full

logger = logging.getLogger(__name__)

LLM_CACHE_DIR = os.path.join(settings.DATA_DIR, "llm_cache")
MAX_RETRIES = 3
API_INTERVAL = 1.0  # 秒,LLM 调用间隔(控成本+避限流)

POSITION_EXTRACT_PROMPT = """你是校招信息解析专家。请从以下招聘公告中提取所有可独立投递的具体岗位,并填入结构化字段。

公司: {company}
公告标题: {title}

公告内容:
\"\"\"{content}\"\"\"

请输出 JSON 数组(严格 JSON,不要输出任何 JSON 以外的文字):
[
  {{
    "position_title": "岗位名称(具体岗位名,如:Java开发工程师/产品经理/管培生,不要用公告标题)",
    "department": "部门或条线(如:技术中台/零售金融,无法确定填空字符串)",
    "job_category": "岗位大类(研发/产品/设计/运营/市场/销售/职能/金融/管培/其他,选1个最贴切的)",
    "job_subcategory": "岗位子类(如:后端开发/算法/前端/测试/数据分析,无法确定填空)",
    "hard_skills": ["硬技能列表,如:Python/Java/SQL/机器学习,无则空数组"],
    "soft_skills": ["软技能列表,如:沟通/团队协作,无则空数组"],
    "certifications": ["证书要求,如:CFA/CPA/法律职业资格,无则空数组"],
    "languages": ["语言要求,如:英语CET-6,无则空数组"],
    "major_required": "具体专业要求(如:计算机科学与技术/软件工程,无明确要求填'不限')",
    "major_category": "专业大类(工科/理科/商科/文科/医科/农学/艺术/不限,选1个)",
    "min_education": "最低学历(大专/本科/硕士/博士/不限)",
    "city": "工作城市(如:北京/上海/深圳,多个用逗号分隔,无则空字符串)",
    "province": "工作省份(如:广东/浙江,无则空字符串)",
    "recruitment_process": "招聘流程简述(如:网申→笔试→面试→offer,无则空字符串)",
    "has_written_test": false,
    "responsibilities": "岗位职责(100字内,无则空字符串)",
    "requirements": "任职要求(100字内,无则空字符串)",
    "bonus_points": "加分项(50字内,无则空字符串)",
    "keywords": ["关键词标签,用于匹配,如:Python/机器学习/大厂,提取3-8个"],
    "jd_summary": "岗位摘要(60字内)",
    "is_management_trainee": false,
    "difficulty": "难度(最激烈/较为激烈/中等难度/较低难度)",
    "apply_url": "独立投递链接(无则空字符串)"
  }}
]

提取规则(严格遵守):
0. 【核心铁律】只提取公告内容/标题中明确出现的岗位。严禁编造、推断、补充任何未在正文中出现的岗位名称。若正文/标题中没有具体岗位名,输出空数组 []。
1. 识别所有可独立投递的具体岗位;每个岗位必须是数组中的一个独立对象,严禁把多个岗位名拼成一个字符串。若只有大类无具体岗位名,拆为"通用校招岗"。
2. is_management_trainee: 管培生/管理培训生/MT/培训生 标记为 true
3. difficulty: 头部互联网/金融/知名外企=最激烈;中型公司=较为激烈;普通=中等;冷门=较低
4. keywords 必须包含岗位核心技能/方向词,用于后续匹配
5. min_education 取最低可投递学历(如"本科及以上"填"本科")

6. 【字段填充策略】分三个层次处理,最大化字段填充率:
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
                          title: str = "") -> List[Dict]:
        """
        从公告正文用 LLM 提取岗位列表。
        带缓存:相同 (company+title+content) hash 不重复调用。
        失败返回空列表(由调用方降级处理)。

        关键防幻觉设计:
        1. 缓存键包含 company+title+content,防止不同公司共用垃圾内容的缓存
        2. 提取后校验岗位名是否出现在源文本中,过滤纯幻觉岗位
        """
        if not content or len(content.strip()) < 30:
            return []

        # 源文本(用于岗位名回查校验,防止 LLM 编造不存在的岗位)
        source_text = f"{title}\n{content}"

        c_hash = _content_hash(content, company=company, title=title)

        # 1. 查缓存
        cached = _get_cached_llm_result(c_hash)
        if cached is not None:
            logger.debug(f"LLM 缓存命中: {company} ({len(cached)} 岗位)")
            return self._validate_positions(cached, source_text)

        # 2. 调用 LLM(带重试)
        prompt = POSITION_EXTRACT_PROMPT.format(
            company=company or "未知",
            title=title or "",
            content=content[:8000],  # 截断控制成本(校招公告通常 2000-6000 字)
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
            "department": "",
            "location": announcement.get("location", ""),
            "education_req": announcement.get("education_req", ""),
            "major_req": "",
            "jd_summary": "",
            "is_management_trainee": False,
            "difficulty": "",
            "apply_url": announcement.get("apply_url", ""),
        }]

    def enrich_announcement(self, announcement: Dict) -> int:
        """
        处理单条公告:抓正文 → LLM 拆岗 → 写 positions → 更新状态。
        返回插入的岗位数。
        """
        ann_id = announcement["id"]
        company_name = announcement.get("company_name", "")
        ann_title = announcement.get("announcement_title", "")
        ann_url = announcement.get("announcement_url", "")

        # 1. 获取正文(优先 DB 已存储的 content,其次缓存,最后实时抓取)
        content = announcement.get("content", "") or ""
        images_json = announcement.get("content_images", "") or ""
        if not content or len(content) < 30:
            content = get_cached_content(ann_url) or ""
        if not content or len(content) < 30:
            fetch_result = fetch_content_full(ann_url)
            content = fetch_result["text"]
            img_urls = fetch_result["images"]
            # 抓到正文后存 DB,避免重复爬取
            if content and len(content) >= 30:
                job_db.update_crawl_status(ann_id, "success", content=content)
            if img_urls:
                import json as _json
                job_db.update_announcement_images(ann_id, _json.dumps(img_urls, ensure_ascii=False))
                images_json = _json.dumps(img_urls, ensure_ascii=False)

        # 1.5 获取本地所有缓存图片(可能比 DB 中存储的更全)
        from content_fetcher import get_cached_images
        local_images = get_cached_images(ann_url)
        # 合并 DB 中的图片和本地图片(去重)
        import json as _json
        db_images = []
        if images_json:
            try:
                db_images = _json.loads(images_json) if isinstance(images_json, str) else images_json
            except Exception:
                db_images = []
        all_images = list(dict.fromkeys(db_images + local_images))  # 去重保序

        # 1.6 垃圾内容检测:微信反爬返回"环境异常"等,不能作为拆岗依据
        content_is_garbage = _is_garbage_content(content)

        # 2. VL OCR:判断是否需要(重新)识别图片
        # 触发条件:正文过短(<100字) 或 正文是低质量VL结果(含"没有包含具体岗位"等) 或 正文明显只有公司介绍
        # 或 正文主要是微信UI元素(视频/小程序/赞/在看/分享等)
        # 或 内容是反爬垃圾
        _low_quality_vl = any(kw in content for kw in [
            "没有包含具体的岗位", "均没有包含", "仅属于招聘宣传",
            "公司介绍", "点击公众号下方菜单栏",
        ])
        # 检测微信文章底部UI噪声(大量"赞/在看/分享/留言/收藏/视频/小程序"等无意义文字)
        _ui_noise_count = sum(content.count(kw) for kw in
                              ["轻点两下", "取消赞", "在看", "分享", "留言", "收藏", "小程序", "听过", "视频号"])
        _is_ui_noise = _ui_noise_count >= 3 and len(content) < 2000
        need_vl = (len(content) < 100) or _low_quality_vl or _is_ui_noise or content_is_garbage

        if need_vl and all_images:
            try:
                logger.info(f"公告 {ann_id} [{company_name}] 重新VL识别({len(all_images)}张图, "
                            f"正文{len(content)}字, garbage={content_is_garbage})")
                vl_prompt = (
                    f"这是{company_name}的招聘公告图片。请逐张识别图片中的所有文字内容,"
                    f"特别关注:岗位名称、专业要求、学历要求、工作地点、岗位职责、任职要求等。"
                    f"如果图片是长图,请完整识别所有文字。按图片顺序输出全部文字。"
                )
                vl_text = self.llm.chat_with_images(vl_prompt, all_images, max_tokens=4000)
                if vl_text and len(vl_text) > 50:
                    content = vl_text
                    content_is_garbage = _is_garbage_content(content)
                    # 把 VL 识别结果和完整图片列表存到 DB
                    job_db.update_crawl_status(ann_id, "success", content=content)
                    job_db.update_announcement_images(ann_id, _json.dumps(all_images, ensure_ascii=False))
                    job_db.update_vl_status(ann_id, "success")
                    logger.info(f"公告 {ann_id} VL 识别成功: {len(vl_text)} 字")
                else:
                    # VL 所有策略(切片+放宽像素)均失败 → 标记 vl_status=failed
                    # 不立即走兜底降级,先记录失败,便于后续排查与飞书表统计
                    vl_error = self.llm.last_vl_error_msg or "VL识别返回空(已尝试多策略切片)"
                    job_db.update_vl_status(ann_id, "failed", error=vl_error)
                    logger.warning(
                        f"公告 {ann_id} VL 识别失败(已尝试多策略): {vl_error[:120]}"
                    )
            except Exception as e:
                vl_error = str(e)
                job_db.update_vl_status(ann_id, "failed", error=vl_error)
                logger.warning(f"公告 {ann_id} VL 识别异常: {e}")
        elif need_vl and not all_images:
            # 需要 VL 但没有图片 → 标记为 failed(无法识别图片公告)
            job_db.update_vl_status(ann_id, "failed", error="需要VL识别但无可用图片")
            logger.warning(f"公告 {ann_id} 需要VL但无图片,标记vl_status=failed")
        else:
            # 不需要 VL(正文足够)→ 标记 not_needed,与 success 区分
            job_db.update_vl_status(ann_id, "not_needed")

        # 对抗性优化:微信公众号反爬严重,正文常抓不到。
        # 但飞书源表的公告标题本身已包含岗位列表(如"投行经理助理,债券承做助理..."),
        # 因此正文缺失或为垃圾时,用标题作为 LLM 输入,仍可拆出岗位。
        # 关键:绝不能把"环境异常"等垃圾内容传给 LLM,否则会产生幻觉。
        if not content or len(content) < 30 or content_is_garbage:
            logger.info(f"公告 {ann_id} [{company_name}] 正文缺失/垃圾,用标题拆岗")
            content = ann_title or ""  # 用标题作为拆岗输入

        # 2. LLM 拆岗
        positions = self.extract_positions(content, company=company_name, title=ann_title)
        c_hash = _content_hash(content, company=company_name, title=ann_title)

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

    def run(self, limit: int = 100) -> Dict:
        """
        批量处理待 LLM 拆岗的公告。
        limit=100 用于试跑验证(首次全量前先验证效果)。

        Returns: {"total": N, "success": M, "degraded": K, "failed": L}
        """
        announcements = job_db.get_announcements_for_llm(limit=limit)
        total = len(announcements)
        success = 0
        degraded = 0
        failed = 0

        for ann in announcements:
            try:
                count = self.enrich_announcement(ann)
                if count > 0:
                    # 判断是成功还是降级
                    ann_after = job_db.get_announcement_by_id(ann["id"])
                    if ann_after and ann_after.get("llm_status") == "success":
                        success += 1
                    else:
                        degraded += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"公告 {ann['id']} 处理异常: {e}")
                job_db.update_llm_status(ann["id"], "failed", error=str(e)[:200])
                failed += 1
            time.sleep(API_INTERVAL)

        logger.info(
            f"LLM 拆岗完成: 总计={total} 成功={success} 降级={degraded} 失败={failed}"
        )
        return {"total": total, "success": success, "degraded": degraded, "failed": failed}


def run_enrichment(limit: int = 100) -> Dict:
    """便捷函数:批量 LLM 拆岗。limit 默认 100(试跑验证)。"""
    enricher = PositionEnricher()
    return enricher.run(limit=limit)
