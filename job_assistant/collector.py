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

from config import settings

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


# ========== 微信公众号文章解析 ==========
def fetch_wechat_article(url: str, timeout: int = 15) -> str:
    """
    抓取微信公众号文章正文,提取招聘相关信息。

    微信公众号文章页面结构:
    - <h1 id="activity-name"> 文章标题
    - <div id="js_content"> 正文内容
    - <span id="profileBt"> 公众号名称
    - <em id="publish_time"> 发布时间

    返回提取后的纯文本(含标题+正文),用于岗位信息提取。
    """
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
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")

        # 提取标题
        title_tag = soup.find("h1", id="activity-name")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # 提取公众号名称
        profile_tag = soup.find("span", id="profileBt")
        account = ""
        if profile_tag:
            strong = profile_tag.find("strong")
            account = strong.get_text(strip=True) if strong else profile_tag.get_text(strip=True)

        # 提取正文
        content_tag = soup.find("div", id="js_content")
        if content_tag:
            # 移除无关标签
            for tag in content_tag(["script", "style", "iframe"]):
                tag.decompose()
            content = content_tag.get_text(separator="\n", strip=True)
        else:
            content = soup.get_text(separator="\n", strip=True)

        # 提取发布时间
        publish_time = ""
        time_tag = soup.find("em", id="publish_time")
        if time_tag:
            publish_time = time_tag.get_text(strip=True)

        # 组装:标题 + 公众号 + 发布时间 + 正文
        parts = []
        if title:
            parts.append(f"标题: {title}")
        if account:
            parts.append(f"来源公众号: {account}")
        if publish_time:
            parts.append(f"发布时间: {publish_time}")
        parts.append(content)

        text = "\n".join(parts)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:8000]  # 截断,避免过长
    except Exception as e:
        logger.debug(f"抓取微信文章失败 {url}: {e}")
        return ""


# ========== 公司招聘官网 Sitemap 抓取 ==========
def fetch_company_career_sitemap(domain: str, timeout: int = 10) -> List[str]:
    """
    尝试抓取公司招聘官网的 sitemap.xml,返回职位列表页面 URL。

    常见 sitemap 路径:
    - /sitemap.xml
    - /sitemap_index.xml
    - /robots.txt 中声明的 sitemap

    注意:大多数公司招聘网站使用 JS 渲染,sitemap 可能不含职位链接。
    此函数作为辅助手段,主抓取仍依赖搜索 API。
    """
    job_urls = []
    sitemap_paths = [
        f"https://{domain}/sitemap.xml",
        f"https://{domain}/sitemap_index.xml",
        f"https://{domain}/sitemap_index.xml",
    ]
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"),
    }
    for sitemap_url in sitemap_paths:
        try:
            resp = requests.get(sitemap_url, headers=headers, timeout=timeout)
            if resp.status_code != 200:
                continue
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "xml")
            # 提取所有 <loc> 标签中的 URL
            for loc in soup.find_all("loc"):
                url = loc.get_text(strip=True)
                # 只保留疑似职位页面的 URL
                if any(kw in url.lower() for kw in ["job", "position", "career", "recruit", "zhaopin"]):
                    job_urls.append(url)
            if job_urls:
                break
        except Exception as e:
            logger.debug(f"抓取 sitemap 失败 {sitemap_url}: {e}")
            continue
    return job_urls[:20]  # 限制数量


# ========== 社区渠道内容提取 ==========
def fetch_community_content(url: str, domain: str, timeout: int = 15) -> str:
    """
    抓取社区渠道(脉脉/牛客/知乎等)的招聘帖子内容。

    不同社区页面结构不同,做通用化处理:
    - 提取页面标题
    - 提取正文区域(移除导航、侧边栏等)
    - 返回纯文本
    """
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
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")

        # 提取标题
        title = ""
        title_tag = soup.find("h1") or soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        # 移除无关元素
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()

        # 提取正文
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)

        result = f"标题: {title}\n{text}" if title else text
        return result[:6000]
    except Exception as e:
        logger.debug(f"抓取社区内容失败 {url}: {e}")
        return ""


def fetch_jd_by_source(url: str, timeout: int = 15) -> str:
    """
    根据 URL 来源选择对应的抓取策略:
    - mp.weixin.qq.com → 微信公众号文章解析
    - 公司招聘官网 → 普通 JD 抓取(sitemap 辅助)
    - 社区渠道 → 社区内容提取
    - 其他 → 通用 JD 抓取
    """
    if settings.WECHAT_MP_DOMAIN in url:
        return fetch_wechat_article(url, timeout)
    # 社区渠道
    community_domains = [cs["domain"] for cs in settings.COMMUNITY_SITES]
    for cd in community_domains:
        if cd in url:
            return fetch_community_content(url, cd, timeout)
    # 默认通用抓取
    return fetch_jd(url, timeout)


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
        拓展抓取源:微信公众号、公司招聘官网、社区渠道
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

        # === 拓展源1:微信公众号(site:mp.weixin.qq.com) ===
        # 招聘类公众号经常发布校招汇总、内推信息,覆盖搜索难以直接找到的岗位
        for direction, keywords in directions.items():
            core_kw = " ".join(keywords[:2])
            for kw in settings.WECHAT_RECRUIT_KEYWORDS[:3]:
                queries.append(f"{core_kw} {kw} site:{settings.WECHAT_MP_DOMAIN}")
        # 重点公众号账号精确搜索(intitle: 限定公众号名)
        for account in settings.WECHAT_MP_ACCOUNTS[:5]:
            for kw in settings.WECHAT_RECRUIT_KEYWORDS[:2]:
                queries.append(f"{account} {kw} site:{settings.WECHAT_MP_DOMAIN}")

        # === 拓展源2:主要公司招聘官网(site:限定) ===
        # 对用户目标公司或头部公司,直接搜索其招聘官网
        company_sites = []
        # 用户指定的目标公司优先匹配
        for tc in companies:
            for cs in settings.COMPANY_CAREER_SITES:
                if tc in cs["name"] or cs["name"] in tc:
                    company_sites.append(cs)
        # 若用户未指定公司,取头部互联网公司
        if not company_sites:
            company_sites = settings.COMPANY_CAREER_SITES[:10]

        for cs in company_sites[:8]:  # 限制公司数量,避免查询过多
            domain = cs.get("campus_domain", cs["domain"]) if role in ("campus", "internship", "") else cs["domain"]
            for direction, keywords in directions.items():
                core_kw = " ".join(keywords[:2])
                queries.append(f"{core_kw} 招聘 site:{domain}")
            # 公司名 + 校招/实习关键词,直接命中招聘页
            if role in ("campus", "internship", ""):
                queries.append(f"{cs['name']} 校招 2026 site:{domain}")
            else:
                queries.append(f"{cs['name']} 社招 招聘 site:{domain}")

        # === 拓展源3:社区渠道(site:限定) ===
        # 脉脉/牛客/应届生求职网等常有内推和一手招聘信息
        for cs in settings.COMMUNITY_SITES[:6]:
            for direction, keywords in directions.items():
                core_kw = " ".join(keywords[:2])
                queries.append(f"{core_kw} 招聘 内推 site:{cs['domain']}")

        return list(dict.fromkeys(queries))[:25]  # 去重,限 25 条

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

                # 抓取 JD(根据来源选择策略:微信文章/社区/通用)
                jd_text = fetch_jd_by_source(url)
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
        # 微信公众号文章标题常见格式:【公司名】岗位名 / 公司名-岗位名 / 公司名·岗位名
        m = re.search(r"【([^】]{2,20})】", title)
        if m:
            return m.group(1).strip()
        m = re.match(r"^([^\s\-|·【\[]+)", title)
        if m and len(m.group(1)) <= 30:
            return m.group(1).strip()
        # 从正文中提取公司名(匹配"公司:"/"单位:"/"招聘方:"等)
        m = re.search(r"(?:公司|单位|招聘方|雇主)[:：]\s*([^\n，,。]{2,30})", text)
        if m:
            return m.group(1).strip()
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
        # 微信公众号文章格式: 发布时间: 2024-XX-XX
        m = re.search(r"发布时间[:：]\s*(20\d{2}[-/]\d{1,2}[-/]\d{1,2})", text)
        if m:
            return m.group(1).replace("/", "-")
        m = re.search(r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2})", text)
        if m:
            return m.group(1).replace("/", "-")
        m = re.search(r"(\d+)\s*天前", text)
        if m:
            days = int(m.group(1))
            from datetime import datetime, timedelta
            return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return "未知"
