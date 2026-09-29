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
    {"name": "医科"}, {"name": "艺术"}, {"name": "不限"}, {"name": "其他"},
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
    "公司名称": 120, "公告标题": 200, "网申更新": 90, "VL错误信息": 300,
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
    "公司类型": 80, "招聘流程": 140, "岗位分类": 70, "岗位子类": 90,
    "最低学历": 70, "专业要求": 120, "专业大类": 70, "城市": 90,
    "硬技能": 120, "关键词": 120, "是否管培": 60, "难度": 80,
    "JD摘要": 150, "投递链接": 100, "公告链接": 100,
}

# 岗位总表字段
# 字段顺序: 岗位标题 → 网申更新 → 公司名称 → 公司行业 → 公司类型 → 招聘流程 →
#           岗位分类 → 岗位子类 → 最低学历 → 专业要求 → 专业大类 → 城市 →
#           硬技能 → 关键词 → 是否管培 → 难度 → JD摘要 → 投递链接 → 公告链接
POSITION_FIELDS = [
    {"name": "岗位标题", "type": 1},
    {"name": "网申更新", "type": 5},
    {"name": "公司名称", "type": 1},
    {"name": "公司行业", "type": 3, "options": INDUSTRY_OPTIONS},
    {"name": "公司类型", "type": 3, "options": COMPANY_TYPE_OPTIONS},
    {"name": "招聘流程", "type": 1},
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
]


class FeishuMasterTableService:
    """飞书总表(公司+岗位)导出服务。"""

    def __init__(self, client: FeishuClient = None):
        self.client = client or FeishuClient()

    def create_master_bitable(self, name: str = "27届校招汇总表") -> Dict:
        """创建总表多维表格,返回 app_token 和子表 ID。"""
        app_token = self.client.create_bitable(name)
        logger.info(f"创建总表多维表格: {name} -> {app_token}")

        # 创建公司总表
        company_table_id = self.client.create_table(app_token, TABLE_COMPANIES)
        self._create_fields(app_token, company_table_id, COMPANY_FIELDS, "公司名称")
        self._setup_view(app_token, company_table_id, COMPANY_COL_WIDTHS, "网申更新")

        # 创建岗位总表
        position_table_id = self.client.create_table(app_token, TABLE_POSITIONS)
        self._create_fields(app_token, position_table_id, POSITION_FIELDS, "岗位标题")
        self._setup_view(app_token, position_table_id, POSITION_COL_WIDTHS, "网申更新")

        # 创建 VL 识别失败记录表
        vl_failure_table_id = self.client.create_table(app_token, TABLE_VL_FAILURES)
        self._create_fields(app_token, vl_failure_table_id, VL_FAILURE_FIELDS, "公司名称")
        self._setup_view(app_token, vl_failure_table_id, VL_FAILURE_COL_WIDTHS, "网申更新")

        # 设置互联网可查看
        self.client.set_public_share(app_token, doc_type="bitable")
        share_url = self.client.get_share_url(app_token, doc_type="bitable")
        logger.info(f"总表分享链接: {share_url}")

        return {
            "app_token": app_token,
            "company_table_id": company_table_id,
            "position_table_id": position_table_id,
            "vl_failure_table_id": vl_failure_table_id,
            "share_url": share_url,
        }

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
        for f in fields[1:]:  # 跳过主字段(已重命名)
            if f["name"] not in existing:
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

    def export_companies(self, app_token: str, table_id: str, limit: int = 0) -> int:
        """导出公司总表数据到飞书(含源表所有字段)。返回写入数。

        注意:飞书 API 的 PATCH view 不支持设置 sort/column_width,
        因此通过写入前排序保证默认展示顺序为「网申更新降序」。
        """
        companies = job_db.get_all_companies()
        if limit:
            companies = companies[:limit]

        records = []
        for c in companies:
            # 取最新公告的源表字段
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
                "_sort_key": apply_update or "",  # 临时排序键
            }
            apply_url = self._url_field(c.get("apply_url", ""))
            if apply_url:
                record["网申链接"] = apply_url
            ann_url = self._url_field(latest_ann.get("announcement_url", ""))
            if ann_url:
                record["公告链接"] = ann_url
            records.append(record)

        # 按网申更新降序排序(最新在前),空值排最后
        records.sort(key=lambda r: r.get("_sort_key", "") or "", reverse=True)
        # 移除临时排序键
        for r in records:
            r.pop("_sort_key", None)

        if not records:
            return 0
        ids = self.client.batch_create_records(app_token, table_id, records)
        logger.info(f"公司总表写入 {len(ids)}/{len(records)} 条")
        return len(ids)

    def export_positions(self, app_token: str, table_id: str, limit: int = 0) -> int:
        """导出岗位总表数据到飞书。返回写入数。

        注意:飞书 API 的 PATCH view 不支持设置 sort/column_width,
        因此通过写入前排序保证默认展示顺序为「网申更新降序」。
        """
        positions = job_db.get_all_positions_for_export()
        if limit:
            positions = positions[:limit]

        records = []
        for p in positions:
            # 岗位标题加上公司名后缀,如 "AI算法研究员/实习生-TenX AI"
            title = p["position_title"] or "通用校招岗"
            company = p["company_name"] or ""
            display_title = f"{title}-{company}" if company else title
            apply_update = p.get("apply_update", "")
            record = {
                "岗位标题": display_title,
                "网申更新": self._date_to_ts(apply_update),
                "公司名称": p["company_name"],
                "公司行业": p.get("industry", ""),
                "公司类型": p.get("company_type", ""),
                "招聘流程": p.get("recruitment_process", ""),
                "岗位分类": p.get("job_category", ""),
                "岗位子类": p.get("job_subcategory", ""),
                "最低学历": p.get("min_education", "") or p.get("education_req", ""),
                "专业要求": p.get("major_required", "") or p.get("major_req", ""),
                "专业大类": p.get("major_category", ""),
                "城市": p.get("city", "") or p.get("location", ""),
                "硬技能": p.get("hard_skills", ""),
                "关键词": p.get("keywords", ""),
                "是否管培": "是" if p.get("is_management_trainee") else "否",
                "难度": p.get("difficulty", ""),
                "JD摘要": p.get("jd_summary", ""),
                "_sort_key": apply_update or "",  # 临时排序键
            }
            url = self._url_field(p.get("apply_url", "") or p.get("source_url", ""))
            if url:
                record["投递链接"] = url
            ann_url = self._url_field(p.get("announcement_url", ""))
            if ann_url:
                record["公告链接"] = ann_url
            records.append(record)

        # 按网申更新降序排序(最新在前),空值排最后
        records.sort(key=lambda r: r.get("_sort_key", "") or "", reverse=True)
        # 移除临时排序键
        for r in records:
            r.pop("_sort_key", None)

        if not records:
            return 0
        ids = self.client.batch_create_records(app_token, table_id, records)
        logger.info(f"岗位总表写入 {len(ids)}/{len(records)} 条")
        return len(ids)

    def export_vl_failures(self, app_token: str, table_id: str) -> int:
        """导出 VL 识别失败的公告到飞书记录表。返回写入数。

        只导出 vl_status=failed 的公告,便于排查哪些公告的图片无法被 VL 识别。
        """
        announcements = job_db.get_vl_failed_announcements()

        records = []
        for ann in announcements:
            # 计算图片数量
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

        # 按网申更新降序排序
        records.sort(key=lambda r: r.get("_sort_key", "") or "", reverse=True)
        for r in records:
            r.pop("_sort_key", None)

        if not records:
            logger.info("无 VL 失败记录,跳过导出")
            return 0
        ids = self.client.batch_create_records(app_token, table_id, records)
        logger.info(f"VL 失败记录表写入 {len(ids)}/{len(records)} 条")
        return len(ids)


def create_and_export_master_table(company_limit: int = 0,
                                   position_limit: int = 0) -> Dict:
    """一键创建总表并导出数据。"""
    service = FeishuMasterTableService()
    result = service.create_master_bitable()
    n_companies = service.export_companies(
        result["app_token"], result["company_table_id"], limit=company_limit)
    n_positions = service.export_positions(
        result["app_token"], result["position_table_id"], limit=position_limit)
    n_vl_failures = service.export_vl_failures(
        result["app_token"], result["vl_failure_table_id"])
    result["companies_written"] = n_companies
    result["positions_written"] = n_positions
    result["vl_failures_written"] = n_vl_failures
    logger.info(
        f"总表导出完成: 公司 {n_companies} 条, 岗位 {n_positions} 条, "
        f"VL失败 {n_vl_failures} 条"
    )
    logger.info(f"总表链接: {result['share_url']}")
    return result


def sync_to_existing_master_table() -> Dict:
    """同步数据到已存在的飞书总表(清空后全量重写)。

    用于每日管线:把本地 DB 的公司/岗位/VL失败记录同步到飞书总表。
    表的 app_token 和 table_id 从 config.settings 读取。

    Returns: {"companies": N, "positions": M, "vl_failures": K}
    """
    from config import settings
    service = FeishuMasterTableService()
    app_token = settings.MASTER_APP_TOKEN
    company_table_id = settings.MASTER_COMPANY_TABLE_ID
    position_table_id = settings.MASTER_POSITION_TABLE_ID
    vl_failure_table_id = settings.MASTER_VL_FAILURE_TABLE_ID

    if not app_token:
        logger.warning("MASTER_APP_TOKEN 未配置,跳过总表同步")
        return {"companies": 0, "positions": 0, "vl_failures": 0}

    result = {"companies": 0, "positions": 0, "vl_failures": 0}

    # 1. 同步公司总表
    if company_table_id:
        try:
            service.client.clear_table_records(app_token, company_table_id)
            result["companies"] = service.export_companies(app_token, company_table_id)
        except Exception as e:
            logger.error(f"同步公司总表失败: {e}")

    # 2. 同步岗位总表
    if position_table_id:
        try:
            service.client.clear_table_records(app_token, position_table_id)
            result["positions"] = service.export_positions(app_token, position_table_id)
        except Exception as e:
            logger.error(f"同步岗位总表失败: {e}")

    # 3. 同步 VL 失败记录表
    if vl_failure_table_id:
        try:
            service.client.clear_table_records(app_token, vl_failure_table_id)
            result["vl_failures"] = service.export_vl_failures(app_token, vl_failure_table_id)
        except Exception as e:
            logger.error(f"同步VL失败记录表失败: {e}")

    logger.info(
        f"总表同步完成: 公司 {result['companies']} 条, "
        f"岗位 {result['positions']} 条, VL失败 {result['vl_failures']} 条"
    )
    return result
