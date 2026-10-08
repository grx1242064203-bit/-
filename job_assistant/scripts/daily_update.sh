#!/bin/bash
# 每日增量更新:只同步源表变更 → 抓新增公告正文 → 拆新增岗位
# 建议每天 8:00 执行(cron)
# 用法: bash scripts/daily_update.sh

set -e
cd /opt/job_assistant/job_assistant
source /opt/job_assistant/job_assistant/job_api/venv/bin/activate

export DATA_DIR=${DATA_DIR:-/opt/job_assistant/job_assistant/data}
export PYTHONUNBUFFERED=1

echo "====== 每日增量更新 ======"
echo "时间: $(date)"

# 增量同步 → 抓正文(200条) → 拆岗(200条)
python3 -c "
from daily_runner import run_daily_pipeline
r = run_daily_pipeline(sync_full=False, crawl_limit=200, enrich_limit=200, crawl_workers=2)
print(f'管线结果: {r}')
"

echo ""
echo "====== 更新完成 ======"
echo "时间: $(date)"
