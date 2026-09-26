"""
LLM 客户端 — 基于 DeepSeek 的简历解析与岗位信息增强。

设计原则(第一性原理):
1. 简历解析的核心是"结构化提取" — 把非结构化文本转为可评分的字段
2. Prompt 角色扮演资深 HR,提取维度对标真实招聘筛选标准
3. 输出严格 JSON,便于直接映射到 UserProfile
4. 失败降级:LLM 不可用时返回空结构,不阻塞主流程

DeepSeek API 兼容 OpenAI 格式,api_key 从环境变量 DEEPSEEK_API_KEY 读取。
"""
import json
import logging
import os
import re
from typing import Dict, List, Optional, Any

import requests

logger = logging.getLogger(__name__)

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"


# ========== 简历解析 Prompt ==========
# 角色扮演 + 明确输出格式 + 提取维度对标 HR 真实筛选标准
RESUME_PARSE_PROMPT = """你是一位有 10 年经验的资深 HR 专家,擅长从简历中精准提取候选人画像。
请从以下简历文本中提取结构化信息,严格输出 JSON,不要输出任何 JSON 以外的文字。

提取维度与要求:
1. school: 毕业院校(全称,如"清华大学")。多个取最高学历的院校。
2. degree: 学历(本科/硕士/博士/大专/高中)。
3. major: 专业全称(如"计算机科学与技术")。
4. graduation_year: 毕业年份(4位数字,如 2026)。在读则填预计毕业年份。
5. experience_years: 工作年限(数字,应届/在校填 0,实习经历不算正式工作年限)。
6. core_skills: 核心技能列表(硬技能优先,如 Python/SQL/Excel/数据分析/项目管理等,提取 5-15 个)。
7. target_roles: 目标岗位方向列表(从简历求职意向/经历推断,如 ["产品经理","数据分析"])。
8. target_cities: 目标城市列表(从简历期望地点推断,不确定则为空数组)。
9. target_industries: 目标行业列表(从经历推断,如 ["互联网","金融"])。
10. certificates: 已获证书列表(如 CFA/CPA/法考/PMP/四六级等)。
11. current_role: 当前身份("学生"/"在职"/"待业")。
12. summary: 候选人一句话画像(学校+学历+核心亮点,不超过 50 字)。

注意:
- 缺失的信息填""(字符串)或 [](数组),不要编造
- experience_years 必须是数字
- 只输出 JSON 对象,不要 markdown 代码块标记

简历文本:
\"\"\"{resume_text}\"\"\"
"""


class LLMClient:
    """DeepSeek LLM 客户端 — 简历解析 + 信息增强"""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.model = model or DEEPSEEK_MODEL
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY 未配置,LLM 功能不可用")

    def _chat(self, messages: List[Dict], temperature: float = 0.1,
              max_tokens: int = 2000) -> Optional[str]:
        """调用 DeepSeek Chat API,返回 assistant 文本内容。失败返回 None。"""
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY 未配置,跳过 LLM 调用")
            return None
        try:
            resp = requests.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return content
        except Exception as e:
            logger.error(f"DeepSeek API 调用失败: {e}")
            return None

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict]:
        """从 LLM 输出中提取 JSON 对象(容错:去除 markdown 标记、多余文本)。"""
        if not text:
            return None
        text = text.strip()
        # 去除 ```json ... ``` 包裹
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        # 找到第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            logger.warning(f"LLM 输出无 JSON: {text[:200]}")
            return None
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            logger.warning(f"LLM 输出 JSON 解析失败: {e}; raw={text[:300]}")
            return None

    def parse_resume(self, resume_text: str) -> Dict[str, Any]:
        """
        解析简历文本,返回结构化画像 dict。

        返回字段与 UserProfile 对齐:
        school, degree, major, graduation_year, experience_years,
        core_skills, direction_keywords, target_cities, target_industries,
        target_certificates, current_role, summary
        """
        if not resume_text or not resume_text.strip():
            logger.warning("简历文本为空")
            return self._empty_profile()

        prompt = RESUME_PARSE_PROMPT.format(resume_text=resume_text[:8000])
        content = self._chat([{"role": "user", "content": prompt}])
        parsed = self._extract_json(content) if content else None

        if not parsed:
            logger.warning("简历解析失败,返回空画像")
            return self._empty_profile()

        # 字段映射 + 类型校验
        profile = self._empty_profile()
        profile["school"] = str(parsed.get("school", "")).strip()
        profile["degree"] = str(parsed.get("degree", "")).strip()
        profile["major"] = str(parsed.get("major", "")).strip()
        profile["graduation_year"] = str(parsed.get("graduation_year", "")).strip()
        profile["current_role"] = str(parsed.get("current_role", "")).strip()
        profile["summary"] = str(parsed.get("summary", "")).strip()

        # 经验年限:确保为数字
        try:
            profile["experience_years"] = float(parsed.get("experience_years", 0) or 0)
        except (ValueError, TypeError):
            profile["experience_years"] = 0.0

        # 列表字段
        profile["core_skills"] = self._to_list(parsed.get("core_skills"))
        profile["target_cities"] = self._to_list(parsed.get("target_cities"))
        profile["target_industries"] = self._to_list(parsed.get("target_industries"))
        profile["target_certificates"] = self._to_list(parsed.get("certificates"))

        # 目标方向 → direction_keywords (方向名 → 该方向关键词)
        target_roles = self._to_list(parsed.get("target_roles"))
        direction_keywords: Dict[str, List[str]] = {}
        for role in target_roles:
            if role:
                # 用岗位名本身作为关键词(采集时会用)
                direction_keywords[role] = [role]
        profile["direction_keywords"] = direction_keywords

        logger.info(f"简历解析完成: school={profile['school']} degree={profile['degree']} "
                    f"major={profile['major']} skills={len(profile['core_skills'])}个")
        return profile

    @staticmethod
    def _empty_profile() -> Dict[str, Any]:
        """返回空画像结构(LLM 失败时的降级值)"""
        return {
            "school": "",
            "degree": "",
            "major": "",
            "graduation_year": "",
            "experience_years": 0.0,
            "core_skills": [],
            "direction_keywords": {},
            "target_cities": [],
            "target_industries": [],
            "target_certificates": [],
            "current_role": "",
            "summary": "",
        }

    @staticmethod
    def _to_list(value: Any) -> List[str]:
        """将 LLM 输出的字段值规范化为字符串列表"""
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            # 处理 "A, B, C" 或 "A、B、C" 格式
            parts = re.split(r"[,，、;；\n]", value)
            return [p.strip() for p in parts if p.strip()]
        return [str(value).strip()] if str(value).strip() else []

    def extract_deadline(self, jd_text: str) -> str:
        """
        从 JD 文本中提取投递截止日期(校招岗位常用)。
        返回 YYYY-MM-DD 格式字符串,提取失败返回空字符串。
        """
        if not jd_text:
            return ""
        prompt = (
            "你是招聘信息解析助手。请从以下 JD 文本中提取投递截止日期。\n"
            "只输出日期(YYYY-MM-DD 格式),没有明确截止日期则输出空字符串。\n"
            "不要输出其他文字。\n\n"
            f"JD 文本:\n{jd_text[:3000]}"
        )
        content = self._chat([{"role": "user", "content": prompt}], max_tokens=50)
        if not content:
            return ""
        content = content.strip().strip('"').strip("'")
        # 匹配 YYYY-MM-DD 或 YYYY/MM/DD
        m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", content)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return ""

    def analyze_jd(self, jd_text: str, title: str, profile: Dict) -> Dict[str, str]:
        """
        基于 JD 正文深度分析,生成高质量摘要和申请建议。

        核心改进(对标参考提示词):
        - 必须基于 JD 正文(职责+要求)分析,严禁只看 title
        - 简评引用 JD 职责要点
        - 申请建议针对 JD 要求具体化

        返回: {jd_summary, match_analysis, application_advice}
        """
        if not jd_text or len(jd_text.strip()) < 50:
            return {
                "jd_summary": title,
                "match_analysis": "JD 正文信息不足",
                "application_advice": "请查看 JD 详情了解具体要求",
            }

        # 用户画像摘要(用于匹配分析)
        profile_summary = (
            f"学校:{profile.get('school','')},学历:{profile.get('degree','')},"
            f"专业:{profile.get('major','')},工作年限:{profile.get('experience_years',0)}年,"
            f"核心技能:{','.join(profile.get('core_skills',[])[:8])}"
        )

        prompt = f"""你是资深招聘顾问。请基于以下 JD 正文(而非仅标题)进行深度分析。

用户画像: {profile_summary}

JD 标题: {title}

JD 正文:
\"\"\"{jd_text[:4000]}\"\"\"

请输出 JSON(不要输出其他文字):
{{
  "jd_summary": "JD 核心摘要(100字内):提炼岗位职责和核心要求,引用JD原文要点",
  "match_analysis": "与用户画像的匹配分析(80字内):指出匹配点和差距",
  "application_advice": "申请建议(80字内):针对JD要求,说明简历应突出的具体经验"
}}
"""
        content = self._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=600,
        )
        parsed = self._extract_json(content) if content else None
        if not parsed:
            # 降级:用前 200 字作为摘要
            return {
                "jd_summary": jd_text[:200].replace("\n", " "),
                "match_analysis": "",
                "application_advice": "",
            }
        return {
            "jd_summary": str(parsed.get("jd_summary", "")).strip(),
            "match_analysis": str(parsed.get("match_analysis", "")).strip(),
            "application_advice": str(parsed.get("application_advice", "")).strip(),
        }
