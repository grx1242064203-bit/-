"""
全局配置 — 所有敏感信息通过环境变量注入,不硬编码。
"""
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Settings:
    # === 飞书应用配置(在 open.feishu.cn 创建商店应用后获取) ===
    FEISHU_APP_ID: str = field(default_factory=lambda: os.getenv("FEISHU_APP_ID", ""))
    FEISHU_APP_SECRET: str = field(default_factory=lambda: os.getenv("FEISHU_APP_SECRET", ""))
    # 应用的 encrypt_key / verification_token(事件订阅用, MVP 可不填)
    FEISHU_ENCRYPT_KEY: str = field(default_factory=lambda: os.getenv("FEISHU_ENCRYPT_KEY", ""))
    FEISHU_VERIFICATION_TOKEN: str = field(default_factory=lambda: os.getenv("FEISHU_VERIFICATION_TOKEN", ""))

    # === WxPusher 配置(在 wxpusher.zjiecode.com 注册应用后获取) ===
    WXPUSHER_APP_TOKEN: str = field(default_factory=lambda: os.getenv("WXPUSHER_APP_TOKEN", ""))

    # === 数据存储 ===
    DATA_DIR: str = field(default_factory=lambda: os.getenv("DATA_DIR", "/workspace/job_assistant/data"))

    # === 运行参数 ===
    # 每个用户每日采集岗位数量上限
    DAILY_JOBS_PER_USER: int = int(os.getenv("DAILY_JOBS_PER_USER", "20"))
    # 飞书 API 写入重试次数
    FEISHU_RETRY: int = int(os.getenv("FEISHU_RETRY", "3"))
    # 飞书 API 调用间隔(秒),避免触发限流
    FEISHU_API_INTERVAL: float = float(os.getenv("FEISHU_API_INTERVAL", "0.2"))

    # === 目标机构白名单 ===
    TARGET_INSTITUTIONS: List[str] = field(default_factory=lambda: [
        # 内资头部券商
        "中金公司", "中信证券", "中信建投", "华泰证券", "国泰海通", "广发证券",
        "招商证券", "申万宏源", "中国银河", "东方证券", "兴业证券", "国信证券",
        # 内资头部公募/私募
        "易方达", "华夏基金", "南方基金", "博时基金", "汇添富", "嘉实基金",
        "富国基金", "鹏华基金", "兴全基金", "东方红", "中欧基金", "景林资产",
        "高毅资产", "幻方量化", "明汯投资", "九坤投资",
        # 外资
        "Goldman Sachs", "JPMorgan", "Morgan Stanley", "HSBC", "Standard Chartered",
        "UBS", "BlackRock", "Citi", "Deutsche Bank", "BNP Paribas", "Nomura",
        "Barclays", "Fidelity", "PIMCO", "Vanguard",
    ])

    # 外资招聘官网域名(用于 site: 搜索 + sitemap 穷举)
    FOREIGN_DOMAINS: List[str] = field(default_factory=lambda: [
        "jobs.standardchartered.com",
        "ajinga.com",          # HSBC 中国
        "careers.hsbc.com",
        "careers.gs.com",
        "careers.jpmorgan.com",
        "careers.morganstanley.com",
        "blackrock.com",
        "ubs.com",
        "careers.citi.com",
        "db.com",
        "careers.bnpparibas.com",
        "nomura.com",
        "careers.barclays.com",
        "careers.fidelity.com",
        "vanguardjobs.com",
        "pimco.com",
    ])


settings = Settings()
