"""
校招企业清单 — 2024-2026 年实际发布校招公告的企业。
每个企业标注:公司类型、申请难度、行业。
用于校招用户的画像匹配和精准采集。

数据来源:各企业官方招聘公众号、校招汇总平台(offer多多、中公教育等)、
行业公开信息。覆盖互联网/金融/快消/咨询/制造/能源/通信/医药等行业。
"""

# 公司类型
COMPANY_TYPE_SOE = "国央企"       # 国有/央企
COMPANY_TYPE_PRIVATE = "民企"     # 民营企业
COMPANY_TYPE_FOREIGN = "外企"     # 外资企业

# 申请难度
DIFFICULTY_HIGHEST = "最激烈"
DIFFICULTY_HIGH = "较为激烈"
DIFFICULTY_MEDIUM = "中等难度"
DIFFICULTY_LOW = "较低难度"

# 行业(与 mappings.json 的 industry_categories 标准分类名保持一致,
# 确保 get_companies_by_filters 按用户选择的 target_industries 精确匹配)
INDUSTRY_INTERNET = "互联网/科技"
INDUSTRY_FINANCE = "金融"
INDUSTRY_FMCG = "消费/零售/快消"
INDUSTRY_CONSULTING = "咨询/专业服务"
INDUSTRY_MANUFACTURING = "制造/工业"
INDUSTRY_ENERGY = "能源/公用事业"
INDUSTRY_TELECOM = "互联网/科技"
INDUSTRY_AUTO = "制造/工业"
INDUSTRY_MEDICAL = "医疗/医药/健康"
INDUSTRY_REALESTATE = "房地产/建筑"
INDUSTRY_OVERSEAS = "其他"
INDUSTRY_LOGISTICS = "交通/物流"
INDUSTRY_EDUCATION = "教育/培训"
INDUSTRY_SEMICONDUCTOR = "制造/工业"
INDUSTRY_GAME = "传媒/文娱/游戏"
INDUSTRY_ACCOUNTING = "咨询/专业服务"
INDUSTRY_RETAIL = "消费/零售/快消"

# 校招企业清单(2024-2026 实际发布校招公告)
CAMPUS_COMPANIES = [
    # ========== 互联网/科技 ==========
    {"name": "阿里巴巴", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_INTERNET},
    {"name": "腾讯", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_INTERNET},
    {"name": "字节跳动", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_INTERNET},
    {"name": "美团", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_INTERNET},
    {"name": "京东", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "百度", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "华为", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_INTERNET},
    {"name": "小米", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "网易", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "快手", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "拼多多", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_INTERNET},
    {"name": "小红书", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_INTERNET},
    {"name": "哔哩哔哩", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "滴滴", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "携程", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "新浪微博", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "知乎", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "蚂蚁集团", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "菜鸟网络", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "阿里云", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "腾讯云", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "华为云", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "金山办公", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "用友网络", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "金蝶软件", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "深信服", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "奇安信", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "启明星辰", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "三六零", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    # 互联网/科技 第二梯队
    {"name": "得物", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "唯品会", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "贝壳找房", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "同程旅行", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "去哪儿网", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "Boss直聘", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "58同城", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_INTERNET},
    {"name": "汽车之家", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "易车", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_INTERNET},
    {"name": "陌陌", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "探探", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "雪球", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "东方财富", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "同花顺", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "富途", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "OPPO", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "vivo", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "荣耀", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "realme", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "大疆创新", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_MANUFACTURING},
    {"name": "科大讯飞", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "商汤科技", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "旷视科技", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_INTERNET},
    {"name": "依图科技", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "云从科技", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "格灵深瞳", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "海康威视", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MANUFACTURING},
    {"name": "大华股份", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "浪潮信息", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "中科曙光", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "紫光股份", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "神州数码", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_INTERNET},
    {"name": "恒生电子", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "广联达", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "金山软件", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "迅雷", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_INTERNET},
    {"name": "美图公司", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_INTERNET},
    {"name": "喜马拉雅", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "蜻蜓FM", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_INTERNET},
    {"name": "什么值得买", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_INTERNET},
    {"name": "豆瓣", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_INTERNET},
    {"name": "脉脉", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "懂车帝", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_INTERNET},
    {"name": "安居客", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_INTERNET},
    {"name": "中软国际", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_INTERNET},
    {"name": "软通动力", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_INTERNET},
    {"name": "东软集团", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_INTERNET},
    {"name": "文思海辉", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_INTERNET},

    # ========== 游戏 ==========
    {"name": "米哈游", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_GAME},
    {"name": "莉莉丝游戏", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_GAME},
    {"name": "叠纸游戏", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_GAME},
    {"name": "鹰角网络", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_GAME},
    {"name": "完美世界", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_GAME},
    {"name": "吉比特", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_GAME},
    {"name": "三七互娱", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_GAME},
    {"name": "盛趣游戏", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_GAME},
    {"name": "多益网络", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_GAME},
    {"name": "网龙网络", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_GAME},
    # 游戏 第二梯队
    {"name": "巨人网络", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_GAME},
    {"name": "4399游戏", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_GAME},
    {"name": "游族网络", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_GAME},
    {"name": "掌趣科技", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_GAME},
    {"name": "盛天网络", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_GAME},
    {"name": "雷霆游戏", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_GAME},
    {"name": "库洛游戏", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_GAME},
    {"name": "散爆网络", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_GAME},
    {"name": "青瓷游戏", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_GAME},
    {"name": "西山居", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_GAME},

    # ========== 银行 ==========
    {"name": "中国工商银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "中国建设银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "中国农业银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "中国银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "交通银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "招商银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "中信银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "浦发银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "民生银行", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "兴业银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "光大银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "华夏银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "平安银行", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "广发银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "北京银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "上海银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "宁波银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "江苏银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "南京银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "杭州银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "徽商银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    # 银行 补充
    {"name": "中国邮政储蓄银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "浙商银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "恒丰银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "渤海银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "齐鲁银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "青岛银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "郑州银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "长沙银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "成都银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "苏州银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "重庆银行", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},

    # ========== 证券/基金 ==========
    {"name": "中信证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "华泰证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "国泰君安", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "海通证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "广发证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "招商证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "中金公司", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "申万宏源", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "东方证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "光大证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "平安证券", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "易方达基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "华夏基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "南方基金", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "嘉实基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "富国基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "汇添富基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "招商基金", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "博时基金", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "银华基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "工银瑞信基金", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "建信基金", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "天弘基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "中欧基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "景顺长城基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    # 证券 补充
    {"name": "中信建投", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "中国银河证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "国信证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "方正证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "兴业证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "长江证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "国金证券", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "东方财富证券", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "安信证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "中泰证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "浙商证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "财通证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "东吴证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "国海证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "东北证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "西南证券", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    # 基金 补充
    {"name": "广发基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "兴证全球基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "鹏华基金", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "交银施罗德基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "华安基金", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "国泰基金", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "大成基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "中银基金", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "上投摩根基金", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "诺安基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "前海开源基金", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "东方红资管", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},

    # ========== 保险 ==========
    {"name": "中国平安", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "中国人寿", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "中国人保", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "中国太保", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "新华保险", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "泰康保险", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    # 保险 补充
    {"name": "阳光保险", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "众安保险", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "大家保险", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},
    {"name": "友邦保险", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "大地保险", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FINANCE},

    # ========== 外资金融 ==========
    {"name": "高盛", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "摩根士丹利", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "摩根大通", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "瑞银集团", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "汇丰银行", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "花旗银行", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "渣打银行", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "星展银行", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "德意志银行", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "法国巴黎银行", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "贝莱德", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    # 外资金融 补充
    {"name": "美银证券", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "野村证券", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "巴克莱银行", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FINANCE},
    {"name": "法国兴业银行", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "三菱日联银行", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "三井住友银行", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FINANCE},
    {"name": "凯雷投资", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "KKR", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "红杉资本", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},
    {"name": "高瓴资本", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FINANCE},

    # ========== 咨询 ==========
    {"name": "麦肯锡", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_CONSULTING},
    {"name": "波士顿咨询", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_CONSULTING},
    {"name": "贝恩咨询", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_CONSULTING},
    {"name": "罗兰贝格", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_CONSULTING},
    {"name": "科尔尼", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_CONSULTING},
    {"name": "埃森哲", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_CONSULTING},
    {"name": "德勤", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_ACCOUNTING},
    {"name": "普华永道", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_ACCOUNTING},
    {"name": "安永", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_ACCOUNTING},
    {"name": "毕马威", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_ACCOUNTING},
    {"name": "立信会计师事务所", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_ACCOUNTING},
    {"name": "天健会计师事务所", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_ACCOUNTING},
    {"name": "致同", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_ACCOUNTING},
    # 咨询 补充
    {"name": "奥纬咨询", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_CONSULTING},
    {"name": "艾意凯咨询", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_CONSULTING},
    {"name": "理特咨询", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_CONSULTING},
    {"name": "普华永道思略特", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_CONSULTING},
    {"name": "德勤咨询", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_CONSULTING},
    {"name": "和君咨询", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_CONSULTING},
    {"name": "正略钧策", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_CONSULTING},
    {"name": "北大纵横", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_CONSULTING},
    # 财会 补充
    {"name": "信永中和", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_ACCOUNTING},
    {"name": "大华会计师事务所", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_ACCOUNTING},
    {"name": "天衡会计师事务所", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_ACCOUNTING},

    # ========== 快消 ==========
    {"name": "宝洁", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FMCG},
    {"name": "联合利华", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FMCG},
    {"name": "欧莱雅", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FMCG},
    {"name": "雀巢", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FMCG},
    {"name": "玛氏", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FMCG},
    {"name": "百事可乐", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FMCG},
    {"name": "可口可乐", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FMCG},
    {"name": "强生", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FMCG},
    {"name": "高露洁", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FMCG},
    {"name": "亿滋国际", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FMCG},
    {"name": "达能", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FMCG},
    {"name": "雅诗兰黛", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_FMCG},
    {"name": "资生堂", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FMCG},
    {"name": "蓝月亮", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FMCG},
    {"name": "农夫山泉", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FMCG},
    {"name": "伊利集团", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FMCG},
    {"name": "蒙牛乳业", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FMCG},
    {"name": "康师傅", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "统一企业", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "海天味业", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FMCG},
    {"name": "元气森林", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FMCG},
    # 快消 补充
    {"name": "喜茶", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FMCG},
    {"name": "蜜雪冰城", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FMCG},
    {"name": "瑞幸咖啡", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FMCG},
    {"name": "星巴克", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_FMCG},
    {"name": "奈雪的茶", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FMCG},
    {"name": "茶百道", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "三只松鼠", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FMCG},
    {"name": "良品铺子", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FMCG},
    {"name": "洽洽食品", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "卫龙", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "达利集团", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "王老吉", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "加多宝", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "盼盼食品", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "立白集团", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "纳爱斯", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "上海家化", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FMCG},
    {"name": "珀莱雅", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_FMCG},
    {"name": "丸美股份", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "自然堂", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "韩束", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "维达国际", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "恒安国际", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_FMCG},
    {"name": "泡泡玛特", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_RETAIL},

    # ========== 汽车 ==========
    {"name": "比亚迪", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_AUTO},
    {"name": "宁德时代", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_AUTO},
    {"name": "蔚来汽车", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_AUTO},
    {"name": "小鹏汽车", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_AUTO},
    {"name": "理想汽车", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_AUTO},
    {"name": "吉利汽车", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "长城汽车", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "长安汽车", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "上汽集团", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "一汽集团", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "广汽集团", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "特斯拉", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_AUTO},
    {"name": "大众汽车", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_AUTO},
    {"name": "宝马", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_AUTO},
    {"name": "奔驰", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_AUTO},
    {"name": "通用汽车", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "丰田汽车", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    # 汽车 补充
    {"name": "零跑汽车", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "哪吒汽车", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_AUTO},
    {"name": "赛力斯", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_AUTO},
    {"name": "极氪", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_AUTO},
    {"name": "智己汽车", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "阿维塔", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "岚图汽车", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_AUTO},
    {"name": "北汽集团", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "东风汽车", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "奇瑞汽车", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "江淮汽车", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_AUTO},
    {"name": "博世", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_AUTO},
    {"name": "大陆集团", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "采埃孚", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "麦格纳", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},
    {"name": "佛吉亚", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_AUTO},
    {"name": "地平线", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_AUTO},
    {"name": "黑芝麻智能", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_AUTO},

    # ========== 能源/电力 ==========
    {"name": "国家电网", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_ENERGY},
    {"name": "南方电网", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_ENERGY},
    {"name": "中石油", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_ENERGY},
    {"name": "中石化", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_ENERGY},
    {"name": "中海油", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_ENERGY},
    {"name": "国家能源集团", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_ENERGY},
    {"name": "中国电建", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_ENERGY},
    {"name": "中国能建", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_ENERGY},
    {"name": "中国中车", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "中国建筑", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_REALESTATE},
    {"name": "中国中铁", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "中国铁建", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "中国交建", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    # 能源/电力 补充
    {"name": "中国核电", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_ENERGY},
    {"name": "中国广核", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_ENERGY},
    {"name": "华能集团", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_ENERGY},
    {"name": "大唐集团", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_ENERGY},
    {"name": "华电集团", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_ENERGY},
    {"name": "国家电投", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_ENERGY},
    {"name": "三峡集团", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_ENERGY},
    {"name": "隆基绿能", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_ENERGY},
    {"name": "通威股份", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_ENERGY},
    {"name": "阳光电源", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_ENERGY},
    {"name": "晶科能源", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_ENERGY},
    {"name": "天合光能", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_ENERGY},
    {"name": "晶澳科技", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_ENERGY},
    {"name": "中国化学", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},

    # ========== 制造/家电 ==========
    {"name": "美的集团", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MANUFACTURING},
    {"name": "格力电器", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "海尔智家", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "TCL科技", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "海信集团", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "京东方", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},

    # ========== 半导体 ==========
    {"name": "中芯国际", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "长江存储", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "紫光集团", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "华虹半导体", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "韦尔股份", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "北方华创", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "中微公司", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "澜起科技", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "卓胜微", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},
    # 半导体 补充
    {"name": "长鑫存储", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "寒武纪", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "海光信息", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "龙芯中科", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "兆易创新", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "圣邦股份", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "华润微", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "士兰微", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "扬杰科技", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "闻泰科技", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "联发科", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "台积电", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_SEMICONDUCTOR},
    {"name": "汇川技术", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "工业富联", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "立讯精密", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    # 制造/家电 补充
    {"name": "石头科技", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "科沃斯", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "追觅科技", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "云鲸智能", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_MANUFACTURING},
    {"name": "三一重工", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "中联重科", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "徐工机械", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "潍柴动力", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "中集集团", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "振华重工", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_MANUFACTURING},
    {"name": "福耀玻璃", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "万华化学", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MANUFACTURING},
    {"name": "恒力石化", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MANUFACTURING},
    {"name": "荣盛石化", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_MANUFACTURING},
    {"name": "海螺水泥", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_MANUFACTURING},
    {"name": "中国巨石", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_MANUFACTURING},

    # ========== 通信 ==========
    {"name": "中国移动", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_TELECOM},
    {"name": "中国联通", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_TELECOM},
    {"name": "中国电信", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_TELECOM},
    {"name": "中兴通讯", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_TELECOM},
    {"name": "烽火通信", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_TELECOM},
    # 通信 补充
    {"name": "中国铁塔", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_TELECOM},
    {"name": "星网锐捷", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_TELECOM},
    {"name": "锐捷网络", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_TELECOM},

    # ========== 医药 ==========
    {"name": "恒瑞医药", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "药明康德", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "迈瑞医疗", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "复星医药", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MEDICAL},
    {"name": "石药集团", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MEDICAL},
    {"name": "正大天晴", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MEDICAL},
    {"name": "扬子江药业", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MEDICAL},
    {"name": "辉瑞", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_MEDICAL},
    {"name": "罗氏", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_MEDICAL},
    {"name": "诺华", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "默沙东", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "阿斯利康", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "赛诺菲", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MEDICAL},
    # 医药 补充
    {"name": "百济神州", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "信达生物", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "君实生物", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MEDICAL},
    {"name": "康希诺", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "智飞生物", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "长春高新", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "片仔癀", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MEDICAL},
    {"name": "云南白药", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MEDICAL},
    {"name": "同仁堂", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_MEDICAL},
    {"name": "华东医药", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MEDICAL},
    {"name": "人福医药", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_MEDICAL},
    {"name": "科伦药业", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MEDICAL},
    {"name": "华海药业", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_MEDICAL},
    {"name": "翰森制药", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MEDICAL},
    {"name": "再鼎医药", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MEDICAL},
    {"name": "凯莱英", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "泰格医药", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "药明生物", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "康龙化成", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MEDICAL},
    {"name": "拜耳", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "葛兰素史克", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "礼来", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_MEDICAL},
    {"name": "艾伯维", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "百时美施贵宝", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "武田制药", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_MEDICAL},
    {"name": "勃林格殷格翰", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_MEDICAL},

    # ========== 地产 ==========
    {"name": "万科地产", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_REALESTATE},
    {"name": "保利发展", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_REALESTATE},
    {"name": "中海地产", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_REALESTATE},
    {"name": "华润置地", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_REALESTATE},
    {"name": "招商蛇口", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_REALESTATE},
    {"name": "龙湖集团", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_REALESTATE},
    # 地产 补充
    {"name": "碧桂园", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_REALESTATE},
    {"name": "融创中国", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_REALESTATE},
    {"name": "金地集团", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_REALESTATE},
    {"name": "旭辉控股", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_REALESTATE},
    {"name": "绿城中国", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_REALESTATE},
    {"name": "滨江集团", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_REALESTATE},
    {"name": "华发股份", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_REALESTATE},
    {"name": "建发股份", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_REALESTATE},

    # ========== 出海/跨境 ==========
    {"name": "SHEIN", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_OVERSEAS},
    {"name": "安克创新", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGH, "industry": INDUSTRY_OVERSEAS},
    {"name": "傲基科技", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_OVERSEAS},
    {"name": "赛维时代", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_OVERSEAS},
    {"name": "吉宏股份", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_OVERSEAS},
    {"name": "Temu", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_HIGHEST, "industry": INDUSTRY_OVERSEAS},

    # ========== 物流 ==========
    {"name": "顺丰速运", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_LOGISTICS},
    {"name": "京东物流", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_LOGISTICS},
    {"name": "中通快递", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_LOGISTICS},
    {"name": "德邦快递", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_LOGISTICS},
    {"name": "菜鸟物流", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_LOGISTICS},
    # 物流 补充
    {"name": "圆通速递", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_LOGISTICS},
    {"name": "申通快递", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_LOGISTICS},
    {"name": "韵达股份", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_LOGISTICS},
    {"name": "极兔速递", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_LOGISTICS},
    {"name": "中外运", "type": COMPANY_TYPE_SOE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_LOGISTICS},

    # ========== 零售 ==========
    {"name": "沃尔玛", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_RETAIL},
    {"name": "永辉超市", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_RETAIL},
    {"name": "盒马鲜生", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_RETAIL},
    # 零售 补充
    {"name": "Costco", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_RETAIL},
    {"name": "麦德龙", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_RETAIL},
    {"name": "大润发", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_RETAIL},
    {"name": "屈臣氏", "type": COMPANY_TYPE_FOREIGN, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_RETAIL},
    {"name": "名创优品", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_RETAIL},
    {"name": "海底捞", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_RETAIL},
    {"name": "九毛九", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_RETAIL},
    {"name": "呷哺呷哺", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_RETAIL},

    # ========== 教育 ==========
    {"name": "新东方", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_EDUCATION},
    {"name": "好未来", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_EDUCATION},
    {"name": "中公教育", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_EDUCATION},
    # 教育 补充
    {"name": "猿辅导", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_EDUCATION},
    {"name": "作业帮", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_EDUCATION},
    {"name": "高途教育", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_EDUCATION},
    {"name": "网易有道", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_MEDIUM, "industry": INDUSTRY_EDUCATION},
    {"name": "粉笔教育", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_EDUCATION},
    {"name": "华住集团", "type": COMPANY_TYPE_PRIVATE, "difficulty": DIFFICULTY_LOW, "industry": INDUSTRY_RETAIL},
]

# 行业列表(用于前端选择)
INDUSTRY_LIST = [
    INDUSTRY_INTERNET, INDUSTRY_FINANCE, INDUSTRY_FMCG, INDUSTRY_CONSULTING,
    INDUSTRY_MANUFACTURING, INDUSTRY_ENERGY, INDUSTRY_TELECOM, INDUSTRY_AUTO,
    INDUSTRY_MEDICAL, INDUSTRY_REALESTATE, INDUSTRY_OVERSEAS, INDUSTRY_LOGISTICS,
    INDUSTRY_EDUCATION, INDUSTRY_SEMICONDUCTOR, INDUSTRY_GAME, INDUSTRY_ACCOUNTING,
    INDUSTRY_RETAIL,
]

# 公司类型列表
COMPANY_TYPE_LIST = [COMPANY_TYPE_SOE, COMPANY_TYPE_PRIVATE, COMPANY_TYPE_FOREIGN]

# 难度列表
DIFFICULTY_LIST = [DIFFICULTY_HIGHEST, DIFFICULTY_HIGH, DIFFICULTY_MEDIUM, DIFFICULTY_LOW]

# === 公司来源字段补充 ===
# 给每家公司补充: career_domain(官网域名) / wechat_account(公众号) / 历史公告 / has_2027
# career_domain 从 config.COMPANY_CAREER_SITES / FOREIGN_CAREER_SITES 自动匹配
try:
    from config import settings as _settings
    _domain_map = {}
    for cs in _settings.COMPANY_CAREER_SITES:
        _domain_map[cs["name"]] = cs.get("campus_domain") or cs["domain"]
    for fs in _settings.FOREIGN_CAREER_SITES:
        _domain_map[fs["name"]] = fs["domain"]
except Exception:
    _domain_map = {}

for _c in CAMPUS_COMPANIES:
    _name = _c["name"]
    _c.setdefault("career_domain", _domain_map.get(_name, ""))
    _c.setdefault("wechat_account", "")          # 官方招聘公众号名(后续采集填充)
    _c.setdefault("last_announcement_url", "")   # 历史公告链接(参考用)
    _c.setdefault("last_announcement_date", "")  # 历史公告日期(参考今年发布时间)
    _c.setdefault("has_2027_announcement", False)  # 是否已发2027届公告


def get_companies_by_filters(
    company_types: list = None,
    difficulties: list = None,
    industries: list = None,
) -> list:
    """按条件筛选校招企业列表"""
    result = CAMPUS_COMPANIES
    if company_types:
        result = [c for c in result if c["type"] in company_types]
    if difficulties:
        result = [c for c in result if c["difficulty"] in difficulties]
    if industries:
        result = [c for c in result if c["industry"] in industries]
    return result


def get_company_names() -> list:
    """返回所有企业名称列表"""
    return [c["name"] for c in CAMPUS_COMPANIES]
