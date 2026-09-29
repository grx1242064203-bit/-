#!/bin/bash
# 招聘情报助手 — 阿里云一键部署脚本
# 适用: Ubuntu 22.04 / Alibaba Cloud Linux 3 / 宝塔面板
# 用法: bash deploy.sh

set -e

APP_DIR="/opt/job_assistant"
DATA_DIR="$APP_DIR/data"
PYTHON="python3"

echo "====== 招聘情报助手部署 ======"

# 1. 检查 Python
echo "[1/6] 检查 Python 环境..."
$PYTHON --version || { echo "❌ 请先安装 Python 3.10+"; exit 1; }

# 2. 创建目录
echo "[2/6] 创建应用目录..."
sudo mkdir -p $APP_DIR
sudo mkdir -p $DATA_DIR
sudo chown -R $USER:$USER $APP_DIR

# 3. 安装系统依赖
echo "[3/6] 安装系统依赖..."
if command -v apt-get &> /dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3-pip python3-venv python3-dev build-essential
elif command -v yum &> /dev/null; then
    sudo yum install -y python3-pip python3-devel gcc
fi

# 4. 创建虚拟环境 + 安装依赖
echo "[4/6] 安装 Python 依赖..."
cd $APP_DIR
$PYTHON -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# 5. 配置 .env
echo "[5/6] 配置环境变量..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  请编辑 $APP_DIR/.env 填入真实密钥:"
    echo "   FEISHU_APP_ID, FEISHU_APP_SECRET, DEEPSEEK_API_KEY, WECHAT_COOKIE"
else
    echo "   .env 已存在,跳过"
fi

# 6. 设置权限
echo "[6/6] 设置文件权限..."
chmod 600 .env 2>/dev/null || true
chmod 700 $DATA_DIR 2>/dev/null || true

echo ""
echo "====== 部署完成 ======"
echo ""
echo "下一步:"
echo "1. 编辑密钥:  nano $APP_DIR/.env"
echo "2. 首次全量抓取: cd $APP_DIR && DATA_DIR=$DATA_DIR bash scripts/full_crawl.sh"
echo "3. 启动 Web 配置页: cd $APP_DIR && DATA_DIR=$DATA_DIR bash scripts/start_web.sh"
echo "4. 配置每日定时: crontab -e  (参考 scripts/crontab.example)"
echo ""
