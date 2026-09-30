"""
用户专属飞书多维表格服务 — 为每个付费用户创建专属岗位库。

设计原则(第一性原理 + 对抗性审查):
1. 每用户一张多维表格,数据隔离,用户只看到自己的匹配岗位
2. 表格设置为「互联网获得链接可查看」— 用户无需飞书账号,浏览器打开即看
3. 字段定义集中在 schema.py,建表和写记录引用同一套,避免不一致
4. 异步创建字段(耗时),先返回表格链接给用户,不阻塞

数据表:
  - 岗位数据库(在招岗位)
  - 已关闭岗位
  - 管培项目(校招专项)
"""
import logging
import time
from typing import Dict, Optional

from feishu_client import FeishuClient
from schema import JOB_FIELDS, CLOSED_JOB_FIELDS, MT_TABLE_FIELDS, RESUME_FIELDS

logger = logging.getLogger(__name__)

# 表名常量
TABLE_NAME_JOBS = "岗位数据库"
TABLE_NAME_CLOSED = "已关闭岗位"
TABLE_NAME_MT = "管培项目"
TABLE_NAME_RESUME = "简历解析数据"

# 主字段名(建表后第一个字段自动成为主字段,需重命名)
PRIMARY_FIELD_JOB = "岗位标题"
PRIMARY_FIELD_MT = "项目名称"
PRIMARY_FIELD_RESUME = "简历版本"


class FeishuTableService:
    """用户专属多维表格创建与管理。"""

    def __init__(self, client: FeishuClient = None):
        self.client = client or FeishuClient()

    def verify_master_tables(self, app_token: str,
                             company_table_id: str,
                             position_table_id: str) -> Dict:
        """校验总表(公司/岗位)是否存在,返回有效的 table_id 映射。

        通过 list_tables 列出 base 内所有表,检查给定的 table_id 是否真实存在。
        若配置的 ID 失效,尝试按表名查找;都找不到则返回空串。

        Returns:
            {"company_table_id": "...", "position_table_id": "...", "ok": bool}
        """
        result = {"company_table_id": "", "position_table_id": "", "ok": False}
        try:
            tables = self.client.list_tables(app_token)
        except Exception as e:
            logger.warning(f"列出总表失败: {e}")
            return result

        table_map = {t.get("table_id"): t for t in tables}

        # 公司表:优先用配置 ID,失效则按名查找
        if company_table_id and company_table_id in table_map:
            result["company_table_id"] = company_table_id
        else:
            for t in tables:
                if "公司" in t.get("name", "") and "岗位" not in t.get("name", ""):
                    result["company_table_id"] = t.get("table_id", "")
                    break

        # 岗位表:优先用配置 ID,失效则按名查找
        if position_table_id and position_table_id in table_map:
            result["position_table_id"] = position_table_id
        else:
            for t in tables:
                name = t.get("name", "")
                if "岗位" in name and "公司" not in name and "关闭" not in name:
                    result["position_table_id"] = t.get("table_id", "")
                    break

        result["ok"] = bool(result["company_table_id"] and result["position_table_id"])
        return result

    def create_user_bitable(self, order_id: str,
                            user_display_name: str = "校招用户") -> Dict:
        """
        为用户创建专属多维表格,含 4 张表 + 全部字段 + 互联网分享。

        表格命名以订单 ID 为主标识(用户要求),学校名作为辅助展示。

        Args:
            order_id: 订单号(表格主标识,如 "123456")
            user_display_name: 辅助展示名(如学校名 "北京大学")

        Returns:
            {
                "app_token": "xxx",
                "jobs_table_id": "xxx",
                "closed_table_id": "xxx",
                "mt_table_id": "xxx",
                "resume_table_id": "xxx",
                "share_url": "https://www.feishu.cn/base/xxx"
            }
        """
        # 以订单 ID 命名多维表格
        display = f"{user_display_name}·" if user_display_name else ""
        bitable_name = f"校招岗位库·{display}订单{order_id}"

        # 1. 创建多维表格
        app_token = self.client.create_bitable(bitable_name)
        logger.info(f"创建多维表格: {bitable_name} -> {app_token}")

        # 2. 创建 4 张数据表
        jobs_table_id = self.client.create_table(app_token, TABLE_NAME_JOBS)
        closed_table_id = self.client.create_table(app_token, TABLE_NAME_CLOSED)
        mt_table_id = self.client.create_table(app_token, TABLE_NAME_MT)
        resume_table_id = self.client.create_table(app_token, TABLE_NAME_RESUME)
        logger.info(
            f"创建 4 张表: jobs={jobs_table_id} closed={closed_table_id} "
            f"mt={mt_table_id} resume={resume_table_id}"
        )

        # 3. 创建字段(耗时,但必须在返回前完成,否则写入会失败)
        self._create_table_fields(app_token, jobs_table_id, JOB_FIELDS, PRIMARY_FIELD_JOB)
        self._create_table_fields(app_token, closed_table_id, CLOSED_JOB_FIELDS, PRIMARY_FIELD_JOB)
        self._create_table_fields(app_token, mt_table_id, MT_TABLE_FIELDS, PRIMARY_FIELD_MT)
        self._create_table_fields(app_token, resume_table_id, RESUME_FIELDS, PRIMARY_FIELD_RESUME)

        # 4. 设置互联网链接可查看(关键!用户无需登录飞书)
        self.client.set_public_share(app_token, doc_type="bitable")

        # 5. 生成分享链接
        share_url = self.client.get_share_url(app_token, doc_type="bitable")

        result = {
            "app_token": app_token,
            "jobs_table_id": jobs_table_id,
            "closed_table_id": closed_table_id,
            "mt_table_id": mt_table_id,
            "resume_table_id": resume_table_id,
            "share_url": share_url,
        }
        logger.info(f"用户表格创建完成: {share_url}")
        return result

    def _create_table_fields(self, app_token: str, table_id: str,
                             fields: list, primary_field_name: str):
        """
        创建表的全部字段(并行化,提速 ~5x)。
        主字段(第一个字段)需重命名为 primary_field_name,其余正常创建。
        """
        # 重命名主字段
        try:
            existing = self.client.list_fields(app_token, table_id)
            for f in existing:
                if f.get("is_primary"):
                    self.client.update_field(
                        app_token, table_id, f["field_id"],
                        field_name=primary_field_name, type=1,
                    )
                    break
        except Exception as e:
            logger.warning(f"重命名主字段失败 {table_id}: {e}")

        # 收集待创建字段
        to_create = []
        for f in fields:
            if f["name"] == primary_field_name:
                continue
            kwargs = {}
            if "style" in f:
                kwargs["property"] = f["style"]
            if "options" in f:
                kwargs["property"] = {"options": f["options"]}
            to_create.append((f["name"], f["type"], kwargs))

        # 并行创建字段(max_workers=4,飞书限流约5次/秒)
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _create_one(name, ftype, kw):
            try:
                self.client.create_field(app_token, table_id, name, ftype, **kw)
                return name, True
            except Exception as e:
                logger.warning(f"创建字段失败 {name}: {e}")
                return name, False

        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(_create_one, *args) for args in to_create]
            for fut in as_completed(futures):
                fut.result()
        logger.info(f"字段创建完成: {table_id} 共 {len(to_create)} 个")

    def write_jobs(self, app_token: str, table_id: str,
                   jobs: list) -> int:
        """
        向用户表格写入岗位记录。
        自动清洗字段(None 不写入),批量写入。
        返回写入记录数。
        """
        if not jobs:
            return 0
        records = self.client.batch_create_records(app_token, table_id, jobs)
        logger.info(f"写入岗位 {len(records)}/{len(jobs)} 条到 table={table_id}")
        return len(records)

    def write_resume_snapshot(self, app_token: str, table_id: str,
                              profile: "UserProfile", version: int = 1) -> bool:
        """将用户画像快照写入简历解析数据表。

        Args:
            app_token: 用户多维表格 app_token
            table_id: 简历解析数据表 ID
            profile: UserProfile 对象(含 resume_text/summary/highlights 等)
            version: 简历版本号(第几次解析)

        Returns:
            是否写入成功
        """
        import json
        import time as _time

        highlights_text = "\n".join(
            f"• {h}" for h in (profile.highlights or [])
        ) if profile.highlights else ""

        # structured_keywords 是 KeywordTag 列表,序列化为 JSON
        try:
            kw_json = json.dumps(
                [{"kw": k.kw, "standard": k.standard, "category": k.category,
                  "weight": k.weight} for k in (profile.structured_keywords or [])],
                ensure_ascii=False,
            )
        except Exception:
            kw_json = ""

        directions_text = "、".join(
            d.get("direction", "") for d in (profile.fit_directions or []) if isinstance(d, dict)
        )

        record = {
            "简历版本": f"v{version}",
            "解析时间": int(_time.time() * 1000),
            "学校": profile.school or "",
            "学历": profile.degree or "",
            "专业": profile.major or "",
            "毕业年份": str(profile.graduation_year or ""),
            "一句话画像": profile.summary or "",
            "核心亮点": highlights_text,
            "结构化关键词": kw_json,
            "适配方向": directions_text,
            "目标城市": "、".join(profile.target_cities or []),
            "目标行业": "、".join(profile.target_industries or []),
            "方向关键词": "、".join(
                kw for kws in (profile.direction_keywords or {}).values() for kw in kws
            ),
            "核心技能": "、".join(profile.core_skills or []),
            "原始简历": (profile.resume_text or "")[:2000],
        }
        try:
            self.client.batch_create_records(app_token, table_id, [record])
            logger.info(f"写入简历快照 v{version} 到 table={table_id}")
            return True
        except Exception as e:
            logger.error(f"写入简历快照失败: {e}")
            return False

    def archive_job(self, app_token: str, jobs_table_id: str,
                    closed_table_id: str, record_id: str, close_ts: int = None):
        """
        将岗位从「岗位数据库」移到「已关闭岗位」表。
        """
        import time
        close_ts = close_ts or int(time.time() * 1000)
        try:
            fields = self.client.get_record(app_token, jobs_table_id, record_id)
            fields["是否在招"] = "否"
            fields["关闭日期"] = close_ts
            self.client.batch_create_records(
                app_token, closed_table_id, [fields]
            )
            self.client.delete_record(app_token, jobs_table_id, record_id)
        except Exception as e:
            logger.warning(f"归档岗位失败 {record_id}: {e}")
