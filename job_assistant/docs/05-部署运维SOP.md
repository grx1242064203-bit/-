# 05. 部署运维 SOP

## 1. 部署架构

```
用户 → HTTPS → Nginx (:443) → 反向代理 → callback_server (:8080)
                                              │
                                    systemd (job-callback)
```

- Nginx 负责 HTTPS 终结和反向代理
- callback_server 监听 `127.0.0.1:8080`
- systemd 管理服务进程，自动重启
- cron 每日 9:00 触发 `main.py daily`

---

## 2. 首次部署

### 2.1 服务器准备

```bash
# 安装系统依赖
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git

# 创建应用目录
sudo mkdir -p /opt/job_assistant
sudo chown $USER:$USER /opt/job_assistant
```

### 2.2 代码部署

```bash
cd /opt/job_assistant
git clone <repo_url> .
git checkout trae/agent-ooAq84

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2.3 配置环境变量

```bash
cat > /opt/job_assistant/.env << 'EOF'
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
WXPUSHER_APP_TOKEN=AT_xxx
TAVILY_API_KEY=tvly-xxx
DATA_DIR=/opt/job_assistant/data
EOF

# 限制 .env 权限
chmod 600 /opt/job_assistant/.env
```

### 2.4 Nginx 配置

```nginx
server {
    listen 443 ssl;
    server_name zhaopin-helper.xyz;

    ssl_certificate     /etc/letsencrypt/live/zhaopin-helper.xyz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/zhaopin-helper.xyz/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 2.5 SSL 证书（Let's Encrypt）

```bash
sudo certbot --nginx -d zhaopin-helper.xyz
```

### 2.6 systemd 服务

创建 `/etc/systemd/system/job-callback.service`：

```ini
[Unit]
Description=Job Assistant Callback Server
After=network.target

[Service]
Type=simple
User=admin
WorkingDirectory=/opt/job_assistant
ExecStart=/opt/job_assistant/venv/bin/python /opt/job_assistant/callback_server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable job-callback
sudo systemctl start job-callback
```

### 2.7 定时任务

```bash
crontab -e
# 每日 9:00 执行（北京时间）
0 9 * * * cd /opt/job_assistant && /opt/job_assistant/venv/bin/python main.py daily >> /var/log/job_assistant.log 2>&1
```

---

## 3. 更新部署 SOP（标准流程）

> 这是日常迭代的标准部署流程，每次代码更新后执行。

```bash
cd /opt/job_assistant

# 1. 拉取最新代码
sudo git pull origin trae/agent-ooAq84

# 2. 清理缓存
sudo find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
sudo find . -name "*.pyc" -delete 2>/dev/null

# 3. 语法检查
venv/bin/python3 -m py_compile onboarding.py feishu_client.py daily_runner.py models.py callback_server.py collector.py scorer.py main.py config.py schema.py wxpusher_client.py && echo "语法 OK"

# 4. 清理坏数据（仅保留已知用户 u1，按需调整）
sudo venv/bin/python3 -c "
import json
with open('data/users.json', 'r') as f:
    users = json.load(f)
for uid in list(users.keys()):
    if uid != 'u1':
        del users[uid]
with open('data/users.json', 'w') as f:
    json.dump(users, f, ensure_ascii=False, indent=2)
print('用户清理完成:', list(users.keys()))
"

# 5. 重启服务
sudo systemctl restart job-callback
sleep 3

# 6. 健康检查
curl -s http://localhost:8080/health
```

**预期输出**：
```json
{"status": "ok", "uptime_seconds": 3, "service": "job-callback"}
```

---

## 4. 验证流程

### 4.1 部署后验证

```bash
# 1. 服务状态
sudo systemctl status job-callback

# 2. 健康检查
curl -s http://localhost:8080/health | python3 -m json.tool

# 3. 端口监听
sudo ss -tlnp | grep 8080

# 4. Nginx 转发
curl -s https://zhaopin-helper.xyz/health
```

### 4.2 功能验证（91402 修复验证）

```bash
cd /opt/job_assistant
source venv/bin/activate
python verify_fix.py
```

验证脚本会依次执行：
1. 凭证检查
2. token 解析测试（wiki node_token → obj_token）
3. 存量用户 token 迁移
4. 单用户每日任务测试

### 4.3 端到端验证

1. **飞书回调**：在飞书中打开应用，检查 `users.json` 是否新增用户
2. **多维表格**：确认用户专属多维表格已创建，字段完整
3. **每日任务**：`python main.py single <user_id>`，确认岗位写入飞书表格
4. **微信推送**：确认用户收到 WxPusher 日报推送

---

## 5. 运维监控

### 5.1 日志查看

```bash
# 回调服务日志
sudo journalctl -u job-callback -n 100 -f

# 每日任务日志
tail -f /var/log/job_assistant.log

# Nginx 日志
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 5.2 健康检查

```bash
# 手动检查
curl -s http://localhost:8080/health

# 可配置监控（如 UptimeRobot）定时访问
https://zhaopin-helper.xyz/health
```

### 5.3 常用排查命令

```bash
# 服务重启
sudo systemctl restart job-callback

# 查看服务状态
sudo systemctl status job-callback

# 查看最近错误
sudo journalctl -u job-callback -n 50 --no-pager | grep -i error

# 手动执行每日任务（调试）
cd /opt/job_assistant && venv/bin/python main.py single u1
```

---

## 6. 回滚 SOP

### 6.1 代码回滚

```bash
cd /opt/job_assistant
git log --oneline -10          # 查看提交历史
git checkout <commit_hash>     # 回滚到指定提交
sudo systemctl restart job-callback
curl -s http://localhost:8080/health
```

### 6.2 服务紧急降级

若飞书 API 大面积故障，可临时停止定时任务：

```bash
# 暂停 cron 任务
crontab -e  # 注释掉 daily 任务行

# 回调服务保持运行（不影响已安装用户查看数据）
```

---

## 7. 数据备份

### 7.1 备份脚本

```bash
#!/bin/bash
# /opt/job_assistant/backup.sh
BACKUP_DIR="/opt/job_assistant/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

cp /opt/job_assistant/data/users.json $BACKUP_DIR/users_$DATE.json
cp -r /opt/job_assistant/data/hashes $BACKUP_DIR/hashes_$DATE

# 保留最近 30 天
find $BACKUP_DIR -name "*.json" -mtime +30 -delete
```

```bash
# 添加到 cron
0 3 * * * /opt/job_assistant/backup.sh
```

### 7.2 恢复

```bash
cp /opt/job_assistant/backups/users_YYYYMMDD_HHMMSS.json /opt/job_assistant/data/users.json
sudo systemctl restart job-callback
```
