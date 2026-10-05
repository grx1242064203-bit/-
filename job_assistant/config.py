"""
全局配置 — 所有敏感信息通过环境变量注入,不硬编码。
支持 .env 文件(项目根目录),方便本地开发和部署。
"""
import os
from dataclasses import dataclass, field
from typing import Dict, List

# 加载 .env 文件(如果存在),不覆盖已设置的环境变量
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass


@dataclass
class Settings:
    # === 飞书应用配置(在 open.feishu.cn 创建商店应用后获取) ===
    FEISHU_APP_ID: str = field(default_factory=lambda: os.getenv("FEISHU_APP_ID", ""))
    FEISHU_APP_SECRET: str = field(default_factory=lambda: os.getenv("FEISHU_APP_SECRET", ""))
    # 应用的 encrypt_key / verification_token(事件订阅用, MVP 可不填)
    FEISHU_ENCRYPT_KEY: str = field(default_factory=lambda: os.getenv("FEISHU_ENCRYPT_KEY", ""))
    FEISHU_VERIFICATION_TOKEN: str = field(default_factory=lambda: os.getenv("FEISHU_VERIFICATION_TOKEN", ""))

    # === WxPusher 配置(已降级为可选辅助通道,主推送走飞书) ===
    WXPUSHER_APP_TOKEN: str = field(default_factory=lambda: os.getenv("WXPUSHER_APP_TOKEN", ""))
    # 管理员 WxPusher UID — 每日任务失败时向其推送告警(不配置则仅记日志)
    ADMIN_WXPUSHER_UID: str = field(default_factory=lambda: os.getenv("ADMIN_WXPUSHER_UID", ""))

    # === LLM 配置(DeepSeek,用于简历解析) ===
    DEEPSEEK_API_KEY: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))

    # === 数据存储 ===
    DATA_DIR: str = field(default_factory=lambda: os.getenv("DATA_DIR", "/opt/job_assistant/data"))

    # === 飞书秋招源表(中心化数据源,每日更新) ===
    # 来源: https://dcn2fr2wam82.feishu.cn/base/WfgTb3wE3aSGhesttvack8innbh?table=tblcBX0o8CIJlQQr
    SOURCE_APP_TOKEN: str = field(default_factory=lambda: os.getenv("SOURCE_APP_TOKEN", "WfgTb3wE3aSGhesttvack8innbh"))
    SOURCE_TABLE_ID: str = field(default_factory=lambda: os.getenv("SOURCE_TABLE_ID", "tblcBX0o8CIJlQQr"))

    # === 飞书总表(公司+岗位+VL失败记录,供用户直接查看) ===
    MASTER_APP_TOKEN: str = field(default_factory=lambda: os.getenv("MASTER_APP_TOKEN", "J8qtbBvPdatotysARtbc2XcinDJ"))
    MASTER_COMPANY_TABLE_ID: str = field(default_factory=lambda: os.getenv("MASTER_COMPANY_TABLE_ID", "tblRsw7CEIvR7dRB"))
    MASTER_POSITION_TABLE_ID: str = field(default_factory=lambda: os.getenv("MASTER_POSITION_TABLE_ID", "tblwrGXMK17WHzk3"))
    MASTER_VL_FAILURE_TABLE_ID: str = field(default_factory=lambda: os.getenv("MASTER_VL_FAILURE_TABLE_ID", "tblDVGCS9CbLrqFH"))

    # === 服务域名（用于生成客户配置页链接） ===
    SERVICE_BASE_URL: str = field(default_factory=lambda: os.getenv("SERVICE_BASE_URL", "https://zhaopin-helper.xyz"))

    # === 运行参数 ===
    # 每个用户每日采集岗位数量上限(调大,但通过质量过滤保证精度)
    DAILY_JOBS_PER_USER: int = int(os.getenv("DAILY_JOBS_PER_USER", "60"))
    # 飞书 API 写入重试次数
    FEISHU_RETRY: int = int(os.getenv("FEISHU_RETRY", "3"))
    # 飞书 API 调用间隔(秒),避免触发限流
    FEISHU_API_INTERVAL: float = float(os.getenv("FEISHU_API_INTERVAL", "0.2"))

    # === 目标机构白名单(已移除,由用户 profile.target_companies 自定义) ===
    # 全局不再硬编码任何行业机构,保持产品通用性

    # 通用招聘/求职网站域名(用于搜索时 site: 限定 + sitemap 穷举)
    # 已移除 linkedin.com(国内使用率低)
    JOB_BOARD_DOMAINS: List[str] = field(default_factory=lambda: [
        # 国内综合招聘
        "zhipin.com", "liepin.com", "51job.com", "zhaopin.com", "lagou.com",
        "maimai.cn",
        # 海外综合招聘
        "indeed.com", "glassdoor.com",
        # 外资企业招聘页(通用,不限行业)
        "careers.", "jobs.", "talent.",
    ])

    # === 拓展抓取源:微信公众号 ===
    # 微信公众号是高质量招聘信息源(垃圾信息少),优先采集
    WECHAT_MP_DOMAIN: str = "mp.weixin.qq.com"
    # 招聘类公众号关键词(用于搜索时限定主题)
    WECHAT_RECRUIT_KEYWORDS: List[str] = field(default_factory=lambda: [
        "校招", "内推", "招聘", "春招", "秋招", "实习", "管培",
        "社招", "应届", "补录", "提前批",
    ])
    # 重点招聘类公众号账号名(用于 intitle: 精确搜索,覆盖一手校招/内推信息)
    # 按行业分组,确保覆盖不同求职方向
    WECHAT_MP_ACCOUNTS: List[str] = field(default_factory=lambda: [
        # 综合校招/实习
        "应届生求职", "校招薪水", "互联派", "职业僧", "offer先生",
        "实习僧", "牛客网", "面包求职", "一起求职", "海归求职",
        "刺猬实习", "白熊求职", "求职奶爸", "校招管家",
        # 金融/券商/基金
        "金融求职", "金融求职招聘", "券商招聘", "基金招聘",
        "投行PEVC求职", "金融小伙伴", "券业星球", "Bank资管Street",
        # 互联网/科技
        "互联网招聘", "Tech求职", "程序员工厂", "后端技术",
        # 咨询/快消/外企
        "咨询求职", "快消求职", "外企招聘", "四大求职",
        "Consulting-Case",
        # 国企/央企/事业单位
        "国企招聘", "事业单位招聘", "央企招聘", "选调生",
    ])

    # === 拓展抓取源:主要公司招聘官网 ===
    # 直接抓取公司 career 页面,覆盖互联网/金融/快消等行业头部公司
    COMPANY_CAREER_SITES: List[Dict[str, str]] = field(default_factory=lambda: [
        # 互联网
        {"name": "字节跳动", "domain": "jobs.bytedance.com", "campus_domain": "campus.bytedance.com"},
        {"name": "腾讯", "domain": "careers.tencent.com", "campus_domain": "join.qq.com"},
        {"name": "阿里巴巴", "domain": "talent.alibaba.com", "campus_domain": "campus.alibaba.com"},
        {"name": "百度", "domain": "talent.baidu.com", "campus_domain": "campus.baidu.com"},
        {"name": "美团", "domain": "zhaopin.meituan.com", "campus_domain": "campus.meituan.com"},
        {"name": "京东", "domain": "zhaopin.jd.com", "campus_domain": "campus.jd.com"},
        {"name": "网易", "domain": "hr.163.com", "campus_domain": "campus.163.com"},
        {"name": "快手", "domain": "zhaopin.kuaishou.cn", "campus_domain": "campus.kuaishou.cn"},
        {"name": "小米", "domain": "hr.xiaomi.com", "campus_domain": "campus.hr.xiaomi.com"},
        {"name": "滴滴", "domain": "talent.didiglobal.com", "campus_domain": "campus.didiglobal.com"},
        {"name": "拼多多", "domain": "careers.pinduoduo.com", "campus_domain": "careers.pinduoduo.com"},
        {"name": "B站", "domain": "jobs.bilibili.com", "campus_domain": "campus.bilibili.com"},
        {"name": "携程", "domain": "job.ctrip.com", "campus_domain": "campus.ctrip.com"},
        {"name": "华为", "domain": "career.huawei.com", "campus_domain": "career.huawei.com"},
        {"name": "OPPO", "domain": "career.oppo.com", "campus_domain": "career.oppo.com"},
        {"name": "vivo", "domain": "hr.vivo.com", "campus_domain": "hr.vivo.com"},
        {"name": "大疆", "domain": "we.dji.com", "campus_domain": "we.dji.com"},
        {"name": "小红书", "domain": "job.xiaohongshu.com", "campus_domain": "job.xiaohongshu.com"},
        # 金融
        {"name": "招商银行", "domain": "career.cmbchina.com", "campus_domain": "career.cmbchina.com"},
        {"name": "中信证券", "domain": "career.cs.ecitic.com", "campus_domain": "career.cs.ecitic.com"},
        {"name": "中金公司", "domain": "cicc.zhiye.com", "campus_domain": "cicc.zhiye.com"},
        {"name": "华泰证券", "domain": "job.htsc.com.cn", "campus_domain": "job.htsc.com.cn"},
        {"name": "工商银行", "domain": "job.icbc.com.cn", "campus_domain": "job.icbc.com.cn"},
        {"name": "建设银行", "domain": "job.ccb.com", "campus_domain": "job.ccb.com"},
        {"name": "平安集团", "domain": "talent.pingan.com", "campus_domain": "campus.pingan.com"},
        {"name": "高盛", "domain": "goldmansachs.com/careers", "campus_domain": "goldmansachs.com/careers"},
        {"name": "摩根士丹利", "domain": "morganstanley.com/careers", "campus_domain": "morganstanley.com/careers"},
        # 快消/外企
        {"name": "宝洁", "domain": "pg.com.cn", "campus_domain": "pg.com.cn"},
        {"name": "联合利华", "domain": "unilever.com.cn", "campus_domain": "unilever.com.cn"},
        {"name": "欧莱雅", "domain": "loreal.com.cn", "campus_domain": "loreal.com.cn"},
        {"name": "玛氏", "domain": "mars.com", "campus_domain": "mars.com"},
        {"name": "雀巢", "domain": "nestle.com.cn", "campus_domain": "nestle.com.cn"},
        {"name": "可口可乐", "domain": "coca-cola.com.cn", "campus_domain": "coca-cola.com.cn"},
        # 咨询
        {"name": "麦肯锡", "domain": "mckinsey.com/careers", "campus_domain": "mckinsey.com/careers"},
        {"name": "波士顿咨询", "domain": "bcg.com/careers", "campus_domain": "bcg.com/careers"},
        {"name": "贝恩咨询", "domain": "bain.com/careers", "campus_domain": "bain.com/careers"},
        # 国企/央企
        {"name": "国家电网", "domain": "zhaopin.sgcc.com.cn", "campus_domain": "zhaopin.sgcc.com.cn"},
        {"name": "中石油", "domain": "zhaopin.cnpc.com.cn", "campus_domain": "zhaopin.cnpc.com.cn"},
        {"name": "中石化", "domain": "job.sinopec.com", "campus_domain": "job.sinopec.com"},
    ])

    # === 外资公司招聘官网(sitemap 直采,覆盖 China+HK 岗位) ===
    # 外资官网 JD 质量高,通过 sitemap.xml 穷举 + site: 搜索兜底
    FOREIGN_CAREER_SITES: List[Dict[str, str]] = field(default_factory=lambda: [
        {"name": "Goldman Sachs", "domain": "careers.gs.com", "sitemap": True},
        {"name": "JPMorgan", "domain": "careers.jpmorgan.com", "sitemap": True},
        {"name": "Morgan Stanley", "domain": "careers.morganstanley.com", "sitemap": True},
        {"name": "HSBC", "domain": "careers.hsbc.com", "sitemap": True},
        {"name": "Standard Chartered", "domain": "jobs.standardchartered.com", "sitemap": True},
        {"name": "UBS", "domain": "ubs.com", "sitemap": True},
        {"name": "BlackRock", "domain": "blackrock.com", "sitemap": True},
        {"name": "Citi", "domain": "careers.citi.com", "sitemap": True},
        {"name": "Deutsche Bank", "domain": "db.com", "sitemap": True},
        {"name": "BNP Paribas", "domain": "careers.bnpparibas.com", "sitemap": True},
        {"name": "Nomura", "domain": "nomura.com", "sitemap": True},
        {"name": "Barclays", "domain": "careers.barclays.com", "sitemap": True},
        {"name": "Fidelity", "domain": "careers.fidelity.com", "sitemap": True},
        {"name": "Vanguard", "domain": "vanguardjobs.com", "sitemap": True},
        {"name": "PIMCO", "domain": "pimco.com", "sitemap": True},
    ])

    # 外资管培/ Graduate Program 专项搜索关键词
    FOREIGN_GRADUATE_KEYWORDS: List[str] = field(default_factory=lambda: [
        "graduate program", "analyst program", "management trainee",
        "graduate scheme", "rotational program", "early careers",
        "campus recruiting", "graduate opportunity", "full-time analyst",
        "new analyst program", "graduate talent program",
    ])

    # === 拓展抓取源:社区渠道 ===
    # 通过 site: 限定搜索招聘相关帖子
    COMMUNITY_SITES: List[Dict[str, str]] = field(default_factory=lambda: [
        {"name": "脉脉", "domain": "maimai.cn", "type": "职场社交"},
        {"name": "知乎", "domain": "zhihu.com", "type": "问答社区"},
        {"name": "小红书", "domain": "xiaohongshu.com", "type": "生活分享"},
        {"name": "V2EX", "domain": "v2ex.com", "type": "技术社区"},
        {"name": "豆瓣", "domain": "douban.com", "type": "小组讨论"},
        {"name": "即刻", "domain": "okjike.com", "type": "兴趣社交"},
        {"name": "牛客网", "domain": "nowcoder.com", "type": "求职社区"},
        {"name": "应届生求职网", "domain": "yingjiesheng.com", "type": "校招平台"},
        {"name": "看准网", "domain": "kanzhun.com", "type": "公司评价"},
        {"name": "一亩三分地", "domain": "1point3acres.com", "type": "留学求职"},
        {"name": "Boss直聘社区", "domain": "zhipin.com", "type": "招聘平台"},
        {"name": "猎聘", "domain": "liepin.com", "type": "中高端招聘"},
    ])

    # === 公司域名 → 公司名映射(用于从 URL 提取公司名) ===
    # 覆盖头部互联网/金融/快消/咨询/国企,从 URL 域名直接推断公司名
    COMPANY_DOMAIN_MAP: Dict[str, str] = field(default_factory=lambda: {
        # 互联网
        "bytedance.com": "字节跳动", "jobs.bytedance.com": "字节跳动",
        "tencent.com": "腾讯", "careers.tencent.com": "腾讯",
        "alibaba.com": "阿里巴巴", "talent.alibaba.com": "阿里巴巴",
        "baidu.com": "百度", "talent.baidu.com": "百度",
        "meituan.com": "美团", "zhaopin.meituan.com": "美团",
        "jd.com": "京东", "zhaopin.jd.com": "京东",
        "163.com": "网易", "hr.163.com": "网易",
        "kuaishou.com": "快手", "zhaopin.kuaishou.cn": "快手",
        "xiaomi.com": "小米", "hr.xiaomi.com": "小米",
        "didiglobal.com": "滴滴", "talent.didiglobal.com": "滴滴",
        "pinduoduo.com": "拼多多", "careers.pinduoduo.com": "拼多多",
        "bilibili.com": "B站", "jobs.bilibili.com": "B站",
        "ctrip.com": "携程", "job.ctrip.com": "携程",
        "huawei.com": "华为", "career.huawei.com": "华为",
        "oppo.com": "OPPO", "career.oppo.com": "OPPO",
        "vivo.com": "vivo", "hr.vivo.com": "vivo",
        "dji.com": "大疆", "we.dji.com": "大疆",
        "xiaohongshu.com": "小红书", "job.xiaohongshu.com": "小红书",
        # 金融
        "cmbchina.com": "招商银行", "career.cmbchina.com": "招商银行",
        "citic.com": "中信证券", "career.cs.ecitic.com": "中信证券",
        "cicc.com": "中金公司", "cicc.zhiye.com": "中金公司",
        "htsc.com.cn": "华泰证券", "job.htsc.com.cn": "华泰证券",
        "icbc.com.cn": "工商银行", "job.icbc.com.cn": "工商银行",
        "ccb.com": "建设银行", "job.ccb.com": "建设银行",
        "pingan.com": "平安集团", "talent.pingan.com": "平安集团",
        "goldmansachs.com": "高盛",
        "morganstanley.com": "摩根士丹利",
        "jpmorgan.com": "摩根大通",
        "hsbc.com": "汇丰银行",
        "ubs.com": "瑞银",
        "blackrock.com": "贝莱德",
        "citi.com": "花旗银行",
        "db.com": "德意志银行",
        # 快消/外企
        "pg.com.cn": "宝洁",
        "unilever.com.cn": "联合利华",
        "loreal.com.cn": "欧莱雅",
        "mars.com": "玛氏",
        "nestle.com.cn": "雀巢",
        "coca-cola.com.cn": "可口可乐",
        # 咨询
        "mckinsey.com": "麦肯锡",
        "bcg.com": "波士顿咨询",
        "bain.com": "贝恩咨询",
        # 国企
        "sgcc.com.cn": "国家电网", "zhaopin.sgcc.com.cn": "国家电网",
        "cnpc.com.cn": "中石油", "zhaopin.cnpc.com.cn": "中石油",
        "sinopec.com": "中石化", "job.sinopec.com": "中石化",
    })

    # === 管培生项目分类(校招用户可选) ===
    # all=全部, finance=金融, internet=互联网, consulting_fmcg=咨询快消, soe=国企央企
    MT_PROGRAM_CATEGORIES: Dict[str, str] = field(default_factory=lambda: {
        "all": "全部管培生项目",
        "finance": "金融管培(银行/券商/基金)",
        "internet": "互联网管培(产品/运营/技术)",
        "consulting_fmcg": "咨询快消管培",
        "soe": "国企央企管培",
    })


settings = Settings()


def get_settings() -> Settings:
    """返回 Settings 单例。供 job_api 子模块统一获取配置。"""
    return settings
