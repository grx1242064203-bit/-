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
        """
        _ensure_parent_path()
        from resume_parser import parse_resume_text  # 延迟 import

        client = self._make_client()
        return self._run_with_timeout(
            parse_resume_text, resume_text, client,
            label="parse_resume",
        )

    def supplement(self, user_edited: dict, resume_text: str = "") -> Dict[str, Any]:
        """补充分析 → 复用 resume_parser.supplement_profile。30s 超时；失败抛异常。

        返回结构（透传 supplement_profile）：
        {fit_directions, structured_keywords, new_directions, new_skills}
        路由层负责挑选 {fit_directions, hard_skills} 字段返回客户端。
        """
        _ensure_parent_path()
        from resume_parser import supplement_profile  # 延迟 import

        client = self._make_client()
        return self._run_with_timeout(
            supplement_profile, user_edited, resume_text, client,
            label="supplement",
        )

    def company_due_diligence(self, company_name: str, resume_text: str = "") -> Dict[str, Any]:
        """公司尽调：联网搜索 + LLM 生成简介/官网/新闻/个性化面试答案。

        流程：
        1. DuckDuckGo 搜索公司官网 + 近期新闻（多关键词 fallback）
        2. 将搜索结果 + 用户简历喂给 LLM，生成：
           - 公司简介 intro
           - 「为什么选择这家公司」面试问题 + 结合用户简历的个性化回答思路
        3. 返回 {intro, official_website, news_links, why_company_questions}
        """
        import json
        import re
        import requests as _requests
        from urllib.parse import unquote, urlparse, parse_qs

        client = self._make_client()

        # 1) 联网搜索：官网 + 新闻（多关键词，提高命中率）
        official_website = ""
        news_links: list = []

        search_queries = [
            f"{company_name} 官网 最新新闻",
            f"{company_name} official website news",
        ]
        for q in search_queries:
            if official_website and len(news_links) >= 3:
                break
            try:
                search_url = (
                    "https://html.duckduckgo.com/html/?q="
                    + _requests.utils.quote(q)
                )
                resp = _requests.get(
                    search_url,
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                                           "Chrome/120.0.0.0 Safari/537.36"},
                    timeout=12,
                )
                resp.raise_for_status()
                # 提取 result__a 链接（DDG HTML 搜索结果）
                links = re.findall(
                    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                    resp.text,
                    re.S,
                )
                seen = set()
                for href, title in links[:10]:
                    title = re.sub(r"<[^>]+>", "", title).strip()
                    if not title:
                        continue
                    # 解析 DDG 重定向 URL
                    if "uddg=" in href:
                        parsed = urlparse(href)
                        raw = parse_qs(parsed.query).get("uddg", [""])[0]
                        href = unquote(raw) if raw else href
                    if not href or href in seen:
                        continue
                    seen.add(href)
                    # 过滤搜索引擎/百科/社媒，第一条干净链接作为官网候选
                    skip_domains = (
                        "baidu.com", "zhihu.com", "bilibili.com", "sohu.com",
                        "163.com", "sina.com", "qq.com", "weibo.com",
                        "duckduckgo.com", "google.com", "bing.com",
                        "wikipedia.org", "baike.baidu.com", "douyin.com",
                        "xiaohongshu.com", "linkedin.com",
                    )
                    is_skipped = any(d in href for d in skip_domains)
                    if not official_website and not is_skipped and href.startswith("http"):
                        official_website = href
                    news_links.append({"title": title[:80], "url": href})
                    if len(news_links) >= 5:
                        break
            except Exception as e:  # noqa: BLE001 搜索失败不阻塞 LLM 生成
                logger.warning(f"公司尽调联网搜索失败 ({q}): {e!r}")

        # 2) LLM 生成简介 + 个性化面试问题/答案
        news_ctx = "\n".join(
            f"- {n['title']}: {n['url']}" for n in news_links
        ) or "（无搜索结果）"

        resume_ctx = resume_text.strip()[:3000] if resume_text else ""
        resume_block = (
            f"\n\n用户简历摘要（用于生成个性化面试回答）：\n{resume_ctx}\n"
            if resume_ctx else ""
        )

        prompt = (
            f"你是一位资深求职辅导专家。请针对公司「{company_name}」生成以下内容，"
            f"严格输出 JSON，不要输出 JSON 以外的文字。\n\n"
            f"参考搜索结果：\n{news_ctx}\n"
            f"{resume_block}\n"
            f"输出字段：\n"
            f"1. intro: 公司简介（150-250字，包含主营业务、行业地位、核心优势）\n"
            f"2. why_company_questions: 「为什么选择这家公司」面试问答列表（3-5个）。\n"
            f"   每个元素格式 {{\"question\": \"面试官可能问的问题\", "
            f"\"answer\": \"结合公司情况和用户简历的回答思路（80-150字，要具体、有针对性，"
            f"如果有用户简历需把简历中的经历/技能与公司业务关联起来）\"}}\n"
            f"   注意：answer 必须是具体的回答思路，不能是空泛的套话。\n"
        )
        content = client._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
            json_mode=True,
        )
        intro = ""
        questions: list = []
        if content:
            try:
                data = json.loads(content)
                intro = data.get("intro", "")
                raw_questions = data.get("why_company_questions", [])
                # 兼容旧字段 hint，统一转成 answer
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
