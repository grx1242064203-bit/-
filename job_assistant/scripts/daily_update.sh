#!/bin/bash
# 每日增量更新:同步源表变更 → LLM 拆岗（源表岗位名填字段）
# 每天 15:00 执行(cron)
# 用法: bash scripts/daily_update.sh

set -e
cd /opt/job_assistant/job_assistant
source /opt/job_assistant/job_assistant/job_api/venv/bin/activate

export DATA_DIR=${DATA_DIR:-/opt/job_assistant/job_assistant/data}
export PYTHONUNBUFFERED=1

echo "====== 每日增量更新 ======"
echo "时间: $(date)"

# 增量同步 → LLM 拆岗(200条)
python3 -c "
from daily_runner import run_daily_pipeline
r = run_daily_pipeline(sync_full=False, enrich_limit=200)
print(f'管线结果: {r}')
"

echo ""
echo "====== 更新完成 ======"
echo "时间: $(date)"
