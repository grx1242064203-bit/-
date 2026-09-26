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
    # 管理员 WxPusher UID — 每日任务失败时向其推送告警(不配置则仅记日志)
    ADMIN_WXPUSHER_UID: str = field(default_factory=lambda: os.getenv("ADMIN_WXPUSHER_UID", ""))

    # === 数据存储 ===
    DATA_DIR: str = field(default_factory=lambda: os.getenv("DATA_DIR", "/opt/job_assistant/data"))

    # === 服务域名（用于生成客户配置页链接） ===
    SERVICE_BASE_URL: str = field(default_factory=lambda: os.getenv("SERVICE_BASE_URL", "https://zhaopin-helper.xyz"))

    # === 运行参数 ===
    # 每个用户每日采集岗位数量上限
    DAILY_JOBS_PER_USER: int = int(os.getenv("DAILY_JOBS_PER_USER", "20"))
    # 飞书 API 写入重试次数
    FEISHU_RETRY: int = int(os.getenv("FEISHU_RETRY", "3"))
    # 飞书 API 调用间隔(秒),避免触发限流
    FEISHU_API_INTERVAL: float = float(os.getenv("FEISHU_API_INTERVAL", "0.2"))

    # === 目标机构白名单(已移除,由用户 profile.target_companies 自定义) ===
    # 全局不再硬编码任何行业机构,保持产品通用性

    # 通用招聘/求职网站域名(用于搜索时 site: 限定 + sitemap 穷举)
    # 保留少量通用域名,用户也可通过 profile 自定义
    JOB_BOARD_DOMAINS: List[str] = field(default_factory=lambda: [
        # 国内综合招聘
        "zhipin.com", "liepin.com", "51job.com", "zhaopin.com", "lagou.com",
        "maimai.cn", "linkedin.com",
        # 海外综合招聘
        "indeed.com", "glassdoor.com", "linkedin.com/jobs",
        # 外资企业招聘页(通用,不限行业)
        "careers.", "jobs.", "talent.",
    ])


settings = Settings()
