"""
多维表格字段定义 — 岗位数据库 schema。
集中管理,建表和写记录都引用同一套定义,避免不一致。
"""
from typing import List, Dict, Any

# 岗位数据库表字段(主表:在招岗位)
JOB_FIELDS: List[Dict[str, Any]] = [
    {"name": "岗位标题", "type": 1},   # text
    {"name": "公司", "type": 1},
    {"name": "部门", "type": 1},
    {"name": "地点", "type": 1},
    {"name": "薪资范围", "type": 1},
    {"name": "经验要求", "type": 1},
    {"name": "学历要求", "type": 1},
    {"name": "JD摘要", "type": 1},
    {"name": "JD链接", "type": 15},  # URL(超链接)
    {"name": "抓取日期", "type": 5, "style": {"date_formatter": "yyyy-MM-dd"}},  # datetime
    {"name": "发布时间", "type": 1},
    {"name": "投递截止日期", "type": 5, "style": {"date_formatter": "yyyy-MM-dd"}},  # 校招截止提醒
    {"name": "岗位类别", "type": 1},
    {"name": "平台层级", "type": 1},
    {"name": "相关性评分", "type": 2, "style": {"formatter": "0"}},  # number, 整数
    {"name": "难度评分", "type": 2, "style": {"formatter": "0"}},
    {"name": "综合推荐度", "type": 3, "options": [
        {"name": "优先申请"}, {"name": "可申请"}, {"name": "观望"}, {"name": "跳过"}]},
    {"name": "简评", "type": 1},
    {"name": "申请建议", "type": 1},
    {"name": "申请状态", "type": 3, "options": [
        {"name": "未投递"}, {"name": "已投递"}, {"name": "面试中"}, {"name": "Offer"}, {"name": "拒绝"}]},
    {"name": "投递日期", "type": 5, "style": {"date_formatter": "yyyy-MM-dd"}},  # 投递跟踪
    {"name": "去重hash", "type": 1},
    {"name": "应届窗口", "type": 3, "options": [{"name": "是"}, {"name": "否"}]},
    {"name": "是否在招", "type": 3, "options": [{"name": "是"}, {"name": "否"}]},
]

# 已关闭岗位表(多一个关闭日期)
CLOSED_JOB_FIELDS: List[Dict[str, Any]] = JOB_FIELDS + [
    {"name": "关闭日期", "type": 5, "style": {"date_formatter": "yyyy-MM-dd"}},
]
