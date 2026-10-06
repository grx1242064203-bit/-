"""邮件分类服务（规则匹配，零 LLM 成本）。

分类规则（按用户给定关键词）：
- 测评：测评链接 / 性格测评 / 在线测评 / 测评截止
- 笔试：笔试邀请 / 笔试时间 / 笔试链接 / 在线笔试
- 面试：面试邀请 / 面试时间 / 会议链接 / 确认链接 / 面试安排 / 一面 / 二面 / 三面 / 终面
- 其他（宣讲会/广告）：不匹配以上关键词 → 跳过

提取信息：公司名、岗位名、事件时间、链接。

提供两层 API：
- classify_only(subject, body) -> str|None  仅初筛返回 task_type（用于异步 LLM 流程）
- classify_and_extract(...) -> dict|None   完整流水线（初筛+规则提取，LLM 不可用时的回退）
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from models.email import (
    TASK_TYPE_ASSESSMENT,
    TASK_TYPE_INTERVIEW,
    TASK_TYPE_WRITTEN,
)

# 关键词规则（按优先级：面试 > 笔试 > 测评，避免"面试安排"被误判）
RULES = [
    (
        TASK_TYPE_INTERVIEW,
        [
            "面试邀请", "面试时间", "面试安排", "面试通知",
            "会议链接", "确认链接", "腾讯会议", "zoom", "飞书会议",
            # 新增：一面/二面/三面/终面/HR面 等轮次关键词
            "一面", "二面", "三面", "终面", "hr面", "技术面", "主管面",
        ],
    ),
    (
        TASK_TYPE_WRITTEN,
        ["笔试邀请", "笔试时间", "笔试链接", "在线笔试", "笔试通知"],
    ),
    (
        TASK_TYPE_ASSESSMENT,
        ["测评链接", "性格测评", "在线测评", "测评截止", "测评通知", "测评链接"],
    ),
]

# 时间正则（覆盖常见格式）
TIME_PATTERNS = [
    # 2024-01-15 14:30
    r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2})",
    # 2024年1月15日 14:30
    r"(\d{4}年\d{1,2}月\d{1,2}日\s*\d{1,2}[:：]\d{2})",
    # 1月15日 14:30
    r"(\d{1,2}月\d{1,2}日\s*\d{1,2}[:：]\d{2})",
    # 01-15 14:30
    r"(\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2})",
]

# URL 正则
URL_PATTERN = re.compile(
    r"https?://[^\s<>\"'）\)]+",
    re.IGNORECASE,
)

# 公司名后缀（用于从发件人提取公司）
COMPANY_SUFFIXES = ["科技", "有限公司", "股份", "集团", "网络", "信息", "咨询", "金融", "银行"]


def classify_email(subject: str, body: str) -> Optional[str]:
    """根据主题+正文关键词初筛。返回 task_type 或 None（不匹配则跳过）。

    仅供异步 LLM 流程的初筛使用——零成本，快速过滤掉广告/宣讲会。
    """
    text = f"{subject}\n{body}".lower()
    for task_type, keywords in RULES:
        for kw in keywords:
            if kw.lower() in text:
                return task_type
    return None


# 别名：明确语义
classify_only = classify_email


def extract_company(subject: str, sender: str, body: str) -> Optional[str]:
    """提取公司名。优先从发件人域名，其次从主题/正文。"""
    # 从发件人邮箱域名推断（xx@company.com → company）
    domain_match = re.search(r"@([\w-]+)\.", sender or "")
    if domain_match:
        domain = domain_match.group(1).lower()
        # 过滤常见公共邮箱域名
        if domain not in {
            "qq", "163", "126", "gmail", "outlook", "hotmail", "sina",
            "foxmail", "yeah", "21cn", "139", "189", "aliyun",
        }:
            return domain_match.group(1)

    # 从主题中提取"XX公司"
    for suffix in COMPANY_SUFFIXES:
        m = re.search(rf"([\u4e00-\u9fa5A-Za-z0-9]+?){suffix}", subject or "")
        if m:
            return m.group(1) + suffix

    return None


def extract_job_title(subject: str, body: str) -> Optional[str]:
    """提取岗位名。匹配"XX岗"、"XX工程师"等。"""
    text = f"{subject}\n{body[:500]}"
    patterns = [
        r"([\u4e00-\u9fa5A-Za-z0-9+#]{2,15}工程师)",
        r"([\u4e00-\u9fa5A-Za-z0-9+#]{2,15}岗)",
        r"([\u4e00-\u9fa5A-Za-z0-9+#]{2,15}经理)",
        r"([\u4e00-\u9fa5A-Za-z0-9+#]{2,15}专员)",
        r"([\u4e00-\u9fa5A-Za-z0-9+#]{2,15}分析师)",
        r"([\u4e00-\u9fa5A-Za-z0-9+#]{2,15}设计师)",
        r"([\u4e00-\u9fa5A-Za-z0-9+#]{2,15}运营)",
        r"([\u4e00-\u9fa5A-Za-z0-9+#]{2,15}产品)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1)
    return None


def extract_event_time(subject: str, body: str) -> Optional[str]:
    """提取事件时间，返回 ISO 格式字符串。解析失败返回 None。"""
    text = f"{subject}\n{body[:2000]}"
    for pattern in TIME_PATTERNS:
        m = re.search(pattern, text)
        if m:
            raw = m.group(1)
            parsed = _parse_time(raw)
            if parsed:
                return parsed
    return None


def _parse_time(raw: str) -> Optional[str]:
    """将各种时间字符串解析为 ISO 格式。"""
    raw = raw.strip()
    # 统一分隔符
    raw = raw.replace("年", "-").replace("月", "-").replace("日", " ")
    raw = raw.replace("/", "-").replace("：", ":")

    for fmt in [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%m-%d %H:%M",
        "%m-%d %H:%M:%S",
    ]:
        try:
            dt = datetime.strptime(raw, fmt)
            # 如果没有年份，补当前年
            if dt.year == 1900:
                dt = dt.replace(year=datetime.now().year)
            return dt.isoformat()
        except ValueError:
            continue
    return None


def extract_links(body: str, task_type: str) -> tuple[Optional[str], list[str]]:
    """提取事件链接和所有链接。
    返回 (event_link, all_links)。event_link 优先取会议/笔试/测评链接。
    """
    urls = URL_PATTERN.findall(body or "")
    if not urls:
        return None, []

    # 去重保序
    seen = set()
    unique_urls = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    # 按类型选主链接
    event_link = None
    if task_type == TASK_TYPE_INTERVIEW:
        meeting_domains = ["meeting", "zoom", "tencent", "feishu", "lark", "teams", "webex"]
        for u in unique_urls:
            if any(d in u.lower() for d in meeting_domains):
                event_link = u
                break
    elif task_type == TASK_TYPE_WRITTEN:
        for u in unique_urls:
            if any(k in u.lower() for k in ["exam", "test", "笔试", "written"]):
                event_link = u
                break
    elif task_type == TASK_TYPE_ASSESSMENT:
        for u in unique_urls:
            if any(k in u.lower() for k in ["assessment", "测评", "survey", "性格"]):
                event_link = u
                break

    if event_link is None and unique_urls:
        event_link = unique_urls[0]

    return event_link, unique_urls


def build_email_link(message_id: str, imap_server: str) -> str:
    """构建邮件回链（用于前端跳转回邮件）。"""
    return f"imap://{imap_server}/{message_id}"


def classify_and_extract(
    subject: str, body: str, sender: str, message_id: str, imap_server: str
) -> Optional[dict]:
    """完整分类+提取流水线。返回任务数据 dict 或 None（不匹配跳过）。"""
    task_type = classify_email(subject, body)
    if task_type is None:
        return None

    event_time = extract_event_time(subject, body)
    event_link, _ = extract_links(body, task_type)

    return {
        "task_type": task_type,
        "company": extract_company(subject, sender, body),
        "job_title": extract_job_title(subject, body),
        "event_time": event_time,
        "event_link": event_link,
        "email_link": build_email_link(message_id, imap_server),
        "notes": f"主题: {subject}",
    }
