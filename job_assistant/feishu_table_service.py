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
from schema import JOB_FIELDS, CLOSED_JOB_FIELDS, MT_TABLE_FIELDS

logger = logging.getLogger(__name__)

# 表名常量
TABLE_NAME_JOBS = "岗位数据库"
TABLE_NAME_CLOSED = "已关闭岗位"
TABLE_NAME_MT = "管培项目"

# 主字段名(建表后第一个字段自动成为主字段,需重命名)
PRIMARY_FIELD_JOB = "岗位标题"
PRIMARY_FIELD_MT = "项目名称"


class FeishuTableService:
    """用户专属多维表格创建与管理。"""

    def __init__(self, client: FeishuClient = None):
        self.client = client or FeishuClient()

    def create_user_bitable(self, user_display_name: str = "校招用户") -> Dict:
        """
        为用户创建专属多维表格,含 3 张表 + 全部字段 + 互联网分享。

        Args:
            user_display_name: 用户名(用于表格命名,如 "张三的岗位库")

        Returns:
            {
                "app_token": "xxx",
                "jobs_table_id": "xxx",
                "closed_table_id": "xxx",
                "mt_table_id": "xxx",
                "share_url": "https://www.feishu.cn/base/xxx"
            }
        """
        bitable_name = f"{user_display_name}的校招岗位库"

        # 1. 创建多维表格
        app_token = self.client.create_bitable(bitable_name)
        logger.info(f"创建多维表格: {bitable_name} -> {app_token}")

        # 2. 创建 3 张数据表
        jobs_table_id = self.client.create_table(app_token, TABLE_NAME_JOBS)
        closed_table_id = self.client.create_table(app_token, TABLE_NAME_CLOSED)
        mt_table_id = self.client.create_table(app_token, TABLE_NAME_MT)
        logger.info(f"创建 3 张表: jobs={jobs_table_id} closed={closed_table_id} mt={mt_table_id}")

        # 3. 创建字段(耗时,但必须在返回前完成,否则写入会失败)
        self._create_table_fields(app_token, jobs_table_id, JOB_FIELDS, PRIMARY_FIELD_JOB)
        self._create_table_fields(app_token, closed_table_id, CLOSED_JOB_FIELDS, PRIMARY_FIELD_JOB)
        self._create_table_fields(app_token, mt_table_id, MT_TABLE_FIELDS, PRIMARY_FIELD_MT)

        # 4. 设置互联网链接可查看(关键!用户无需登录飞书)
        self.client.set_public_share(app_token, doc_type="bitable")

        # 5. 生成分享链接
        share_url = self.client.get_share_url(app_token, doc_type="bitable")

        result = {
            "app_token": app_token,
            "jobs_table_id": jobs_table_id,
            "closed_table_id": closed_table_id,
            "mt_table_id": mt_table_id,
            "share_url": share_url,
        }
        logger.info(f"用户表格创建完成: {share_url}")
        return result

    def _create_table_fields(self, app_token: str, table_id: str,
                             fields: list, primary_field_name: str):
        """
        创建表的全部字段。
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

        # 创建其余字段
        for f in fields:
            if f["name"] == primary_field_name:
                continue  # 主字段已重命名
            kwargs = {}
            if "style" in f:
                kwargs["property"] = f["style"]
            if "options" in f:
                kwargs["property"] = {"options": f["options"]}
            try:
                self.client.create_field(
                    app_token, table_id, f["name"], f["type"], **kwargs
                )
            except Exception as e:
                # 字段创建失败不阻塞(可能字段已存在)
                logger.warning(f"创建字段失败 {f['name']}: {e}")
            time.sleep(0.1)  # 避免限流

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
