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
    def search(self, query: str, max_results: int = 10,
               include_domains: List[str] = None) -> List[Dict]:
        """返回 [{title, url, snippet}]"""
        ...


class TavilySearchProvider(SearchProvider):
    """Tavily AI 搜索 — 有免费额度,适合金融信息搜索"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY", "")

    def search(self, query: str, max_results: int = 10,
               include_domains: List[str] = None) -> List[Dict]:
        if not self.api_key:
            logger.warning("TAVILY_API_KEY 未设置,跳过搜索")
            return []
        try:
            body = {
                "api_key": self.api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": False,
            }
            if include_domains:
                body["include_domains"] = include_domains
            resp = requests.post(
                "https://api.tavily.com/search",
                json=body,
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

    def search(self, query: str, max_results: int = 10,
               include_domains: List[str] = None) -> List[Dict]:
        if not self.api_key:
            return []
        try:
            params = {"q": query, "api_key": self.api_key, "num": max_results,
                      "engine": "google", "hl": "zh-cn"}
            if include_domains:
                # Google site: 操作符
                params["q"] = query + " " + " OR ".join(f"site:{d}" for d in include_domains)
            resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
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


# ========== 质量过滤函数 ==========

# 搜索/列表页 URL 特征(这些不是具体岗位详情页,应排除)
SEARCH_LISTING_PATTERNS = [
    r"/search", r"/job-list", r"/jobs/search", r"/jobs/list",
    r"/zhaopin/",  # 猎聘搜索页
    r"/web/geek/job",  # Boss直聘搜索结果页
    r"zhipin\.com/web",  # Boss直聘 web 端搜索
    r"\?q=", r"\?keyword=", r"\?query=", r"\?keywords=",
    r"search\?", r"list\?",
    r"/position/search", r"/recruit/search",
    r"linkedin\.com/jobs/search",  # 领英搜索(领英渠道已删除,兜底)
    r"/jobs/view/\?.*keywords",  # 带搜索参数的职位列表
]

# 岗位详情页特征(命中则保留)
JOB_DETAIL_PATTERNS = [
    r"/job_detail/",  # Boss直聘详情
    r"zhipin\.com/job/",  # Boss直聘详情
    r"/job/\d+",  # 通用职位详情
    r"/li/\d+",  # 猎聘详情
    r"/jobs/\d+", r"/job/\d+",
    r"/position/\d+", r"/position_detail",
    r"mp\.weixin\.qq\.com/s",  # 微信公众号文章
]

# JD 正文必须包含的岗位相关关键词(用于判断页面是否真的是招聘内容)
JOB_CONTENT_KEYWORDS = [
    "岗位职责", "岗位要求", "任职要求", "任职资格", "职位描述",
    "职位要求", "工作内容", "工作要求", "职责描述", "职责要求",
    "招聘", "岗位", "任职", "jd", "responsibilit", "requirement",
    "qualification", "we are hiring", "looking for",
]


def _is_search_listing_url(url: str) -> bool:
    """
    判断 URL 是否为搜索/列表页(而非具体岗位详情页)。
    这些页面是垃圾信息,应排除。
    """
    if not url:
        return True
    url_lower = url.lower()
    # 先检查是否是详情页(命中则不是搜索页)
    for pat in JOB_DETAIL_PATTERNS:
        if re.search(pat, url_lower):
            return False
    # 再检查是否是搜索页特征
    for pat in SEARCH_LISTING_PATTERNS:
        if re.search(pat, url_lower):
            return True
    # 智联/51job 的列表页特征
    if "zhaopin.com" in url_lower and "/job/" not in url_lower:
        if "search" in url_lower or "list" in url_lower or "?k=" in url_lower:
            return True
    if "51job.com" in url_lower and "search" in url_lower:
        return True
    return False


def _is_job_content(text: str) -> bool:
    """
    判断抓取到的文本是否包含岗位相关内容。
    排除非招聘页面(如公司介绍页、新闻页、404页等)。
    """
    if not text or len(text.strip()) < 50:
        return False
    text_lower = text.lower()
    # 必须至少命中 1 个岗位关键词
    hit_count = sum(1 for kw in JOB_CONTENT_KEYWORDS if kw in text_lower)
    return hit_count >= 1


def _is_role_mismatch(title: str, text: str, role: str) -> bool:
    """
    判断岗位是否与用户角色不匹配。
    - 社招用户:排除明确校招/应届/管培的岗位
    - 校招用户:排除明确要求多年工作经验的社招岗位
    - 实习用户:排除全职岗位
    """
    combined = (title + " " + text).lower()

    if role == "social":
        # 社招用户:排除校招/应届/管培(年份动态)
        from datetime import datetime as _dt
        _yr = _dt.now().year
        campus_kw = ["校招", "校园招聘", "应届", "应届生", "管培", "管培生",
                     "graduate program", "campus", "秋招", "春招",
                     f"{_yr}届", f"{_yr+1}届",
                     f"class of {_yr}", f"class of {_yr+1}"]
        return any(kw in combined for kw in campus_kw)

    elif role == "campus":
        # 校招用户:排除明确要求多年经验的社招岗位
        social_exp_patterns = [
            r"(\d+)\s*年以上工作经验", r"(\d+)\s*年工作经验",
            r"(\d+)\s*年以上相关经验", r"at least (\d+) years",
            r"(\d+)\+\s*years",
        ]
        for p in social_exp_patterns:
            m = re.search(p, combined)
            if m and int(m.group(1)) >= 3:
                return True
        # 硬编码的多年经验关键词(无捕获组,直接判定)
        hard_exp_kw = ["5年", "8年", "10年", "5 年", "8 年", "10 年",
                       "五年", "八年", "十年", "5+ years", "8+ years", "10+ years"]
        if any(kw in combined for kw in hard_exp_kw):
            return True
        # 明确标注"社招"且无应届字样
        if "社招" in combined and "应届" not in combined and "校招" not in combined:
            return True
        return False

    elif role == "internship":
        # 实习用户:排除全职岗位
        if "全职" in combined and "实习" not in combined:
            return True
        return False

    return False


def _is_too_old(posted_date_str: str, max_days: int = 365) -> bool:
    """
    判断岗位发布日期是否过老。
    max_days: 最大允许天数(社招 180 天,校招 365 天)
    """
    if not posted_date_str or posted_date_str == "未知":
        return False  # 日期未知时不过滤(避免误删)
    try:
        from datetime import datetime, timedelta
        # 尝试解析 YYYY-MM-DD 或 YYYY/MM/DD
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(posted_date_str, fmt)
                age = (datetime.now() - dt).days
                return age > max_days
            except ValueError:
                continue
    except Exception:
        pass
    return False


# ========== 采集器 ==========
class JobCollector:
    """岗位采集器 — 搜索 + 抓取 + 提取"""

    def __init__(self, provider: SearchProvider = None):
        self.provider = provider or get_search_provider()

    def _build_queries(self, profile, target_companies: List[str],
                       target_cities: List[str]) -> List[str]:
        """
        根据用户画像构建搜索关键词。
        优先级:方向关键词(精准) > 微信公众号(高质量) > 公司官网 > 社区

        核心修复:
        - 方向关键词驱动搜索,避免 role 为空时注入无关的通用管培/外资查询
        - role 为空时从 experience_years 推断(0年→campus,否则→social),不瞎猜
        """
        cities = " ".join(target_cities) if target_cities else ""
        companies = target_companies if target_companies else []
        directions = profile.direction_keywords or {}
        role = getattr(profile, "role", "") or ""

        # role 兜底:若未设置,从经验年限推断(0年→校招,有经验→社招)
        if not role:
            exp = getattr(profile, "experience_years", 0) or 0
            role = "campus" if exp == 0 else "social"

        queries = []

        # === 优先级1:用户方向关键词 + 招聘词(精准匹配,放最前面) ===
        # 方向关键词是用户画像的核心,必须优先搜索
        for direction, keywords in directions.items():
            if not keywords:
                continue
            # 用前 2-3 个关键词组合搜索,提高精准度
            core_kw = " ".join(keywords[:3])
            # 方向名 + 招聘 + 城市
            for city in (target_cities or [""]):
                q = f"{core_kw} 招聘 {city}".strip()
                if len(q) > 5:
                    queries.append(q)
            # 方向名 + 校招/实习/社招(按 role)
            if role == "internship":
                queries.append(f"{core_kw} 实习 招聘")
            elif role == "campus":
                queries.append(f"{core_kw} 校招 招聘")
                queries.append(f"{core_kw} 应届 招聘")
            else:
                queries.append(f"{core_kw} 社招 招聘")

        # === 优先级2:微信公众号(高质量、低噪声) ===
        for direction, keywords in directions.items():
            if not keywords:
                continue
            core_kw = " ".join(keywords[:2])
            for kw in settings.WECHAT_RECRUIT_KEYWORDS[:4]:
                queries.append(f"{core_kw} {kw} site:{settings.WECHAT_MP_DOMAIN}")
        # 重点公众号账号精确搜索(按行业匹配用户方向,避免不相关账号)
        relevant_accounts = self._match_wechat_accounts(directions)
        for account in relevant_accounts[:8]:
            for kw in settings.WECHAT_RECRUIT_KEYWORDS[:3]:
                queries.append(f"{account} {kw} site:{settings.WECHAT_MP_DOMAIN}")

        # === 优先级3:用户方向 + 目标公司 ===
        for direction, keywords in directions.items():
            if not keywords:
                continue
            core_kw = " ".join(keywords[:3])
            for comp in (companies or [""]):
                for city in (target_cities or [""]):
                    q = f"{comp} {core_kw} 招聘 {city}".strip()
                    if len(q) > 5:
                        queries.append(q)
            if not companies:
                queries.append(f"{core_kw} 招聘 {cities}".strip())

        # === 优先级4:角色专项(仅在 role 明确时注入,避免无关通用查询) ===
        if role == "internship":
            from datetime import datetime as _dt
            _yr = _dt.now().year
            queries.append(f"实习生 招聘 {_yr}")
            queries.append(f"internship hiring {_yr} china")
            for direction in directions:
                queries.append(f"{direction} 实习 招聘")
        elif role == "campus":
            from datetime import datetime as _dt
            _yr = _dt.now().year
            queries.append(f"管培生 校招 招聘 {_yr}")
            queries.append("应届生 校招 招聘")
            # 外资管培专项(校招用户重点)
            for fg in settings.FOREIGN_GRADUATE_KEYWORDS[:5]:
                queries.append(f"{fg} China {_yr}")
            # === 管培生项目专项(根据用户偏好 mt_program_preference) ===
            mt_pref = getattr(profile, "mt_program_preference", "all") or "all"
            mt_queries_by_pref = {
                "all": [
                    f"管培生 招聘 {_yr}", "管理培训生 校招",
                    f"MT program {_yr} China", "graduate trainee program",
                ],
                "finance": [
                    "银行管培生 校招", "券商管培生 招聘", "基金管培生",
                    f"金融管培生 {_yr}", "bank management trainee",
                ],
                "internet": [
                    "互联网管培生 校招", "产品管培生 招聘", "运营管培生",
                    f"技术管培生 {_yr}", "tech management trainee program",
                ],
                "consulting_fmcg": [
                    "咨询管培生 校招", "快消管培生 招聘",
                    "consulting graduate program", "FMCG management trainee",
                ],
                "soe": [
                    "国企管培生 校招", "央企管培生 招聘",
                    f"国企 管理培训生 {_yr}",
                ],
            }
            for mq in mt_queries_by_pref.get(mt_pref, mt_queries_by_pref["all"]):
                queries.append(mq)
        elif role == "social":
            from datetime import datetime as _dt
            _yr = _dt.now().year
            queries.append(f"社招 招聘 {_yr}")
            queries.append(f"experienced hire {_yr} china")

        # 用户专业相关
        if profile.major:
            queries.append(f"{profile.major} 招聘 {cities}".strip())

        # === 优先级5:公司招聘官网(site:限定) ===
        company_sites = []
        for tc in companies:
            for cs in settings.COMPANY_CAREER_SITES:
                if tc in cs["name"] or cs["name"] in tc:
                    company_sites.append(cs)
        if not company_sites:
            company_sites = settings.COMPANY_CAREER_SITES[:8]

        for cs in company_sites[:6]:
            domain = cs.get("campus_domain", cs["domain"]) if role in ("campus", "internship") else cs["domain"]
            for direction, keywords in directions.items():
                if not keywords:
                    continue
                core_kw = " ".join(keywords[:2])
                queries.append(f"{core_kw} 招聘 site:{domain}")
            if role == "campus":
                from datetime import datetime as _dt
                _yr = _dt.now().year
                queries.append(f"{cs['name']} 校招 {_yr} site:{domain}")

        # === 优先级6:外资官网管培专项(仅校招用户) ===
        if role == "campus":
            for fs in settings.FOREIGN_CAREER_SITES[:6]:
                for fg in settings.FOREIGN_GRADUATE_KEYWORDS[:3]:
                    queries.append(f"{fs['name']} {fg}")

        # === 优先级7:社区渠道 ===
        for cs in settings.COMMUNITY_SITES[:5]:
            for direction, keywords in directions.items():
                if not keywords:
                    continue
                core_kw = " ".join(keywords[:2])
                queries.append(f"{core_kw} 内推 site:{cs['domain']}")

        return list(dict.fromkeys(queries))[:30]

    @staticmethod
    def _match_wechat_accounts(directions: Dict[str, List[str]]) -> List[str]:
        """
        根据用户方向关键词匹配相关的微信公众号账号。
        避免对金融方向的用户推送互联网/快消类公众号文章。
        """
        if not directions:
            return settings.WECHAT_MP_ACCOUNTS[:8]

        # 合并所有方向关键词
        all_kw = set()
        for kws in directions.values():
            for kw in kws:
                all_kw.add(kw.lower())

        # 账号分组(与 config 中 WECHAT_MP_ACCOUNTS 对应)
        account_groups = {
            "金融": ["金融求职", "金融求职招聘", "券商招聘", "基金招聘",
                    "投行PEVC求职", "金融小伙伴", "券业星球", "Bank资管Street"],
            "互联网": ["互联网招聘", "Tech求职", "程序员工厂", "后端技术",
                      "牛客网", "程序员工厂"],
            "咨询快消": ["咨询求职", "快消求职", "外企招聘", "四大求职",
                       "Consulting-Case"],
            "国企": ["国企招聘", "事业单位招聘", "央企招聘", "选调生"],
            "综合": ["应届生求职", "校招薪水", "互联派", "职业僧", "offer先生",
                    "实习僧", "面包求职", "一起求职", "海归求职",
                    "刺猬实习", "白熊求职", "求职奶爸", "校招管家"],
        }

        # 判断用户方向属于哪个行业
        finance_kw = ["金融", "银行", "证券", "券商", "基金", "fof", "投资",
                      "投行", "pe", "vc", "资管", "保险", "信托", "量化"]
        internet_kw = ["互联网", "产品", "运营", "研发", "算法", "前端", "后端",
                       "java", "python", "数据", "程序员", "开发"]
        consulting_kw = ["咨询", "快消", "mbb", "贝恩", "麦肯锡", "bcg", "宝洁",
                         "联合利华", "欧莱雅"]
        soe_kw = ["国企", "央企", "公务员", "事业单位", "选调", "体制内"]

        matched_groups = []
        for kw in all_kw:
            if any(f in kw for f in finance_kw):
                matched_groups.append("金融")
            if any(i in kw for i in internet_kw):
                matched_groups.append("互联网")
            if any(c in kw for c in consulting_kw):
                matched_groups.append("咨询快消")
            if any(s in kw for s in soe_kw):
                matched_groups.append("国企")

        # 收集匹配的账号 + 综合类账号(兜底)
        result = []
        for group in set(matched_groups):
            result.extend(account_groups.get(group, []))
        result.extend(account_groups["综合"])
        return result[:12]

    def collect(self, profile, target_companies: List[str],
                target_cities: List[str], limit: int = 40) -> List[Dict]:
        """采集岗位,返回标准化的 job dict 列表

        质量过滤链(按顺序,任一不通过则跳过):
        1. URL 去重
        2. 排除搜索/列表页 URL(只保留具体岗位详情页)
        3. 标题关键词初筛
        4. 角色匹配(社招不搜校招岗,反之亦然)
        5. 抓取 JD 正文
        6. 内容校验(必须含岗位相关关键词)
        7. 发布日期过滤(排除过老岗位)
        """
        queries = self._build_queries(profile, target_companies, target_cities)
        seen_urls = set()
        jobs = []

        role = getattr(profile, "role", "") or ""
        if not role:
            exp = getattr(profile, "experience_years", 0) or 0
            role = "campus" if exp == 0 else "social"
        # 日期过滤阈值:社招 180 天,校招 365 天
        max_age_days = 180 if role == "social" else 365

        for q in queries:
            if len(jobs) >= limit:
                break

            # 微信公众号搜索:用 include_domains 替代 site:(Tavily 对 site: 支持不佳)
            include_domains = None
            if f"site:{settings.WECHAT_MP_DOMAIN}" in q:
                q = q.replace(f" site:{settings.WECHAT_MP_DOMAIN}", "")
                include_domains = [settings.WECHAT_MP_DOMAIN]

            results = self.provider.search(q, max_results=8, include_domains=include_domains)
            for r in results:
                if len(jobs) >= limit:
                    break
                url = r["url"]
                if not url or url in seen_urls:
                    continue

                # 过滤1:排除搜索/列表页 URL
                if _is_search_listing_url(url):
                    continue
                seen_urls.add(url)

                title = r["title"]
                all_target_kw = []
                for kws in (profile.direction_keywords or {}).values():
                    all_target_kw.extend(kws)
                all_target_kw += ["招聘", "hiring", "job", "position", "校招",
                                  "社招", "实习", "intern", "管培", "graduate"]
                if not any(kw.lower() in title.lower() for kw in all_target_kw):
                    continue

                # 过滤2:角色不匹配(社招排除校招岗,校招排除社招岗)
                snippet = r.get("snippet", "")
                if _is_role_mismatch(title, snippet, role):
                    continue

                # 抓取 JD
                jd_text = fetch_jd_by_source(url)
                full_text = jd_text or snippet

                # 过滤3:内容校验(必须含岗位相关关键词)
                if not _is_job_content(full_text):
                    continue

                # 过滤4:角色再次校验(基于完整 JD 正文)
                if _is_role_mismatch(title, full_text, role):
                    continue

                # 提取发布日期并过滤过老岗位
                posted = self._extract_posted_date(full_text)
                if _is_too_old(posted, max_age_days):
                    continue

                is_open = bool(jd_text)
                company = self._extract_company(title, full_text, url)
                location = self._extract_location(full_text, target_cities)
                salary = self._extract_salary(full_text)

                # 来源标记
                is_wechat = settings.WECHAT_MP_DOMAIN in url
                source = "微信公众号" if is_wechat else (
                    "公司官网" if any(cs["domain"] in url for cs in settings.COMPANY_CAREER_SITES) else
                    "社区" if any(cs["domain"] in url for cs in settings.COMMUNITY_SITES) else "搜索"
                )

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
                    "source": source,
                    "is_open": is_open,
                })
            time.sleep(0.3)

        return jobs

    @staticmethod
    def _extract_company(title: str, text: str, url: str = "") -> str:
        """
        提取公司名。优先级:
        1. URL 域名映射(最可靠,如 careers.tencent.com → 腾讯)
        2. title 中的 【公司名】 格式
        3. title 开头的公司名
        4. 正文中的"公司:"等标记
        """
        # 1. 从 URL 域名提取公司名(最可靠)
        if url:
            from urllib.parse import urlparse
            try:
                domain = urlparse(url).netloc.lower()
                # 精确匹配子域名
                if domain in settings.COMPANY_DOMAIN_MAP:
                    return settings.COMPANY_DOMAIN_MAP[domain]
                # 匹配主域名
                for dom, name in settings.COMPANY_DOMAIN_MAP.items():
                    if domain.endswith(dom) or dom in domain:
                        return name
            except Exception:
                pass

        # 2. 从 title 提取【公司名】
        m = re.search(r"【([^】]{2,20})】", title)
        if m:
            return m.group(1).strip()
        m = re.match(r"^([^\s\-|·【\[]+)", title)
        if m and len(m.group(1)) <= 30:
            return m.group(1).strip()
        # 3. 从正文中提取公司名
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
