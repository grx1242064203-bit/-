"""LLM 代理服务：复用父目录 LLMClient + resume_parser，对云端 API 暴露受限接口。

设计要点：
1. 不直接暴露 DeepSeek API Key — 由服务层注入，路由层无感知。
2. 复用父目录 (/workspace/job_assistant) 的 resume_parser.parse_resume_text
   与 supplement_profile，避免重复实现 Prompt 与归一化逻辑。
3. sys.path 处理：job_api 位于 job_assistant 子目录，import 父目录模块需把
   job_assistant 根目录加入 sys.path 头部。延迟到方法调用时执行，避免在
   模块导入期污染 sys.path 影响 job_api 自身的 config 解析。
4. 异常上抛：调用失败 / 超时 / 缺 API Key 时抛异常，由路由层映射为 503。
"""
import concurrent.futures
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# /workspace/job_assistant —— llm_proxy.py 的上三级目录
# (__file__ = .../job_api/services/llm_proxy.py, parents[2] = job_assistant/)
_PARENT_DIR = str(Path(__file__).resolve().parents[2])
_path_lock = threading.Lock()
_path_added = False


def _ensure_parent_path() -> None:
    """把 job_assistant 根目录加入 sys.path 头部（仅一次）。"""
    global _path_added
    with _path_lock:
        if _path_added:
            return
        if _PARENT_DIR not in sys.path:
            sys.path.insert(0, _PARENT_DIR)
        _path_added = True


class LLMProxyService:
    """DeepSeek LLM 代理 — 简历解析 + 补充分析。

    封装父目录 LLMClient，对外只暴露结构化结果，不泄漏 API Key。
    """

    def __init__(self, api_key: str = "", timeout: int = 30):
        self.api_key = api_key
        self.timeout = timeout

    def _make_client(self):
        """构造父目录 LLMClient 实例。缺 API Key 时抛 RuntimeError。"""
        _ensure_parent_path()
        from llm_client import LLMClient  # 延迟 import，避免模块导入期副作用

        client = LLMClient(api_key=self.api_key or None)
        if not getattr(client, "api_key", ""):
            raise RuntimeError("DEEPSEEK_API_KEY 未配置，LLM 服务不可用")
        return client

    def parse_resume(self, resume_text: str) -> Dict[str, Any]:
        """解析简历 → {"keywords": [...], "fit_directions": [...]}。

        复用 resume_parser.parse_resume_text。30s 超时；失败抛异常。
        传 raise_on_error=True 让 LLM 失败/返回空时抛 RuntimeError,
        供路由层映射为 503(而非返回空 keywords 让前端误判成功)。
        """
        _ensure_parent_path()
        from resume_parser import parse_resume_text  # 延迟 import

        client = self._make_client()
        return self._run_with_timeout(
            parse_resume_text, resume_text, client, True,
            label="parse_resume",
        )

    def supplement(self, user_edited: dict, resume_text: str = "") -> Dict[str, Any]:
        """补充分析 → 复用 resume_parser.supplement_profile。30s 超时；失败抛异常。

        返回结构（透传 supplement_profile）：
        {fit_directions, structured_keywords, new_directions, new_skills}
        路由层负责挑选 {fit_directions, hard_skills} 字段返回客户端。
        传 raise_on_error=True 让 LLM 失败时抛 RuntimeError,映射为 503。
        """
        _ensure_parent_path()
        from resume_parser import supplement_profile  # 延迟 import

        client = self._make_client()
        return self._run_with_timeout(
            supplement_profile, user_edited, resume_text, client, True,
            label="supplement",
        )

    def extract_schedule_from_text(self, subject: str, body: str) -> Dict[str, Any]:
        """从邮件主题+正文提取日程结构化信息（零 LLM 成本的规则匹配的 AI 补强）。

        用于"AI 智能建日程"：用户粘贴邮件正文，AI 提取关键字段，自动填表。
        不直接创建日程——返回结构化数据，前端预填表单，用户确认后再提交。
        失败抛异常，由路由层映射为 503。

        返回：
            {
                "task_type": "interview"|"written"|"assessment"|"other",
                "company": str,            # 公司名
                "job_title": str,          # 岗位名
                "event_time": str|None,     # ISO 8601 datetime（解析失败为 None）
                "duration_minutes": int,    # 预估时长（分钟）
                "meeting_link": str|None,   # 会议/笔试/测评链接
                "notes": str,               # 备注（含邮件主题）
                "confidence": "high"|"medium"|"low"  # AI 自评置信度
            }
        """
        import json
        import re
        from datetime import datetime, timezone

        client = self._make_client()

        subject = (subject or "").strip()
        body = (body or "").strip()
        # 截断超长正文，控制 token 成本
        body_truncated = body[:4000]

        # 注入当前日期，避免 LLM 模仿 prompt 例子里的年份(2025)导致日程存到过去
        # 邮件正文里如果没显式写年份，LLM 应该用当前年份(2026)而不是例子年份(2025)
        today_iso = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
        today_year = today_iso[:4]

        prompt = (
            "你是招聘流程信息抽取助手。从用户提供的邮件主题和正文中，"
            "提取招聘相关的日程信息。严格输出 JSON，不要输出 JSON 以外的任何文字。\n\n"
            f"【重要：当前日期】今天是 {today_iso}。如果邮件正文没有显式指定年份，"
            f"请用当前年份 {today_year}。招聘日程通常在未来，"
            f"请勿把日程时间设置在过去（早于今天）。\n\n"
            "【字段说明】\n"
            "1. task_type: 事件类型，取值 interview(面试) / written(笔试) / "
            "assessment(测评/性格测试) / other(宣讲会等其他招聘相关事件)。"
            "无法判断时给 other。\n"
            "2. company: 公司全称。从发件人域名、落款、正文中提取。"
            "找不到时返回空字符串。\n"
            "3. job_title: 岗位名称。如「后端开发工程师」「产品经理」。"
            "找不到时返回空字符串。\n"
            "4. event_time: 事件开始时间，ISO 8601 格式（如 "
            f'"{today_year}-01-15T14:30:00+08:00"）。'
            "正文中的时间可能是「1月15日 14:30」「1月15日下午2点半」"
            "等中文表达，请规范化为 ISO。如果时间不明确或缺失，返回 null。\n"
            "5. duration_minutes: 预估时长（分钟）。面试一般 60，笔试 120，"
            "测评 30。无法判断给 60。\n"
            "6. meeting_link: 会议链接/笔试链接/测评链接。优先取腾讯会议、"
            "Zoom、飞书、Teams、会议链接等。没有则返回 null。\n"
            "7. notes: 备注，简短一句话说明事件（如「腾讯会议 二面」）。\n"
            "8. confidence: 你对这次提取结果的整体置信度，取值 "
            "high / medium / low。时间缺失或公司不明时降级。\n\n"
            f"【邮件主题】\n{subject or '（无主题）'}\n\n"
            f"【邮件正文】\n{body_truncated or '（无正文）'}\n\n"
            "【输出 JSON 模板】\n"
            "{\n"
            '  "task_type": "interview",\n'
            '  "company": "示例科技有限公司",\n'
            '  "job_title": "后端开发工程师",\n'
            f'  "event_time": "{today_year}-01-15T14:30:00+08:00",\n'
            '  "duration_minutes": 60,\n'
            '  "meeting_link": "https://meeting.tencent.com/xxx",\n'
            '  "notes": "腾讯会议 二面",\n'
            '  "confidence": "high"\n'
            "}\n"
        )
        content = client._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=800,
            json_mode=True,
        )
        if content is None:
            raise RuntimeError(
                "邮件日程提取 LLM 调用失败: API 返回空"
                "(可能 API Key 无效或服务不可用)"
            )

        # 解析 JSON（容错：模型偶发返回非纯 JSON 时用正则兜底）
        data: Dict[str, Any] = {}
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", content, re.S)
            if m:
                try:
                    data = json.loads(m.group(0))
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}

        # 校验 + 归一化 task_type
        valid_types = {"interview", "written", "assessment", "other"}
        task_type = data.get("task_type", "other")
        if task_type not in valid_types:
            task_type = "other"

        # 校验 event_time（必须是可解析的 ISO）
        event_time = data.get("event_time")
        if event_time:
            try:
                # 兼容模型偶发返回 "2025-01-15 14:30:00" 这种带空格的伪 ISO
                normalized = str(event_time).replace(" ", "T")
                datetime.fromisoformat(normalized)
                event_time = normalized
            except (ValueError, TypeError):
                event_time = None
        else:
            event_time = None

        # duration_minutes 必须是正整数
        try:
            duration = int(data.get("duration_minutes", 60))
            if duration <= 0:
                duration = 60
        except (ValueError, TypeError):
            duration = 60

        confidence = data.get("confidence", "low")
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"

        return {
            "task_type": task_type,
            "company": str(data.get("company", "") or "").strip(),
            "job_title": str(data.get("job_title", "") or "").strip(),
            "event_time": event_time,
            "duration_minutes": duration,
            "meeting_link": data.get("meeting_link") or None,
            "notes": str(data.get("notes", "") or "").strip(),
            "confidence": confidence,
        }

    def company_due_diligence(self, company_name: str, resume_text: str = "") -> Dict[str, Any]:
        """公司尽调：联网搜索 + LLM 生成简介/官网/新闻/个性化面试答案。

        搜索：Bing（找官网，直接 URL）+ 百度（补充新闻，国内覆盖最全）
        LLM：结合搜索结果 + 用户简历，生成专业深度面试回答
        """
        import json
        import re

        client = self._make_client()

        # ============ 1) 联网搜索：官网 + 新闻 ============
        official_website, news_links = self._search_company_info(company_name)

        # ============ 2) LLM 生成简介 + 个性化面试问答 ============
        news_ctx = "\n".join(
            f"- {n['title']}: {n['url']}" for n in news_links
        ) or "（无搜索结果）"

        resume_ctx = resume_text.strip()[:4000] if resume_text else ""
        resume_block = (
            f"\n\n【用户简历】（用于生成个性化、有针对性的面试回答）：\n{resume_ctx}\n"
            if resume_ctx else ""
        )

        prompt = (
            f"你是一位拥有 10 年以上经验的资深职业规划师和面试官辅导专家，"
            f"深谙互联网/金融/快消/制造等各行业的校招面试套路。\n\n"
            f"请针对公司「{company_name}」生成以下内容，严格输出 JSON，"
            f"不要输出 JSON 以外的任何文字。\n\n"
            f"【参考搜索结果】\n{news_ctx}\n"
            f"{resume_block}\n\n"
            f"【输出字段】\n"
            f"1. intro: 公司简介（200-300字，涵盖主营业务、行业地位、核心产品/技术、"
            f"近期动态、企业文化/价值观）。要专业、有信息量。\n\n"
            f"2. why_company_questions: 面试问答列表（3-4个），覆盖面试官最可能追问的"
            f"核心问题，如：\n"
            f"   - 「你为什么选择我们公司/这个岗位？」\n"
            f"   - 「你了解我们公司的哪些业务/产品？」\n"
            f"   - 「你认为我们公司的核心竞争力是什么？」\n"
            f"   - 「你的经历和我们岗位的匹配度如何？」\n\n"
            f"   每个元素格式：{{\"question\": \"面试官问题\", \"answer\": \"专业回答\"}}\n\n"
            f"   【answer 写作要求（严格遵守）】：\n"
            f"   - 长度 300-500 字，要充实、有细节，不能空泛\n"
            f"   - 采用「表态 + 论据1（公司业务/行业洞察）+ 论据2（个人经历+数据）"
            f"+ 收尾匹配」的结构\n"
            f"   - 必须结合用户简历中的具体经历/项目/技能，用数据量化（如"
            f"「在XX项目中负责YY，将ZZ提升了30%」），把个人优势和公司需求强关联\n"
            f"   - 体现行业洞察力：提到公司的具体产品、业务线、竞争对手、行业趋势\n"
            f"   - 语言专业、自信，像一个真正了解行业、做过功课的候选人，"
            f"避免「我觉得」「可能」「大概」这类模糊词\n"
            f"   - 不要写「求职者应该」「建议」这类第三人称，直接写第一人称的回答内容\n"
        )
        content = client._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=3000,
            json_mode=True,
        )
        if content is None:
            raise RuntimeError(
                "公司尽调 LLM 调用失败: API 返回空(可能 API Key 无效或服务不可用)"
            )
        intro = ""
        questions: list = []
        if content:
            try:
                data = json.loads(content)
                intro = data.get("intro", "")
                raw_questions = data.get("why_company_questions", [])
                for q in raw_questions:
                    if isinstance(q, dict):
                        answer = q.get("answer") or q.get("hint") or ""
                        if q.get("question"):
                            questions.append({
                                "question": q["question"],
                                "answer": answer,
                            })
            except json.JSONDecodeError:
                m = re.search(r"\{.*\}", content, re.S)
                if m:
                    try:
                        data = json.loads(m.group(0))
                        intro = data.get("intro", "")
                        raw_questions = data.get("why_company_questions", [])
                        for q in raw_questions:
                            if isinstance(q, dict):
                                answer = q.get("answer") or q.get("hint") or ""
                                if q.get("question"):
                                    questions.append({
                                        "question": q["question"],
                                        "answer": answer,
                                    })
                    except json.JSONDecodeError:
                        pass

        return {
            "intro": intro,
            "official_website": official_website,
            "news_links": news_links,
            "why_company_questions": questions,
        }

    def _search_company_info(self, company_name: str):
        """搜索公司官网 + 近期新闻。Bing 为主（直接 URL），百度为辅（新闻补充）。

        Returns: (official_website: str, news_links: list[dict])
        """
        import re
        import requests as _requests

        browser_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        skip_domains = (
            "baidu.com", "zhihu.com", "bilibili.com", "sohu.com",
            "163.com", "sina.com", "qq.com", "weibo.com",
            "duckduckgo.com", "google.com", "bing.com", "microsoft.com",
            "wikipedia.org", "baike.baidu.com", "douyin.com",
            "xiaohongshu.com", "linkedin.com", "csdn.net", "jianshu.com",
            "maimai.cn",
        )

        def _is_skipped(href: str) -> bool:
            return any(d in href for d in skip_domains)

        def _extract_real_url(href: str) -> str:
            """解析百度跳转链接 / DDG 重定向，返回真实 URL。"""
            if "baidu.com/link?url=" in href:
                try:
                    resp = _requests.head(href, headers=browser_headers,
                                          allow_redirects=True, timeout=8)
                    return resp.url
                except Exception:
                    return href
            if "uddg=" in href:
                from urllib.parse import unquote, urlparse, parse_qs
                parsed = urlparse(href)
                raw = parse_qs(parsed.query).get("uddg", [""])[0]
                return unquote(raw) if raw else href
            return href

        official_website = ""
        news_links: list = []
        seen_urls = set()

        # ---- 1) Bing 搜索（官网 + 新闻，返回直接 URL）----
        try:
            r = _requests.get(
                "https://www.bing.com/search",
                params={"q": f"{company_name} 官网 最新新闻"},
                headers=browser_headers,
                timeout=12,
            )
            r.raise_for_status()
            blocks = re.findall(
                r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>',
                r.text, re.S,
            )
            for b in blocks:
                m = re.search(
                    r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', b, re.S
                )
                if not m:
                    continue
                href = m.group(1)
                title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                if not title or href in seen_urls:
                    continue
                seen_urls.add(href)
                if not official_website and not _is_skipped(href):
                    official_website = href
                news_links.append({"title": title[:80], "url": href})
                if len(news_links) >= 6:
                    break
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Bing 搜索失败 ({company_name}): {e!r}")

        # ---- 2) 百度搜索（补充新闻，国内覆盖最全）----
        if len(news_links) < 5:
            try:
                r = _requests.get(
                    "https://www.baidu.com/s",
                    params={"wd": f"{company_name} 最新新闻 动态"},
                    headers=browser_headers,
                    timeout=12,
                )
                r.raise_for_status()
                links = re.findall(
                    r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                    r.text, re.S,
                )
                for href, title in links:
                    title = re.sub(r"<[^>]+>", "", title).strip()
                    if not title:
                        continue
                    real_url = _extract_real_url(href)
                    if real_url in seen_urls:
                        continue
                    seen_urls.add(real_url)
                    if not official_website and not _is_skipped(real_url):
                        official_website = real_url
                    news_links.append({"title": title[:80], "url": real_url})
                    if len(news_links) >= 8:
                        break
            except Exception as e:  # noqa: BLE001
                logger.warning(f"百度搜索失败 ({company_name}): {e!r}")

        # 去重 + 限制条数
        final_news = []
        seen = set()
        for n in news_links:
            if n["url"] in seen:
                continue
            seen.add(n["url"])
            final_news.append(n)
            if len(final_news) >= 6:
                break

        return official_website, final_news

    def _run_with_timeout(self, fn, *args, label: str = "llm_call"):
        """在线程池中执行 fn，超过 self.timeout 抛 TimeoutError。

        parse_resume_text 内部已捕获 LLM 异常并返回空结果，因此超时是
        调用层主动保护；其他显式异常（如 API Key 缺失）原样上抛。
        """
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(fn, *args)
            try:
                return future.result(timeout=self.timeout)
            except concurrent.futures.TimeoutError:
                logger.error(f"LLM {label} 超时 ({self.timeout}s)")
                raise TimeoutError(f"LLM {label} 超时 ({self.timeout}s)")
        finally:
            executor.shutdown(wait=False)
