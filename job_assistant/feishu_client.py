"""
飞书 API 客户端。

设计原则(对抗性审查后):
1. tenant_access_token 缓存 + 自动刷新(2小时过期,提前5分钟刷新)
2. 所有写操作带重试(指数退避),应对限流(5次/秒)
3. 创建资源后立即分享给用户并转移所有权 — 用户真正拥有数据
4. 失败不影响其他用户 — 调用方捕获异常
"""
import json
import time
import logging
from typing import Dict, List, Optional, Any

import requests

from config import settings

logger = logging.getLogger(__name__)

FEISHU_HOST = "https://open.feishu.cn"

# 多维表格字段类型
FIELD_TYPE_TEXT = 1
FIELD_TYPE_NUMBER = 2
FIELD_TYPE_DATETIME = 5
FIELD_TYPE_SELECT = 3
FIELD_TYPE_URL = 15


class FeishuClient:
    """飞书开放平台客户端 — 基于 tenant_access_token(应用身份)"""

    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id or settings.FEISHU_APP_ID
        self.app_secret = app_secret or settings.FEISHU_APP_SECRET
        self._token: Optional[str] = None
        self._token_expire: float = 0

    # ---------- Token 管理 ----------
    def _get_tenant_token(self) -> str:
        if self._token and time.time() < self._token_expire - 300:
            return self._token
        resp = requests.post(
            f"{FEISHU_HOST}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
        self._token = data["tenant_access_token"]
        self._token_expire = time.time() + data.get("expire", 7200)
        logger.info("tenant_access_token 已刷新")
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_tenant_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def _request(self, method: str, path: str, json_body: dict = None,
                 params: dict = None) -> dict:
        """带重试的请求,应对 99991400(限流)等临时错误"""
        url = f"{FEISHU_HOST}{path}"
        # 手动序列化 JSON(ensure_ascii=False),发送原始 UTF-8 中文
        # 原因:requests 默认 json= 会把中文转义成 \uXXXX,飞书可能解析异常
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8") if json_body else None
        for attempt in range(settings.FEISHU_RETRY):
            try:
                resp = requests.request(
                    method, url, headers=self._headers(),
                    data=data, params=params, timeout=30,
                )
                data = resp.json()
                code = data.get("code", -1)
                if code == 0:
                    return data.get("data", {})
                # 限流或临时错误,重试
                if code in (99991400, 1254291, 500) and attempt < settings.FEISHU_RETRY - 1:
                    wait = 2 ** attempt
                    logger.warning(f"飞书 API 临时错误 code={code}, {wait}s 后重试")
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"飞书 API 错误 code={code} msg={data.get('msg')} path={path} body={json.dumps(data, ensure_ascii=False)[:500]}")
            except requests.RequestException as e:
                if attempt < settings.FEISHU_RETRY - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise RuntimeError(f"飞书 API 重试耗尽: {path}")

    # ---------- 多维表格 ----------
    def create_bitable(self, name: str) -> str:
        """创建多维表格,返回 app_token"""
        data = self._request("POST", "/open-apis/bitable/v1/apps",
                             json_body={"name": name})
        return data["app"]["app_token"]

    def create_table(self, app_token: str, name: str) -> str:
        """在多维表格中创建数据表,返回 table_id"""
        data = self._request(
            "POST", f"/open-apis/bitable/v1/apps/{app_token}/tables",
            json_body={"table": {"name": name}},
        )
        return data["table_id"]

    def create_field(self, app_token: str, table_id: str, field_name: str,
                     field_type: int, **kwargs) -> str:
        """创建字段"""
        body = {"field_name": field_name, "type": field_type}
        body.update(kwargs)
        data = self._request(
            "POST",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
            json_body=body,
        )
        return data["field"]["field_id"]

    def batch_create_records(self, app_token: str, table_id: str,
                             records: List[Dict]) -> List[str]:
        """批量写入记录,每批最多 500 条,返回 record_id 列表"""
        ids = []
        for i in range(0, len(records), 500):
            batch = records[i:i + 500]
            data = self._request(
                "POST",
                f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
                json_body={"records": [{"fields": r} for r in batch]},
            )
            ids.extend(r["record_id"] for r in data.get("records", []))
            time.sleep(settings.FEISHU_API_INTERVAL)
        return ids

    def search_records(self, app_token: str, table_id: str,
                       filter_expr: str, fields: List[str] = None) -> List[Dict]:
        """按条件查询记录(用于去重 hash 查询)"""
        all_records = []
        page_token = None
        while True:
            params = {"page_size": 200, "filter": filter_expr}
            if page_token:
                params["page_token"] = page_token
            if fields:
                params["field_names"] = json.dumps(fields)
            data = self._request(
                "GET",
                f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/search",
                params=params,
            )
            all_records.extend(data.get("items", []))
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
        return all_records

    def delete_record(self, app_token: str, table_id: str, record_id: str):
        """删除单条记录"""
        self._request(
            "DELETE",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
        )

    def get_record(self, app_token: str, table_id: str, record_id: str) -> Dict:
        """获取单条记录完整字段(用于归档前拉取完整数据)"""
        return self._request(
            "GET",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
        ).get("record", {}).get("fields", {})

    @staticmethod
    def normalize_fields(fields: Dict) -> Dict:
        """
        将飞书读出的字段值归一化为可写入的格式。
        读出格式: select=[{name}], url={text,link}, datetime=时间戳
        写入格式: select="name" 或 [name], url={text,link}, datetime="yyyy-MM-dd HH:mm:ss"
        """
        result = {}
        for k, v in fields.items():
            if v is None or v == "":
                continue
            if isinstance(v, list):
                # select 多选/单选数组: [{"name": "xxx"}]
                names = [item.get("name") if isinstance(item, dict) else str(item)
                         for item in v if item]
                if len(names) == 1:
                    result[k] = names[0]
                elif len(names) > 1:
                    result[k] = names
                # 空数组跳过
            elif isinstance(v, dict):
                if "link" in v:
                    # url 字段: {"text": "...", "link": "..."}
                    result[k] = v
                else:
                    # 其他对象转字符串
                    result[k] = str(v)
            else:
                result[k] = v
        return result

    # ---------- 文档 ----------
    def create_doc(self, title: str) -> tuple:
        """创建新版文档,返回 (document_id, url)"""
        data = self._request("POST", "/open-apis/docx/v1/documents",
                             json_body={"title": title})
        doc_id = data["document"]["document_id"]
        url = data["document"]["url"]
        return doc_id, url

    def append_doc_blocks(self, document_id: str, blocks: List[Dict]):
        """向文档追加内容块(blocks)"""
        # 文档根 block_id = document_id
        self._request(
            "POST",
            f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children",
            json_body={"children": blocks},
        )

    # ---------- 权限:分享 + 转移所有权 ----------
    def share_with_user(self, token: str, doc_type: str,
                        open_id: str, perm: str = "full_access"):
        """将文档/表格分享给用户,perm: view/edit/full_access"""
        self._request(
            "POST",
            f"/open-apis/drive/v1/permissions/{token}/members?type={doc_type}",
            json_body={
                "member_type": "openid",
                "member_id": open_id,
                "perm": perm,
            },
        )

    def transfer_owner(self, token: str, doc_type: str, open_id: str):
        """将文档/表格所有权转移给用户(用户真正拥有数据)"""
        try:
            self._request(
                "POST",
                f"/open-apis/drive/v1/permissions/{token}/members/transfer_owner?type={doc_type}",
                json_body={
                    "member_type": "openid",
                    "member_id": open_id,
                },
            )
            logger.info(f"所有权已转移给用户 {open_id}")
        except RuntimeError as e:
            # 转移所有权可能因权限配置失败,降级为只分享
            logger.warning(f"所有权转移失败,降级为分享: {e}")
            self.share_with_user(token, doc_type, open_id, "full_access")
