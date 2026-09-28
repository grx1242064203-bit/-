"""
飞书总表服务 — 把 companies 和 positions 总库导出到飞书多维表格,供用户直接查看。

设计原则(第一性原理):
1. 一张多维表格包含「公司总表」+「岗位总表」两个子表
2. 设置为「互联网获得链接可查看」— 用户无需飞书账号,浏览器打开即看
3. 增量写入:先查重再插入,避免重复
4. 批量写入(每批 500 条),控制 API 调用频率
"""
import logging
import time
from typing import Dict, List

import job_db
from feishu_client import FeishuClient

logger = logging.getLogger(__name__)

# 表名
TABLE_COMPANIES = "公司总表"
TABLE_POSITIONS = "岗位总表"

# 公司总表字段
COMPANY_FIELDS = [
    {"name": "公司名称", "type": 1},
    {"name": "行业", "type": 1},
    {"name": "公司类型", "type": 1},
    {"name": "公告数", "type": 2, "style": {"formatter": "0"}},
    {"name": "岗位数", "type": 2, "style": {"formatter": "0"}},
    {"name": "网申链接", "type": 15},
]

# 岗位总表字段
POSITION_FIELDS = [
    {"name": "岗位标题", "type": 1},
    {"name": "公司", "type": 1},
    {"name": "岗位分类", "type": 1},
    {"name": "岗位子类", "type": 1},
    {"name": "最低学历", "type": 1},
    {"name": "专业要求", "type": 1},
    {"name": "专业大类", "type": 1},
    {"name": "城市", "type": 1},
    {"name": "硬技能", "type": 1},
    {"name": "关键词", "type": 1},
    {"name": "是否管培", "type": 3, "options": [{"name": "是"}, {"name": "否"}]},
    {"name": "难度", "type": 1},
    {"name": "JD摘要", "type": 1},
    {"name": "投递链接", "type": 15},
    {"name": "公司行业", "type": 1},
    {"name": "公司类型", "type": 1},
]


class FeishuMasterTableService:
    """飞书总表(公司+岗位)导出服务。"""

    def __init__(self, client: FeishuClient = None):
        self.client = client or FeishuClient()

    def create_master_bitable(self, name: str = "校招岗位总表") -> Dict:
        """创建总表多维表格,返回 app_token 和子表 ID。"""
        app_token = self.client.create_bitable(name)
        logger.info(f"创建总表多维表格: {name} -> {app_token}")

        # 创建公司总表
        company_table_id = self.client.create_table(app_token, TABLE_COMPANIES)
        self._create_fields(app_token, company_table_id, COMPANY_FIELDS, "公司名称")

        # 创建岗位总表
        position_table_id = self.client.create_table(app_token, TABLE_POSITIONS)
        self._create_fields(app_token, position_table_id, POSITION_FIELDS, "岗位标题")

        # 设置互联网可查看
        self.client.set_public_share(app_token, doc_type="bitable")
        share_url = self.client.get_share_url(app_token, doc_type="bitable")
        logger.info(f"总表分享链接: {share_url}")

        return {
            "app_token": app_token,
            "company_table_id": company_table_id,
            "position_table_id": position_table_id,
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

    @staticmethod
    def _url_field(url: str) -> Dict:
        """飞书 URL 字段需要对象格式。"""
        if not url:
            return None
        return {"link": url, "text": url[:50]}

    def export_companies(self, app_token: str, table_id: str, limit: int = 0) -> int:
        """导出公司总表数据到飞书。返回写入数。"""
        companies = job_db.get_all_companies()
        if limit:
            companies = companies[:limit]

        records = []
        for c in companies:
            ann_count = job_db.get_announcement_count_by_company(c["id"])
            pos_count = job_db.get_position_count_by_company(c["id"])
            record = {
                "公司名称": c["name"],
                "行业": c.get("industry", ""),
                "公司类型": c.get("company_type", ""),
                "公告数": ann_count,
                "岗位数": pos_count,
            }
            url = self._url_field(c.get("apply_url", ""))
            if url:
                record["网申链接"] = url
            records.append(record)
        if not records:
            return 0
        ids = self.client.batch_create_records(app_token, table_id, records)
        logger.info(f"公司总表写入 {len(ids)}/{len(records)} 条")
        return len(ids)

    def export_positions(self, app_token: str, table_id: str, limit: int = 0) -> int:
        """导出岗位总表数据到飞书。返回写入数。"""
        positions = job_db.get_all_positions_for_export()
        if limit:
            positions = positions[:limit]

        records = []
        for p in positions:
            record = {
                "岗位标题": p["position_title"],
                "公司": p["company_name"],
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
                "公司行业": p.get("industry", ""),
                "公司类型": p.get("company_type", ""),
            }
            url = self._url_field(p.get("apply_url", "") or p.get("source_url", ""))
            if url:
                record["投递链接"] = url
            records.append(record)
        if not records:
            return 0
        ids = self.client.batch_create_records(app_token, table_id, records)
        logger.info(f"岗位总表写入 {len(ids)}/{len(records)} 条")
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
    result["companies_written"] = n_companies
    result["positions_written"] = n_positions
    logger.info(f"总表导出完成: 公司 {n_companies} 条, 岗位 {n_positions} 条")
    logger.info(f"总表链接: {result['share_url']}")
    return result
