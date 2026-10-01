"""查看源表记录的完整返回结构。"""
import sys
sys.path.insert(0, "/opt/job_assistant")

from feishu_client import FeishuClient
from config import settings
import job_db

client = FeishuClient()
app_token = client.resolve_app_token(settings.SOURCE_APP_TOKEN)
table_id = settings.SOURCE_TABLE_ID

ann = job_db._get_conn().execute(
    "SELECT id, feishu_record_id FROM announcements WHERE llm_status='skipped' LIMIT 1"
).fetchone()

record = client.get_record(app_token, table_id, ann[1])
print("=== record 完整结构 ===")
import json
print(json.dumps(record, ensure_ascii=False, indent=2)[:2000])
