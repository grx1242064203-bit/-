#!/bin/bash
# 启动 Web 配置页(Flask,端口 5000)
# 用法: bash scripts/start_web.sh

cd /opt/job_assistant
source venv/bin/activate

export DATA_DIR=${DATA_DIR:-/opt/job_assistant/data}

# 停止旧进程
pkill -f "python3 web_setup.py" 2>/dev/null || true
sleep 1

# 后台启动
nohup python3 web_setup.py > logs/web.log 2>&1 &

echo "Web 配置页已启动: http://$(curl -s ifconfig.me):5000"
echo "日志: tail -f /opt/job_assistant/logs/web.log"
