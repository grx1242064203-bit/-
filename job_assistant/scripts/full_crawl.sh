#!/bin/bash
# 首次全量抓取:同步源表 → 抓正文 → LLM拆岗 → 导出飞书总表
# 预计耗时: 3-5 小时(取决于网络和LLM响应速度)
# 用法: bash scripts/full_crawl.sh

set -e
cd /opt/job_assistant
source venv/bin/activate

export DATA_DIR=${DATA_DIR:-/opt/job_assistant/data}
export PYTHONUNBUFFERED=1

echo "====== 首次全量抓取开始 ======"
echo "时间: $(date)"

# 1. 全量同步飞书源表
echo ""
echo "[1/4] 全量同步飞书源表..."
python3 -c "
from feishu_source import FeishuSourceSync
s = FeishuSourceSync()
r = s.sync(full=True)
print(f'同步结果: {r}')
"

# 2. 抓取正文(3线程并发,全量)
echo ""
echo "[2/4] 抓取正文(全量,3线程)..."
python3 -c "
from content_fetcher import fetch_announcement_contents
r = fetch_announcement_contents(limit=99999, workers=3)
print(f'抓取结果: {r}')
"

# 3. LLM 拆岗(全量)
echo ""
echo "[3/4] LLM 拆岗(全量)..."
python3 -c "
from llm_enricher import run_enrichment
r = run_enrichment(limit=99999)
print(f'拆岗结果: {r}')
"

# 4. 导出飞书总表
echo ""
echo "[4/4] 导出飞书总表..."
python3 -c "
from feishu_master_tables import create_and_export_master_table
r = create_and_export_master_table()
print(f'总表链接: {r[\"share_url\"]}')
"

echo ""
echo "====== 全量抓取完成 ======"
echo "时间: $(date)"
