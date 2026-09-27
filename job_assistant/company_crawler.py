"""
公司来源采集器 — 遍历公司库中的每家公司的信息来源,
发现 2027 届校招公告并入库到总数据库。

核心策略:
- 首次初始化:遍历所有公司(可分批)
- 之后每日:只扫描 has_2027_announcement=False 的公司
- 采集方式:Tavily site: 限定搜索(不直接爬网站,避免反爬)
- AI 检视:每条新公告入库前用 LLM 验证是否为有效的 2027 届校招
"""
import logging
import time
from typing import List, Dict

from campus_companies import CAMPUS_COMPANIES
from collector import (
    get_search_provider,
    fetch_jd_by_source,
    _is_allowed_campus_source,
    _is_job_content,
    _is_role_mismatch,
    _is_search_listing_url,
    JobCollector,
)
from config import settings
from llm_client import LLMClient
import job_db

logger = logging.getLogger(__name__)


class CompanyCrawler:
    """公司来源采集器"""

    def __init__(self):
        self.provider = get_search_provider()
        self.llm = LLMClient()
        self.collector = JobCollector(provider=self.provider)

    def _build_company_queries(self, company: Dict) -> List[str]:
        """
        为单家公司构建搜索查询。
        优先:官网域名 > 公众号 > 通用微信搜索
        """
        name = company["name"]
        queries = []
        # 官网域名定向搜索
        domain = company.get("career_domain", "")
        if domain:
            queries.append(f"{name} 校招 2027 site:{domain}")
            queries.append(f"{name} 校园招聘 2027 site:{domain}")
        # 微信公众号定向搜索
        wechat = company.get("wechat_account", "")
        if wechat:
            queries.append(f"{wechat} 校招 2027 site:{settings.WECHAT_MP_DOMAIN}")
        # 通用微信搜索(兜底)
        queries.append(f"{name} 校招 2027 site:{settings.WECHAT_MP_DOMAIN}")
        queries.append(f"{name} 2027届校园招聘")
        return queries

    def _search_one_company(self, company: Dict) -> List[Dict]:
        """搜索单家公司的 2027 校招公告,返回过滤后的原始结果"""
        queries = self._build_company_queries(company)
        all_results = []
        seen_urls = set()

        for q in queries[:3]:  # 每家公司最多 3 个查询,控制 API 用量
            try:
                results = self.provider.search(q, max_results=5)
            except Exception as e:
                logger.warning(f"搜索失败 [{company['name']}] {q}: {e}")
                continue
            for r in results:
                url = r.get("url", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                all_results.append(r)

        # 过滤:来源白名单 + 非搜索列表页 + 是岗位内容 + 非实习
        filtered = []
        for r in all_results:
            url = r.get("url", "")
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            if not _is_allowed_campus_source(url):
                continue
            if _is_search_listing_url(url):
                continue
            combined = " ".join(filter(None, [title, snippet]))
            if not _is_job_content(combined):
                continue
            if _is_role_mismatch(title, snippet, "campus"):
                continue
            filtered.append(r)
        return filtered

    def _process_announcement(self, company: Dict, r: Dict) -> bool:
        """
        处理单条公告:抓取 JD → AI 检视 → 生成摘要 → 入库。
        返回 True=成功入库, False=跳过。
        """
        url = r.get("url", "")
        title = r.get("title", "")
        snippet = r.get("snippet", "")

        # 抓取 JD 正文
        jd_text = fetch_jd_by_source(url, timeout=15)
        full_text = " ".join(filter(None, [title, snippet, jd_text]))

        # AI 检视:是否为有效的 2027 届校招公告
        verify = self.llm.verify_campus_announcement(
            title=title, jd_text=full_text, company=company["name"]
        )
        if not verify["is_valid"] or not verify["is_2027"]:
            logger.info(f"AI 检视未通过 [{company['name']}] {title[:40]}: "
                        f"valid={verify['is_valid']} is_2027={verify['is_2027']}")
            return False

        # AI 生成 JD 摘要
        jd_summary = self.llm.generate_jd_summary(jd_text or snippet, verify["job_title"])

        # 提取截止日期
        deadline = self.llm.extract_deadline(full_text)

        # 提取公司信息
        company_name = self.collector._extract_company(
            verify["job_title"], full_text, url
        ) or company["name"]

        # 入库到总数据库
        job = {
            "company": company_name,
            "job_title": verify["job_title"],
            "source": self._detect_source(url),
            "jd_url": url,
            "jd_summary": jd_summary,
            "industry": company.get("industry", ""),
            "company_type": company.get("type", ""),
            "difficulty": company.get("difficulty", ""),
            "deadline": deadline,
            "publish_time": verify.get("publish_time", ""),
        }
        inserted = job_db.insert_announcement(job)
        if inserted:
            logger.info(f"✓ 入库 [{company_name}] {verify['job_title'][:40]}")
            # 标记公司已发 2027 公告
            company["has_2027_announcement"] = True
            company["last_announcement_url"] = url
            company["last_announcement_date"] = verify.get("publish_time", "")
        return inserted

    @staticmethod
    def _detect_source(url: str) -> str:
        """判断来源类型"""
        url_lower = url.lower()
        if "mp.weixin.qq.com" in url_lower:
            return "微信公众号"
        if ".edu.cn" in url_lower:
            return "高校就业网"
        return "公司官网"

    def crawl(self, only_pending: bool = True, batch_size: int = 30) -> Dict:
        """
        执行采集。

        Args:
            only_pending: True=只扫未发公告的公司, False=扫所有公司(首次)
            batch_size: 每批处理公司数(控制 API 用量)

        Returns:
            {"scanned": N, "found": M, "inserted": K}
        """
        companies = CAMPUS_COMPANIES
        if only_pending:
            companies = [c for c in companies if not c.get("has_2027_announcement")]

        logger.info(f"开始采集: 待扫描公司 {len(companies)} 家 (only_pending={only_pending})")

        scanned = 0
        found = 0
        inserted = 0

        for i, company in enumerate(companies):
            scanned += 1
            try:
                results = self._search_one_company(company)
                if not results:
                    continue
                found += len(results)
                for r in results:
                    try:
                        if self._process_announcement(company, r):
                            inserted += 1
                    except Exception as e:
                        logger.warning(f"处理公告失败 [{company['name']}]: {e}")
            except Exception as e:
                logger.warning(f"搜索公司失败 [{company['name']}]: {e}")

            # 每 batch_size 家打一次进度
            if scanned % batch_size == 0:
                logger.info(f"进度: {scanned}/{len(companies)} 家, "
                            f"发现 {found} 条,入库 {inserted} 条")

            # 请求间隔,避免触发限流
            time.sleep(1)

        summary = {"scanned": scanned, "found": found, "inserted": inserted}
        logger.info(f"采集完成: {summary}")
        return summary


def run_daily_crawl():
    """每日采集入口:只扫描未发 2027 公告的公司"""
    job_db.init_db()
    crawler = CompanyCrawler()
    return crawler.crawl(only_pending=True)


def run_initial_crawl():
    """首次全量采集入口:扫描所有公司"""
    job_db.init_db()
    crawler = CompanyCrawler()
    return crawler.crawl(only_pending=False)
