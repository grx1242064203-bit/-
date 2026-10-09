#!/bin/bash
# Offer搭子 job_api 一键部署脚本
# 在你 Mac 上跑：bash scripts/deploy_job_api.sh
# 作用：上传 job_api 到服务器 + 装 venv + 配 systemd + 配 nginx + 重启 + 健康检查

set -e

# ============ 配置 ============
SSH_HOST="prod"                              # 已配在 ~/.ssh/config
REMOTE_APP_DIR="/opt/job_assistant/job_api"
REMOTE_DATA_DIR="/opt/job_assistant/data"
LOCAL_JOB_API_DIR="$(cd "$(dirname "$0")/.." && pwd)/job_api"
LOCAL_ENV_FILE="$LOCAL_JOB_API_DIR/.env"

# ============ 检查 ============
echo "====== Offer搭子 job_api 部署 ======"
echo ""

if [ ! -f "$LOCAL_ENV_FILE" ]; then
    echo "❌ 找不到 $LOCAL_ENV_FILE"
    echo "   请先在 Mac 上创建 job_api/.env（参考 .env.example）"
    exit 1
fi

# 检查 ssh prod 能否连
if ! ssh -o ConnectTimeout=10 prod "echo ok" > /dev/null 2>&1; then
    echo "❌ ssh prod 连不上"
    echo "   请确认 ~/.ssh/config 里有 prod 别名（参考 docs/05-部署运维SOP.md 第 3.2 节）"
    exit 1
fi

echo "✅ SSH 连接 OK"
echo "本地代码目录: $LOCAL_JOB_API_DIR"
echo "远程部署目录: $REMOTE_APP_DIR"
echo ""
read -p "继续部署? [y/N] " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "已取消"
    exit 0
fi

# ============ 1. 上传代码 ============
echo ""
echo "[1/6] 上传 job_api 代码到服务器..."
ssh prod "sudo mkdir -p $REMOTE_APP_DIR $REMOTE_DATA_DIR && sudo chown -R admin:admin $REMOTE_APP_DIR $REMOTE_DATA_DIR"

# 用 rsync 增量上传（排除虚拟环境、缓存、本地数据库）
rsync -avz --delete \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='auth.db' \
    --exclude='jobs.db' \
    --exclude='data/' \
    -e "ssh" \
    "$LOCAL_JOB_API_DIR/" "$SSH_HOST:$REMOTE_APP_DIR/"

echo "✅ 代码上传完成"

# ============ 1.5 检查沙箱密钥 ============
echo ""
echo "[1.5/6] 检查支付宝沙箱密钥（.alipay-sandbox.json）..."
if [ ! -f "$LOCAL_JOB_API_DIR/.alipay-sandbox.json" ]; then
    echo "⚠️  .alipay-sandbox.json 不存在"
    echo "   沙箱密钥未自动获取，支付能力将降级为 mock 模式"
    echo "   获取方式："
    echo "     1. 安装 alipay-cli: curl -fsSL https://opengw.alipay.com/alipaycli/install | ALIPAY_CLI_SKIP_VERIFY=true bash"
    echo "     2. 获取沙箱密钥: bash .agents/skills/alipay-aipay/references/integration/modules/scripts/sandbox_config.sh ensure \$(pwd) Python"
    echo "   或在沙箱环境中已生成，手动复制到 job_api/ 目录"
    echo "   继续部署..."
else
    echo "✅ .alipay-sandbox.json 存在（已随代码上传到服务器）"
fi

# ============ 2. 上传 .env ============
echo ""
echo "[2/6] 上传 .env（权限 600）..."
scp "$LOCAL_ENV_FILE" "$SSH_HOST:$REMOTE_APP_DIR/.env"
ssh prod "chmod 600 $REMOTE_APP_DIR/.env"
echo "✅ .env 上传完成"

# ============ 3. 创建虚拟环境 + 安装依赖 ============
echo ""
echo "[3/6] 创建虚拟环境 + 安装依赖（首次较慢，约 2-5 分钟）..."
ssh prod << 'EOF'
cd /opt/job_assistant/job_api
if [ ! -d venv ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ 依赖安装完成"
EOF

# ============ 4. 创建 systemd 服务 ============
echo ""
echo "[4/6] 配置 systemd 服务 job-api..."
ssh prod << 'EOF'
sudo tee /etc/systemd/system/job-api.service > /dev/null << 'UNIT'
[Unit]
Description=Offer搭子 job_api (FastAPI)
After=network.target

[Service]
Type=simple
User=admin
WorkingDirectory=/opt/job_assistant/job_api
Environment="PYTHONUNBUFFERED=1"
ExecStart=/opt/job_assistant/job_api/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable job-api
sudo systemctl restart job-api
sleep 3
sudo systemctl status job-api --no-pager | head -10
EOF

# ============ 5. 配置 nginx ============
echo ""
echo "[5/6] 配置 nginx（/api/v1 和 /download 转给 job-api:8000，其余保留给 job-callback:8080）..."
ssh prod << 'EOF'
# 备份现有 nginx 配置
sudo cp /etc/nginx/sites-available/zhaopin-helper.xyz /etc/nginx/sites-available/zhaopin-helper.xyz.bak.$(date +%Y%m%d_%H%M%S) 2>/dev/null || \
sudo cp /etc/nginx/conf.d/zhaopin-helper.xyz.conf /etc/nginx/conf.d/zhaopin-helper.xyz.conf.bak.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true

# 写新配置（路径分流）
sudo tee /etc/nginx/sites-available/zhaopin-helper.xyz > /dev/null << 'NGINX'
server {
    listen 443 ssl http2;
    server_name zhaopin-helper.xyz;

    ssl_certificate     /etc/letsencrypt/live/zhaopin-helper.xyz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/zhaopin-helper.xyz/privkey.pem;

    # 上传下载安装包的大小限制（默认 1m 太小）
    client_max_body_size 100m;

    # API 接口 → job_api (FastAPI :8000)
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 30s;
    }

    # 下载页 → job_api (FastAPI :8000)
    location /download {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 静态下载文件 → job_api (FastAPI :8000)
    location /downloads/ {
        proxy_pass http://127.0.0.1:8000/downloads/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # 其他路径 → 旧的 callback_server (:8080)
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# HTTP → HTTPS 跳转
server {
    listen 80;
    server_name zhaopin-helper.xyz;
    return 301 https://$host$request_uri;
}
NGINX

# 启用站点
sudo ln -sf /etc/nginx/sites-available/zhaopin-helper.xyz /etc/nginx/sites-enabled/zhaopin-helper.xyz 2>/dev/null || true

# 测试 + 重载
sudo nginx -t
sudo systemctl reload nginx
echo "✅ nginx 配置完成"
EOF

# ============ 6. 健康检查 ============
echo ""
echo "[6/6] 健康检查..."
ssh prod << 'EOF'
echo "--- job-api 服务状态 ---"
sudo systemctl is-active job-api

echo ""
echo "--- 本地 API 健康检查 ---"
curl -s http://127.0.0.1:8000/api/v1/health || echo "❌ 本地 API 不通"

echo ""
echo ""
echo "--- 公网 API 健康检查 ---"
curl -s https://zhaopin-helper.xyz/api/v1/health || echo "❌ 公网 API 不通"

echo ""
echo ""
echo "--- 下载页 ---"
curl -s -o /dev/null -w "HTTP %{http_code}" https://zhaopin-helper.xyz/download || echo "❌ 下载页不通"

echo ""
EOF

echo ""
echo "====== 部署完成 ======"
echo ""
echo "下一步:"
echo "1. 浏览器打开 https://zhaopin-helper.xyz/docs 看 Swagger UI"
echo "2. 浏览器打开 https://zhaopin-helper.xyz/download 看下载页"
echo "3. 如果下载页显示'安装包还在准备中'，正常——CI 还没跑完，等 git push v0.1.0 后 10-20 分钟自动出现"
