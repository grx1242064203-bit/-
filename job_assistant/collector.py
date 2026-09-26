"""
岗位采集器 — 可插拔搜索提供者 + JD 抓取 + 结构化提取。

设计原则:
- 搜索提供者可插拔(Tavily/SerpAPI/Brave 等),通过环境变量切换
- JD 抓取处理静态页(BS4)+ 动态页(Playwright,可选)
- 提取失败的岗位跳过,不影响其他
"""
import os
import re
import logging
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)


# ========== 搜索提供者接口 ==========
class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        """返回 [{title, url, snippet}]"""
        ...


class TavilySearchProvider(SearchProvider):
    """Tavily AI 搜索 — 有免费额度,适合金融信息搜索"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY", "")

    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        if not self.api_key:
            logger.warning("TAVILY_API_KEY 未设置,跳过搜索")
            return []
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results,
                    "include_answer": False,
                },
                timeout=30,
            )
            data = resp.json()
            results = []
            for r in data.get("results", []):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                })
            return results
        except Exception as e:
            logger.error(f"Tavily 搜索失败: {e}")
            return []


class SerpApiSearchProvider(SearchProvider):
    """SerpAPI — Google 搜索结果"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("SERPAPI_KEY", "")

    def search(self, query: str, max_results: int = 10) -> List[Dict]:
        if not self.api_key:
            return []
        try:
            resp = requests.get("https://serpapi.com/search", params={
                "q": query, "api_key": self.api_key, "num": max_results,
                "engine": "google", "hl": "zh-cn",
            }, timeout=30)
            data = resp.json()
            results = []
            for r in data.get("organic_results", [])[:max_results]:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("link", ""),
                    "snippet": r.get("snippet", ""),
                })
            return results
        except Exception as e:
            logger.error(f"SerpAPI 搜索失败: {e}")
            return []


def get_search_provider() -> SearchProvider:
    """根据环境变量选择搜索提供者"""
    if os.getenv("TAVILY_API_KEY"):
        return TavilySearchProvider()
    if os.getenv("SERPAPI_KEY"):
        return SerpApiSearchProvider()
    raise RuntimeError("未配置搜索 API Key(TAVILY_API_KEY 或 SERPAPI_KEY)")


# ========== JD 抓取 ==========
def fetch_jd(url: str, timeout: int = 15) -> str:
    """抓取 JD 页面正文。静态页用 BS4,动态页返回空(需 Playwright 扩展)"""
    try:
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            return ""
        # 简单提取正文文本
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        # 移除 script/style
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # 清理多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:5000]  # 截断,避免过长
    except Exception as e:
        logger.debug(f"抓取 JD 失败 {url}: {e}")
        return ""


# ========== 采集器 ==========
class JobCollector:
    """岗位采集器 — 搜索 + 抓取 + 提取"""

    def __init__(self, provider: SearchProvider = None):
        self.provider = provider or get_search_provider()

    def _build_queries(self, profile, target_companies: List[str],
                       target_cities: List[str]) -> List[str]:
        """
        根据用户画像构建搜索关键词(通用化)。
        从 direction_keywords 取每个方向的关键词组合搜索词。
        按用户角色(role)注入差异化关键词:
        - internship(实习): 优先搜实习岗位
        - campus(校招): 优先搜校招/管培/应届
        - social(社招): 搜社招岗位,排除校招
        """
        cities = " ".join(target_cities) if target_cities else ""
        companies = target_companies if target_companies else []
        directions = profile.direction_keywords or {}
        role = getattr(profile, "role", "") or ""

        queries = []
        # 按用户目标方向构建搜索词
        for direction, keywords in directions.items():
            # 取该方向前3个关键词作为搜索核心
            core_kw = " ".join(keywords[:3])
            for comp in (companies or [""]):
                for city in (target_cities or [""]):
                    q = f"{comp} {core_kw} 招聘 {city}".strip()
                    if len(q) > 5:
                        queries.append(q)
            if not companies:
                queries.append(f"{core_kw} 招聘 {cities}".strip())

        # 按角色注入专项搜索词
        if role == "internship":
            # 实习:优先搜实习岗位
            queries.append("实习生 招聘 2026")
            queries.append("internship hiring 2026 china")
            for direction in directions:
                queries.append(f"{direction} 实习 招聘")
        elif role == "campus":
            # 校招:校招/管培/应届
            queries.append("管培生 校招 招聘 2026")
            queries.append("graduate program campus hiring 2026 china")
            queries.append("应届生 校招 招聘")
        elif role == "social":
            # 社招:搜社招岗位
            queries.append("社招 招聘 2026")
            queries.append("experienced hire 2026 china")
        else:
            # 未指定角色:通用校招/管培(默认,覆盖大多数用户)
            queries.append("管培生 校招 招聘 2026")
            queries.append("graduate program campus hiring 2026 china")

        # 用户专业相关
        if profile.major:
            queries.append(f"{profile.major} 招聘 {cities}".strip())

        return list(dict.fromkeys(queries))[:15]  # 去重,限 15 条

    def collect(self, profile, target_companies: List[str],
                target_cities: List[str], limit: int = 20) -> List[Dict]:
        """采集岗位,返回标准化的 job dict 列表"""
        queries = self._build_queries(profile, target_companies, target_cities)
        seen_urls = set()
        jobs = []

        for q in queries:
            if len(jobs) >= limit:
                break
            results = self.provider.search(q, max_results=8)
            for r in results:
                url = r["url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # 初筛:排除明显不相关的(用户方向关键词+通用招聘词)
                title = r["title"]
                all_target_kw = []
                for kws in (profile.direction_keywords or {}).values():
                    all_target_kw.extend(kws)
                all_target_kw += ["招聘", "hiring", "job", "position", "校招",
                                  "社招", "实习", "intern", "管培", "graduate"]
                if not any(kw.lower() in title.lower() for kw in all_target_kw):
                    continue

                # 抓取 JD
                jd_text = fetch_jd(url)
                snippet = r.get("snippet", "")
                full_text = jd_text or snippet

                if not full_text:
                    continue

                # 提取公司、地点、薪资
                company = self._extract_company(title, full_text)
                location = self._extract_location(full_text, target_cities)
                salary = self._extract_salary(full_text)
                posted = self._extract_posted_date(full_text)

                jobs.append({
                    "title": title,
                    "company": company,
                    "department": "",
                    "location": location,
                    "salary": salary,
                    "jd_text": full_text,
                    "jd_summary": snippet[:200],
                    "jd_url": url,
                    "posted": posted,
                    "crawl_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
                if len(jobs) >= limit:
                    break
            time.sleep(0.3)  # 搜索限流

        return jobs

    @staticmethod
    def _extract_company(title: str, text: str) -> str:
        # 优先从 title 提取(招聘信息常含公司名)
        m = re.match(r"^([^\s\-|【\[]+)", title)
        if m:
            return m.group(1).strip()[:30]
        return "未知"

    @staticmethod
    def _extract_location(text: str, target_cities: List[str]) -> str:
        for city in target_cities or ["北京", "上海", "深圳", "广州", "香港",
                                      "杭州", "成都", "南京", "武汉"]:
            if city in text:
                return city
        m = re.search(r"(北京|上海|深圳|广州|香港|杭州|成都|南京|武汉|苏州|厦门)", text)
        return m.group(1) if m else "不限"

    @staticmethod
    def _extract_salary(text: str) -> str:
        m = re.search(r"(\d+\.?\d*)\s*[-~到]\s*(\d+\.?\d*)\s*[kK万]", text)
        if m:
            return f"{m.group(1)}-{m.group(2)}K"
        m = re.search(r"(\d+)\s*[-~]\s*(\d+)\s*万", text)
        if m:
            return f"{m.group(1)}-{m.group(2)}万/年"
        return "面议"

    @staticmethod
    def _extract_posted_date(text: str) -> str:
        m = re.search(r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2})", text)
        if m:
            return m.group(1).replace("/", "-")
        m = re.search(r"(\d+)\s*天前", text)
        if m:
            days = int(m.group(1))
            from datetime import datetime, timedelta
            return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return "未知"
