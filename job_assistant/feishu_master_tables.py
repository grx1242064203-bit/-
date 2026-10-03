"""
飞书总表服务 — 把 companies 和 positions 总库导出到飞书多维表格,供用户直接查看。

设计原则(第一性原理):
1. 一张多维表格包含「27届秋招启动公司汇总」+「27届校招岗位汇总」两个子表
2. 设置为「互联网获得链接可查看」— 用户无需飞书账号,浏览器打开即看
3. 分类/类型类字段使用单选(带颜色标签),可筛选,与数据源表格样式一致
4. 增量写入:先查重再插入,避免重复
5. 批量写入(每批 500 条),控制 API 调用频率
"""
import json
import logging
import os
import time
from typing import Dict, List

import job_db
from feishu_client import FeishuClient

logger = logging.getLogger(__name__)

# 加载映射配置(行业/公司类型/招聘类型的选项)
_MAPPINGS_PATH = os.path.join(os.path.dirname(__file__), "mappings.json")
with open(_MAPPINGS_PATH, "r", encoding="utf-8") as _f:
    _MAPPINGS = json.load(_f)

# 行业选项(带颜色)
INDUSTRY_OPTIONS = [{"name": c["name"]} for c in _MAPPINGS["industry_categories"]]
# 公司类型选项
COMPANY_TYPE_OPTIONS = [{"name": c["name"]} for c in _MAPPINGS["company_type_categories"]]
# 招聘类型选项
RECRUIT_TYPE_OPTIONS = [{"name": t} for t in _MAPPINGS["recruit_types"]]
# 学历要求选项(汇总源表与岗位表常见值)
EDUCATION_OPTIONS = [
    {"name": "专科起"}, {"name": "大专起"}, {"name": "本科起"},
    {"name": "硕士起"}, {"name": "博士起"}, {"name": "博士"},
    {"name": "本科"}, {"name": "硕士"}, {"name": "不限"}, {"name": "详见公告"},
]
# 岗位分类选项
JOB_CATEGORY_OPTIONS = [
    {"name": "产品"}, {"name": "研发"}, {"name": "设计"}, {"name": "运营"},
    {"name": "职能"}, {"name": "销售"}, {"name": "金融"}, {"name": "管培"},
    {"name": "其他"},
]
# 专业大类选项
MAJOR_CATEGORY_OPTIONS = [
    {"name": "工科"}, {"name": "理科"}, {"name": "文科"}, {"name": "商科"},
    {"name": "医科"}, {"name": "农学"}, {"name": "艺术"}, {"name": "不限"}, {"name": "其他"},
]
# 难度选项
DIFFICULTY_OPTIONS = [
    {"name": "简单"}, {"name": "中等难度"}, {"name": "较为激烈"}, {"name": "困难"},
]
# 是否管培选项
YESNO_OPTIONS = [{"name": "是"}, {"name": "否"}]

# 表名
TABLE_COMPANIES = "27届秋招启动公司汇总"
TABLE_POSITIONS = "27届校招岗位汇总"
TABLE_VL_FAILURES = "VL识别失败记录"

# VL 失败记录表字段
VL_FAILURE_FIELDS = [
    {"name": "公告ID", "type": 2},  # 数字,增量同步唯一键
    {"name": "公司名称", "type": 1},
    {"name": "公告标题", "type": 1},
    {"name": "网申更新", "type": 5},
    {"name": "VL错误信息", "type": 1},
    {"name": "图片数量", "type": 2},
    {"name": "正文长度", "type": 2},
    {"name": "公告链接", "type": 15},
    {"name": "网申链接", "type": 15},
]

VL_FAILURE_COL_WIDTHS = {
    "公告ID": 70, "公司名称": 120, "公告标题": 200, "网申更新": 90, "VL错误信息": 300,
    "图片数量": 70, "正文长度": 80, "公告链接": 120, "网申链接": 120,
}

# 公司总表字段
# 字段顺序: 公司名称 → 网申更新 → 行业 → 公司类型 → 招聘类型 → 招聘对象 →
#           招聘地点 → 学历要求 → 截止日期 → 招聘岗位 → 网申链接 → 公告链接
# 注: 招聘地点为多选(与源表一致), 截止日期为文本(源表含"招满即止"等非日期值)
COMPANY_FIELDS = [
    {"name": "公司名称", "type": 1},
    {"name": "网申更新", "type": 5},
    {"name": "行业", "type": 3, "options": INDUSTRY_OPTIONS},
    {"name": "公司类型", "type": 3, "options": COMPANY_TYPE_OPTIONS},
    {"name": "招聘类型", "type": 3, "options": RECRUIT_TYPE_OPTIONS},
    {"name": "招聘对象", "type": 3},
    {"name": "招聘地点", "type": 4},
    {"name": "学历要求", "type": 3, "options": EDUCATION_OPTIONS},
    {"name": "截止日期", "type": 1},
    {"name": "招聘岗位", "type": 1},
    {"name": "网申链接", "type": 15},
    {"name": "公告链接", "type": 15},
]

# 公司表列宽(像素,与源表接近,偏窄)
COMPANY_COL_WIDTHS = {
    "公司名称": 120, "网申更新": 90, "行业": 100, "公司类型": 80,
    "招聘类型": 80, "招聘对象": 80, "招聘地点": 110, "学历要求": 70,
    "截止日期": 80, "招聘岗位": 150, "网申链接": 100, "公告链接": 100,
}

# 岗位表列宽(偏窄,与源表一致)
POSITION_COL_WIDTHS = {
    "岗位标题": 160, "网申更新": 90, "公司名称": 110, "公司行业": 100,
    "公司类型": 80, "岗位分类": 70, "岗位子类": 90,
    "最低学历": 70, "专业要求": 120, "专业大类": 70, "城市": 90,
    "硬技能": 120, "关键词": 120, "是否管培": 60, "难度": 80,
    "JD摘要": 150, "投递链接": 100, "公告链接": 100, "去重ID": 80,
}

# 岗位总表字段
# 字段顺序: 岗位标题 → 网申更新 → 公司名称 → 公司行业 → 公司类型 →
#           岗位分类 → 岗位子类 → 最低学历 → 专业要求 → 专业大类 → 城市 →
#           硬技能 → 关键词 → 是否管培 → 难度 → JD摘要 → 投递链接 → 公告链接
POSITION_FIELDS = [
    {"name": "岗位标题", "type": 1},
    {"name": "网申更新", "type": 5},
    {"name": "公司名称", "type": 1},
    {"name": "公司行业", "type": 3, "options": INDUSTRY_OPTIONS},
    {"name": "公司类型", "type": 3, "options": COMPANY_TYPE_OPTIONS},
    {"name": "岗位分类", "type": 3, "options": JOB_CATEGORY_OPTIONS},
    {"name": "岗位子类", "type": 1},
    {"name": "最低学历", "type": 3, "options": EDUCATION_OPTIONS},
    {"name": "专业要求", "type": 1},
    {"name": "专业大类", "type": 3, "options": MAJOR_CATEGORY_OPTIONS},
    {"name": "城市", "type": 1},
    {"name": "硬技能", "type": 1},
    {"name": "关键词", "type": 1},
    {"name": "是否管培", "type": 3, "options": YESNO_OPTIONS},
    {"name": "难度", "type": 3, "options": DIFFICULTY_OPTIONS},
    {"name": "JD摘要", "type": 1},
    {"name": "投递链接", "type": 15},
    {"name": "公告链接", "type": 15},
    # 去重ID: 增量同步唯一键(dedup_hash),用户侧仅作技术字段展示
    {"name": "去重ID", "type": 1},
]


class FeishuMasterTableService:
    """飞书总表(公司+岗位)导出服务。"""

    def __init__(self, client: FeishuClient = None):
        self.client = client or FeishuClient()

    def create_master_bitable(self, name: str = "27届校招汇总表") -> Dict:
        """创建总表多维表格,返回 app_token 和子表 ID。

        表结构(面向用户,产品化):
        1. 📖 使用说明 — 产品介绍 + 使用指引(首屏可见)
        2. 27届秋招启动公司汇总 — 公司维度
        3. 岗位-{专业大类} — 岗位维度(export_positions 动态创建)
        """
        app_token = self.client.create_bitable(name)
        logger.info(f"创建总表多维表格: {name} -> {app_token}")

        # 1. 使用说明表(置于最前,作为产品入口)
        guide_table_id = self.client.create_table(app_token, "📖 使用说明")
        self._setup_guide_table(app_token, guide_table_id)

        # 2. 公司总表
        company_table_id = self.client.create_table(app_token, TABLE_COMPANIES)
        self._create_fields(app_token, company_table_id, COMPANY_FIELDS, "公司名称")
        self._setup_view(app_token, company_table_id, COMPANY_COL_WIDTHS, "网申更新")

        # 岗位分表由 export_positions 按专业大类动态创建,此处不预建

        # 设置互联网可查看
        self.client.set_public_share(app_token, doc_type="bitable")
        share_url = self.client.get_share_url(app_token, doc_type="bitable")
        logger.info(f"总表分享链接: {share_url}")

        return {
            "app_token": app_token,
            "guide_table_id": guide_table_id,
            "company_table_id": company_table_id,
            "position_table_id": "",  # 岗位分表动态创建,此 ID 仅作同步开关
            "vl_failure_table_id": "",  # VL 失败表已移除
            "share_url": share_url,
        }

    def _setup_guide_table(self, app_token: str, table_id: str):
        """设置使用说明表:创建字段并写入产品指引内容。

        口吻参考源表《27届实习/秋招/春招表格使用指南》:
        直接对学生说话、用真实提问开头、给可操作的筛选技巧、
        关键提醒单独成段、分编号小节、大量举例。
        """
        guide_fields = [
            {"name": "板块", "type": 3, "property": {"options": [
                {"name": "开篇"}, {"name": "怎么找岗位"}, {"name": "字段说明"},
                {"name": "更新机制"}, {"name": "投递提醒"},
            ]}},
            {"name": "标题", "type": 1},
            {"name": "内容", "type": 1},
        ]
        self._create_fields(app_token, table_id, guide_fields, "标题")

        rows = [
            {"板块": "开篇", "标题": "先别只盯“专业对口”",
             "内容": "很多同学一打开表格，第一反应是搜自己的专业：\n"
                     "「数学专业能投什么？」\n"
                     "「计算机是不是只能搜计算机岗？」\n"
                     "「JD 没写我的专业，是不是就不能投？」\n\n"
                     "其实这样很容易漏掉机会。\n"
                     "企业校招大多数时候不是在找「某个专业的人」，"
                     "而是在找「能做某类岗位的人」。\n\n"
                     "所以这份表格更建议按 岗位分类、城市、学历、"
                     "截止时间 来看，而不是只按专业名搜索。"},
            {"板块": "开篇", "标题": "这份表格适合谁看？",
             "内容": "如果你有下面这些情况，可以先从这份表格开始筛选：\n"
                        "• 不确定自己能投哪些岗位\n"
                        "• 想看哪些公司正在秋招\n"
                        "• 想按城市、按专业大类找岗位\n"
                        "• 想找管培生、不限专业的岗位\n"
                        "• 想看岗位、截止时间、工作地点、投递入口\n"
                        "• 不想再被「专业对口」几个字卡住"},
            {"板块": "怎么找岗位", "标题": "01 先按专业大类切入",
             "内容": "左侧「岗位-工科 / 商科 / 文科 / 理科 / 医科 / 艺术 / 农学 / 不限」"
                        "是按岗位适配的专业大类拆分的。\n\n"
                        "不知道自己专业属于哪类？可以这样判断：\n"
                        "• 工科：机械、电子、计算机、自动化、土木、化工等\n"
                        "• 商科：金融、会计、市场、管理、经济等\n"
                        "• 文科：语言、新闻、法学、教育、历史等\n"
                        "• 不确定时，先看「岗位-不限」，很多岗位对专业没严格限制"},
            {"板块": "怎么找岗位", "标题": "02 用「岗位分类」缩小范围",
             "内容": "确定大类后，用表头筛选器选「岗位分类」。\n"
                        "比如工科同学可以看：开发、算法、硬件电子、芯片半导体、制造与质量。\n"
                        "商科同学可以看：金融、商业(销售与市场)、职能、运营与供应链。\n\n"
                        "想找不限专业的，可以看：管培生、产品、运营、人力资源。\n\n"
                        "搜岗位时尽量搜岗位关键词（开发、产品、运营、设计…），"
                        "不要只搜专业名称。"},
            {"板块": "怎么找岗位", "标题": "03 城市怎么筛？用「包含」",
             "内容": "城市筛选最容易漏机会。\n\n"
                        "不要只筛：城市 = 北京\n"
                        "因为很多公司会写「北京/上海/广州/深圳」或「全国各地」。\n\n"
                        "筛城市时，建议用「包含」而不是「等于」，"
                        "并且把「全国各地」一起看。\n\n"
                        "举例：\n"
                        "• 想找北京岗位：城市包含「北京」+「全国各地」\n"
                        "• 想找南京岗位：城市包含「南京」+「江苏」+「全国各地」"},
            {"板块": "怎么找岗位", "标题": "04 公司总表怎么看",
             "内容": "「27届秋招启动公司汇总」是按公司维度汇总的。\n\n"
                        "适合这样用：\n"
                        "• 按「公司行业」筛你想去的行业（互联网/金融/制造…）\n"
                        "• 按「公司类型」筛央企/国企/外企/民企\n"
                        "• 「招聘岗位」列看这家公司最新招哪些方向\n"
                        "• 点「网申链接」直接进官方投递页\n\n"
                        "不确定能投什么时，先扫一遍公司总表，"
                        "看到感兴趣的公司再点进去看具体岗位。"},
            {"板块": "字段说明", "标题": "岗位表字段怎么看",
             "内容": "• 岗位标题：岗位名-公司名，一眼看清是什么岗\n"
                        "• 网申更新：这条信息最近更新的日期，越近越新鲜\n"
                        "• 公司行业 / 公司类型：行业和企业性质\n"
                        "• 岗位分类 / 岗位子类：岗位所属类别，可筛选\n"
                        "• 最低学历：岗位要求的学历门槛\n"
                        "• 专业大类：这个岗位适配的专业方向\n"
                        "• 城市：工作地点（一个岗位可能有多个城市）\n"
                        "• 硬技能 / 关键词：岗位技能标签，快速判断匹配度\n"
                        "• 是否管培：是不是管培生项目\n"
                        "• 投递链接：官方网申入口，点进去直接投\n"
                        "• 公告链接：原始招聘公告，看详细 JD"},
            {"板块": "字段说明", "标题": "公司表字段怎么看",
             "内容": "• 公司名称 / 行业 / 公司类型：基础信息\n"
                        "• 网申更新：最新公告更新日期\n"
                        "• 招聘类型 / 招聘对象：校招类型和面向届数\n"
                        "• 招聘地点：工作城市（多选）\n"
                        "• 学历要求：最低学历门槛\n"
                        "• 截止日期：网申截止（写「招满即止」表示没明确截止，越早投越好）\n"
                        "• 招聘岗位：最新公告的岗位方向\n"
                        "• 网申链接 / 公告链接：官方入口"},
            {"板块": "更新机制", "标题": "数据从哪来、多久更一次",
             "内容": "数据来自公开招聘公告，每日凌晨自动抓取、结构化解析后写入本表。\n\n"
                        "岗位按「公司 + 岗位名 + 工作城市」去重，同一个岗位只保留一条。\n\n"
                        "每日更新一次，新增当日发布的秋招岗位和公司。历史数据持续保留。"},
            {"板块": "投递提醒", "标题": "投递前一定要再确认这些",
             "内容": "表格适合快速筛选，但最终投递前，"
                        "点进「投递链接」或「公告链接」看清楚：\n"
                        "• 具体岗位要求和 JD\n"
                        "• 网申截止时间\n"
                        "• 是否有测评/笔试\n"
                        "• 投递城市是否可选\n"
                        "• 简历投递方式\n"
                        "• 岗位是否招满即止\n\n"
                        "有些公司流程很快，入口开着开着就关了。"
                        "不要一直等「准备好了再投」。"},
            {"板块": "投递提醒", "标题": "最后提醒",
             "内容": "投递岗位不是只比谁准备得最完美，"
                        "也很看谁开始得更早、投得更持续、愿意多试几个方向。\n\n"
                        "如果你现在还不知道自己能投什么，先别卡在专业名称里。"
                        "可以先从岗位关键词开始看：\n"
                        "运营、产品、市场、销售、人力、管培生、开发、研发、测试、设计、项目、供应链……\n\n"
                        "先看到真实岗位，再判断自己能不能匹配。"
                        "投起来之后，方向会越来越清楚。"},
        ]
        records = [
            {"板块": r["板块"], "标题": r["标题"], "内容": r["内容"]}
            for r in rows
        ]
        self.client.batch_create_records(app_token, table_id, records)
        logger.info(f"使用说明表写入 {len(records)} 条指引")

    def _create_fields(self, app_token: str, table_id: str,
                       fields: List[Dict], primary_field: str):
        """创建字段(跳过已存在的)。"""
        existing_fields = self.client.list_fields(app_token, table_id)
        existing = {f["field_name"] for f in existing_fields}
        # 主字段重命名(飞书建表后第一个字段默认叫"多行文本",需重命名)
        if primary_field not in existing and existing_fields:
            first = existing_fields[0]
            self.client.update_field(app_token, table_id, first["field_id"],
                                     field_name=primary_field, type=first["type"])
            existing.add(primary_field)
            existing_fields = self.client.list_fields(app_token, table_id)
        for f in fields:  # 跳过主字段(已重命名),其余按需创建
            if f["name"] == primary_field or f["name"] in existing:
                continue
            kwargs = {}
            if "style" in f:
                kwargs["style"] = f["style"]
            if "options" in f:
                kwargs["property"] = {"options": f["options"]}
            self.client.create_field(app_token, table_id, f["name"], f["type"], **kwargs)
            time.sleep(0.3)

    def _setup_view(self, app_token: str, table_id: str,
                    col_widths: Dict[str, int], sort_field: str = "网申更新"):
        """设置默认视图:列宽 + 按网申更新降序排序。"""
        views = self.client.list_views(app_token, table_id)
        if not views:
            logger.warning(f"未找到视图,跳过视图设置: table={table_id}")
            return
        view_id = views[0].get("view_id", "")
        if not view_id:
            return

        # 字段名 → field_id 映射
        fields = self.client.list_fields(app_token, table_id)
        name_to_id = {f["field_name"]: f["field_id"] for f in fields}

        # 构建列宽配置
        column_width = {}
        for name, width in col_widths.items():
            fid = name_to_id.get(name)
            if fid:
                column_width[fid] = width

        # 构建排序配置(按网申更新降序)
        # 飞书 API 要求 sort 格式为 {"sort_conditions": [{"field_id":..., "desc":...}]}
        sort_fid = name_to_id.get(sort_field)
        sort_conf = None
        if sort_fid:
            sort_conf = {"sort_conditions": [{"field_id": sort_fid, "desc": True}]}

        property_ = {}
        if column_width:
            property_["column_width"] = column_width
        if sort_conf:
            property_["sort"] = sort_conf

        if property_:
            ok = self.client.update_view(app_token, table_id, view_id, property_)
            if ok:
                logger.info(f"视图设置完成(列宽+排序): table={table_id}")
            else:
                logger.warning(f"视图设置失败: table={table_id}")

    def _build_existing_map(self, app_token: str, table_id: str,
                            key_field: str) -> tuple:
        """拉取表中所有记录,构建 key_field -> {"record_id":..., "fields": 归一化字段} 的映射。

        用于增量 upsert:把飞书侧已有记录按唯一键索引,便于判断新增/更新。
        fields 经过 normalize_fields 归一化(select→字符串/list, url→{text,link})。

        Returns: (existing_map, total_record_count)
        total_record_count 用于检测"有记录但缺少 key 字段"的情况(首次迁移),
        此时需要清表重写一次以补全 key 字段。
        """
        existing: Dict[str, Dict] = {}
        records = self.client.list_all_records(app_token, table_id)
        for r in records:
            rid = r.get("record_id", "")
            fields = r.get("fields", {}) or {}
            key_val = fields.get(key_field)
            # key_field 可能是 select(返回 [{"name":...}])、文本、或 URL({"text","link"})
            if isinstance(key_val, list):
                key_val = key_val[0].get("name", "") if key_val else ""
            elif isinstance(key_val, dict):
                key_val = key_val.get("link") or key_val.get("text", "")
            if not key_val:
                continue
            existing[str(key_val)] = {
                "record_id": rid,
                "fields": self.client.normalize_fields(fields),
            }
        return existing, len(records)

    @staticmethod
    def _fields_equal(target: Dict, existing_norm: Dict) -> bool:
        """比较目标字段与飞书侧已归一化字段是否相等。

        规则:
        - 缺失键 与 空字符串/空值 视为相等
        - URL 字段只比较 link(不比较 text)
        - 单元素列表 与 字符串 视为相等(飞书 normalize 会把单选数组拍平成字符串)
        - 字符串去首尾空白后比较
        - 其他类型直接比较
        """
        def _canon(v):
            # 单元素列表拍平为字符串,与 normalize_fields 行为对齐
            if isinstance(v, list) and len(v) == 1:
                return v[0]
            return v

        all_keys = set(target.keys()) | set(existing_norm.keys())
        for k in all_keys:
            tv = _canon(target.get(k))
            ev = _canon(existing_norm.get(k))
            # 缺失或空值视为相等
            tv_empty = tv is None or tv == "" or tv == []
            ev_empty = ev is None or ev == "" or ev == []
            if tv_empty and ev_empty:
                continue
            if tv_empty != ev_empty:
                return False
            # URL 字段:只比 link
            if isinstance(tv, dict) and "link" in tv and isinstance(ev, dict) and "link" in ev:
                if tv.get("link") != ev.get("link"):
                    return False
                continue
            # 字符串去空白
            if isinstance(tv, str) and isinstance(ev, str):
                if tv.strip() != ev.strip():
                    return False
                continue
            # 列表比较(忽略顺序差异,如多选地点)
            if isinstance(tv, list) and isinstance(ev, list):
                if sorted(map(str, tv)) != sorted(map(str, ev)):
                    return False
                continue
            if tv != ev:
                return False
        return True

    @staticmethod
    def _url_field(url: str) -> Dict:
        """飞书 URL 字段需要对象格式。"""
        if not url:
            return None
        return {"link": url, "text": url[:50]}

    @staticmethod
    def _date_to_ts(date_str: str) -> int:
        """将 YYYY-MM-DD 字符串转为毫秒时间戳(飞书日期字段需要)。"""
        if not date_str:
            return None
        try:
            # 兼容 YYYY/MM/DD 格式
            date_str = date_str.replace("/", "-")
            t = time.strptime(date_str[:10], "%Y-%m-%d")
            return int(time.mktime(t) * 1000)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _format_grade(min_grade, max_grade) -> str:
        """格式化届数范围。"""
        if not min_grade and not max_grade:
            return ""
        if min_grade == max_grade:
            return f"{min_grade}届"
        return f"{min_grade}-{max_grade}届"

    @staticmethod
    def _split_location(location: str) -> List[str]:
        """将空格分隔的地点字符串拆为多选项数组(与源表多选格式一致)。"""
        if not location:
            return []
        return [c for c in location.replace("、", " ").replace(",", " ").split() if c]

    def export_companies(self, app_token: str, table_id: str, limit: int = 0) -> Dict:
        """增量导出公司总表数据到飞书(按「公司名称」upsert)。

        返回 {"created": N, "updated": M}。

        增量策略:
        1. 拉取飞书侧已有记录,按「公司名称」建索引
        2. 本地不存在的公司 → 新增
        3. 已存在但字段有变化 → 更新
        4. 已存在且无变化 → 跳过
        (不删除飞书侧有但本地没有的公司,避免误删)
        """
        companies = job_db.get_all_companies()
        if limit:
            companies = companies[:limit]

        # 构建目标记录
        records = []
        for c in companies:
            latest_ann = job_db.get_latest_announcement_by_company(c["id"]) or {}
            apply_update = latest_ann.get("apply_update", "")
            record = {
                "公司名称": c["name"],
                "网申更新": self._date_to_ts(apply_update),
                "行业": c.get("industry", ""),
                "公司类型": c.get("company_type", ""),
                "招聘类型": latest_ann.get("recruit_type", ""),
                "招聘对象": latest_ann.get("recruit_target", ""),
                "招聘地点": self._split_location(latest_ann.get("location", "")),
                "学历要求": latest_ann.get("education_req", ""),
                "截止日期": latest_ann.get("deadline", ""),
                "招聘岗位": latest_ann.get("announcement_title", ""),
                "_sort_key": apply_update or "",
            }
            apply_url = self._url_field(c.get("apply_url", ""))
            if apply_url:
                record["网申链接"] = apply_url
            ann_url = self._url_field(latest_ann.get("announcement_url", ""))
            if ann_url:
                record["公告链接"] = ann_url
            records.append(record)

        records.sort(key=lambda r: r.get("_sort_key", "") or "", reverse=True)
        for r in records:
            r.pop("_sort_key", None)

        if not records:
            return {"created": 0, "updated": 0}

        # 拉取飞书侧已有记录
        existing, total = self._build_existing_map(app_token, table_id, "公司名称")
        # 首次迁移兜底:若表中有记录但缺少「公司名称」,清表重写一次
        if total > 0 and len(existing) < total:
            logger.info(f"公司表检测到 {total - len(existing)} 条缺键记录,一次性清表重写")
            self.client.clear_table_records(app_token, table_id)
            existing = {}

        to_create = []
        to_update = []
        for rec in records:
            name = rec["公司名称"]
            if name not in existing:
                to_create.append(rec)
                continue
            old = existing[name]["fields"]
            if not self._fields_equal(rec, old):
                to_update.append({
                    "record_id": existing[name]["record_id"],
                    "fields": rec,
                })

        created = 0
        if to_create:
            ids = self.client.batch_create_records(app_token, table_id, to_create)
            created = len(ids)
        updated = 0
        if to_update:
            updated = self.client.batch_update_records(app_token, table_id, to_update)

        logger.info(
            f"公司总表增量同步: 新增 {created} 条, 更新 {updated} 条, "
            f"跳过 {len(records) - len(to_create) - len(to_update)} 条"
        )
        return {"created": created, "updated": updated}

    def export_positions(self, app_token: str, table_id: str = "", limit: int = 0) -> Dict:
        """增量导出岗位总表数据到飞书(按专业大类拆分子表,按「去重ID」upsert)。

        返回 {"created": N, "updated": M}。

        拆分原因:单表 3.5 万+ 岗位接近飞书 5 万条上限,按「专业大类」拆分后
        每类最多 ~2.2 万条(工科),远低于上限。

        增量策略(每类子表独立执行):
        1. 拉取子表已有记录,按「去重ID」(=dedup_hash)建索引
        2. 本地有、飞书无 → 新增
        3. 本地有、飞书有但字段变化 → 更新
        4. 两边都有且无变化 → 跳过
        (不删除飞书侧有但本地没有的岗位;若岗位大类变更,旧表残留由周度全量兜底)

        表名规则:「岗位-{专业大类}」。table_id 参数保留兼容旧调用,实际不使用。
        """
        positions = job_db.get_all_positions_for_export()
        if limit:
            positions = positions[:limit]
        if not positions:
            return {"created": 0, "updated": 0}

        # 按专业大类分组(空值归入「其他」)
        groups: Dict[str, list] = {}
        for p in positions:
            cat = (p.get("major_category") or "").strip() or "其他"
            groups.setdefault(cat, []).append(p)

        total_created = 0
        total_updated = 0
        for cat, cat_positions in groups.items():
            table_name = f"岗位-{cat}"
            cat_table_id = self.client.get_or_create_table(
                app_token, table_name, POSITION_FIELDS, "岗位标题")
            if not cat_table_id:
                logger.warning(f"无法获取/创建表 {table_name},跳过")
                continue

            # 构建目标记录
            records = []
            for p in cat_positions:
                title = p["position_title"] or "通用校招岗"
                company = p["company_name"] or ""
                display_title = f"{title}-{company}" if company else title
                apply_update = p.get("apply_update", "")
                dedup_hash = p.get("dedup_hash", "")
                record = {
                    "岗位标题": display_title,
                    "网申更新": self._date_to_ts(apply_update),
                    "公司名称": p["company_name"],
                    "公司行业": p.get("industry", ""),
                    "公司类型": p.get("company_type", ""),
                    "岗位分类": p.get("job_category", ""),
                    "岗位子类": p.get("job_subcategory", ""),
                    "最低学历": p.get("min_education", "") or p.get("education_req", ""),
                    "专业要求": p.get("major_required", "") or p.get("major_req", ""),
                    "专业大类": cat,
                    "城市": p.get("city", "") or p.get("location", ""),
                    "硬技能": p.get("hard_skills", ""),
                    "关键词": p.get("keywords", ""),
                    "是否管培": "是" if p.get("is_management_trainee") else "否",
                    "难度": p.get("difficulty", ""),
                    "JD摘要": p.get("jd_summary", ""),
                    "去重ID": dedup_hash,
                    "_sort_key": apply_update or "",
                }
                url = self._url_field(p.get("apply_url", "") or p.get("source_url", ""))
                if url:
                    record["投递链接"] = url
                ann_url = self._url_field(p.get("announcement_url", ""))
                if ann_url:
                    record["公告链接"] = ann_url
                records.append(record)

            # 按网申更新降序排序
            records.sort(key=lambda r: r.get("_sort_key", "") or "", reverse=True)
            for r in records:
                r.pop("_sort_key", None)

            if not records:
                continue

            # 拉取飞书侧已有记录(按去重ID索引)
            existing, total = self._build_existing_map(app_token, cat_table_id, "去重ID")
            # 首次迁移兜底:老记录无「去重ID」字段,清表重写一次补全
            if total > 0 and len(existing) < total:
                logger.info(f"[{table_name}] 检测到 {total - len(existing)} 条缺键记录,一次性清表重写")
                self.client.clear_table_records(app_token, cat_table_id)
                existing = {}

            to_create = []
            to_update = []
            for rec in records:
                hid = rec.get("去重ID")
                if not hid or hid not in existing:
                    to_create.append(rec)
                    continue
                old = existing[hid]["fields"]
                if not self._fields_equal(rec, old):
                    to_update.append({
                        "record_id": existing[hid]["record_id"],
                        "fields": rec,
                    })

            created = 0
            if to_create:
                ids = self.client.batch_create_records(app_token, cat_table_id, to_create)
                created = len(ids)
            updated = 0
            if to_update:
                updated = self.client.batch_update_records(app_token, cat_table_id, to_update)

            total_created += created
            total_updated += updated
            skipped = len(records) - len(to_create) - len(to_update)
            logger.info(
                f"[{table_name}] 增量同步: 新增 {created}, 更新 {updated}, 跳过 {skipped}"
            )

        logger.info(
            f"岗位总表增量同步完成: {len(groups)} 个大类, "
            f"新增 {total_created} 条, 更新 {total_updated} 条"
        )
        return {"created": total_created, "updated": total_updated}

    def export_vl_failures(self, app_token: str, table_id: str) -> Dict:
        """增量导出 VL 识别失败的公告到飞书记录表(按「公告ID」upsert,含删除)。

        返回 {"created": N, "updated": M, "deleted": K}。

        与公司/岗位表不同:VL 失败记录是动态集合(识别失败→重处理成功后会移出),
        因此需要删除飞书侧有但本地已不再失败的记录。
        """
        announcements = job_db.get_vl_failed_announcements()

        records = []
        for ann in announcements:
            img_count = 0
            images_json = ann.get("content_images", "") or ""
            if images_json:
                try:
                    import json as _json
                    imgs = _json.loads(images_json)
                    img_count = len(imgs) if isinstance(imgs, list) else 0
                except Exception:
                    pass

            record = {
                "公告ID": ann.get("id"),
                "公司名称": ann.get("company_name", ""),
                "公告标题": ann.get("announcement_title", ""),
                "网申更新": self._date_to_ts(ann.get("apply_update", "")),
                "VL错误信息": (ann.get("vl_error", "") or "")[:300],
                "图片数量": img_count,
                "正文长度": ann.get("content_len", 0) or 0,
                "_sort_key": ann.get("apply_update", "") or "",
            }
            ann_url = self._url_field(ann.get("announcement_url", ""))
            if ann_url:
                record["公告链接"] = ann_url
            apply_url = self._url_field(ann.get("apply_url", ""))
            if apply_url:
                record["网申链接"] = apply_url
            records.append(record)

        records.sort(key=lambda r: r.get("_sort_key", "") or "", reverse=True)
        for r in records:
            r.pop("_sort_key", None)

        # 拉取飞书侧已有记录(按公告ID索引)
        existing, total = self._build_existing_map(app_token, table_id, "公告ID")
        # 首次迁移兜底:老记录无「公告ID」字段,清表重写一次补全
        if total > 0 and len(existing) < total:
            logger.info(f"VL失败表检测到 {total - len(existing)} 条缺键记录,一次性清表重写")
            self.client.clear_table_records(app_token, table_id)
            existing = {}

        if not records:
            # 本地无失败记录:删除飞书侧全部残留
            if existing:
                deleted = self.client.batch_delete_records(
                    app_token, table_id,
                    [v["record_id"] for v in existing.values()])
                logger.info(f"无 VL 失败记录,清理飞书侧残留 {deleted} 条")
                return {"created": 0, "updated": 0, "deleted": deleted}
            logger.info("无 VL 失败记录,跳过导出")
            return {"created": 0, "updated": 0, "deleted": 0}

        to_create = []
        to_update = []
        target_keys = set()
        for rec in records:
            aid = rec.get("公告ID")
            key = str(aid) if aid is not None else None
            if not key:
                # 无 ID 的极端情况直接新增(不参与去重)
                to_create.append(rec)
                continue
            target_keys.add(key)
            if key not in existing:
                to_create.append(rec)
                continue
            old = existing[key]["fields"]
            if not self._fields_equal(rec, old):
                to_update.append({
                    "record_id": existing[key]["record_id"],
                    "fields": rec,
                })

        # 删除:飞书侧有但本地已不再失败的记录
        to_delete = [v["record_id"] for k, v in existing.items() if k not in target_keys]

        created = updated = deleted = 0
        if to_create:
            ids = self.client.batch_create_records(app_token, table_id, to_create)
            created = len(ids)
        if to_update:
            updated = self.client.batch_update_records(app_token, table_id, to_update)
        if to_delete:
            deleted = self.client.batch_delete_records(app_token, table_id, to_delete)

        logger.info(
            f"VL 失败记录表增量同步: 新增 {created}, 更新 {updated}, 删除 {deleted}"
        )
        return {"created": created, "updated": updated, "deleted": deleted}


def create_and_export_master_table(company_limit: int = 0,
                                   position_limit: int = 0) -> Dict:
    """一键创建总表并导出数据(增量 upsert,新表等价于全量写入)。"""
    service = FeishuMasterTableService()
    result = service.create_master_bitable()
    r_companies = service.export_companies(
        result["app_token"], result["company_table_id"], limit=company_limit)
    # position_table_id 为空字符串时,export_positions 仍会按名称动态建分表
    r_positions = service.export_positions(
        result["app_token"], result["position_table_id"], limit=position_limit)
    result["companies"] = r_companies
    result["positions"] = r_positions
    logger.info(
        f"总表导出完成: 公司 {r_companies}, 岗位 {r_positions}"
    )
    logger.info(f"总表链接: {result['share_url']}")
    return result


def sync_to_existing_master_table() -> Dict:
    """增量同步数据到已存在的飞书总表(upsert,不清表)。

    用于每日管线:把本地 DB 的公司/岗位增量同步到飞书总表。
    表的 app_token 和 table_id 从 config.settings 读取。

    增量策略:按唯一键 upsert(公司名称 / 去重ID),
    不清空表,同步期间用户始终能看到完整数据。

    Returns: {"companies": {...}, "positions": {...}}
    """
    from config import settings
    service = FeishuMasterTableService()
    app_token = settings.MASTER_APP_TOKEN
    company_table_id = settings.MASTER_COMPANY_TABLE_ID
    position_table_id = settings.MASTER_POSITION_TABLE_ID

    if not app_token:
        logger.warning("MASTER_APP_TOKEN 未配置,跳过总表同步")
        return {"companies": {}, "positions": {}}

    result = {"companies": {}, "positions": {}}

    # 1. 增量同步公司总表(按公司名称 upsert)
    if company_table_id:
        try:
            result["companies"] = service.export_companies(app_token, company_table_id)
        except Exception as e:
            logger.error(f"同步公司总表失败: {e}")

    # 2. 增量同步岗位总表(按专业大类拆分子表,按去重ID upsert)
    #    position_table_id 仅用于判断是否开启岗位同步,实际表按名称动态创建
    if position_table_id:
        try:
            result["positions"] = service.export_positions(app_token, position_table_id)
        except Exception as e:
            logger.error(f"同步岗位总表失败: {e}")

    logger.info(
        f"总表增量同步完成: 公司 {result['companies']}, "
        f"岗位 {result['positions']}"
    )
    return result


def cleanup_master_tables() -> Dict:
    """清理总表中的冗余表与字段(产品化前的一次性整理)。

    执行内容:
    1. 删除表: 数据表、27届校招岗位汇总(孤儿表)、VL识别失败记录
    2. 从所有「岗位-*」分表中删除「招聘流程」字段(若存在)
    """
    from config import settings
    service = FeishuMasterTableService()
    client = service.client
    app_token = settings.MASTER_APP_TOKEN
    if not app_token:
        logger.warning("MASTER_APP_TOKEN 未配置")
        return {"deleted_tables": [], "deleted_fields": []}

    # 1. 列出所有表,按名称删除冗余表
    tables = client.list_tables(app_token)
    tables_to_delete = {"数据表", "27届校招岗位汇总", "VL识别失败记录"}
    deleted_tables = []
    position_tables = []
    for t in tables:
        name = t.get("name", "")
        tid = t.get("table_id", "")
        if name in tables_to_delete:
            if client.delete_table(app_token, tid):
                deleted_tables.append(name)
        elif name.startswith("岗位-"):
            position_tables.append((name, tid))

    # 2. 从岗位分表中删除「招聘流程」字段
    deleted_fields = []
    for name, tid in position_tables:
        fields = client.list_fields(app_token, tid)
        for f in fields:
            if f.get("field_name") == "招聘流程":
                if client.delete_field(app_token, tid, f["field_id"]):
                    deleted_fields.append(f"{name}.招聘流程")

    result = {"deleted_tables": deleted_tables, "deleted_fields": deleted_fields}
    logger.info(f"总表清理完成: 删除表 {deleted_tables}, 删除字段 {deleted_fields}")
    return result


def add_guide_table_to_master() -> str:
    """给已存在的总表添加「📖 使用说明」表(产品化入口)。

    如果已存在同名表则跳过创建,直接复用。
    返回 guide_table_id。
    """
    from config import settings
    service = FeishuMasterTableService()
    client = service.client
    app_token = settings.MASTER_APP_TOKEN
    if not app_token:
        logger.warning("MASTER_APP_TOKEN 未配置")
        return ""

    guide_table_id = client.get_or_create_table(app_token, "📖 使用说明")
    service._setup_guide_table(app_token, guide_table_id)
    return guide_table_id
