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
git checkout main

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> 注意：`trae/agent-ooAq84` 分支已合并到 `main`，生产部署统一使用 `main` 分支。

### 2.3 配置环境变量

```bash
cat > /opt/job_assistant/.env << 'EOF'
# 飞书应用凭证(open.feishu.cn 创建后获取)
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_VERIFICATION_TOKEN=xxx

# 搜索 API(二选一,Tavily 有免费额度)
TAVILY_API_KEY=tvly-xxx

# LLM 配置(DeepSeek,用于简历解析)
DEEPSEEK_API_KEY=sk-xxx

# 数据存储目录
DATA_DIR=/opt/job_assistant/data

# 服务域名(用于生成客户配置页链接)
SERVICE_BASE_URL=https://zhaopin-helper.xyz
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
# 每日 8:00 执行校招总数据库增量采集（中心化，先于用户分发）
0 8 * * * cd /opt/job_assistant && /opt/job_assistant/venv/bin/python -c "from company_crawler import CompanyCrawler; CompanyCrawler().run_daily_crawl()" >> /var/log/job_crawler.log 2>&1
# 每日 9:00 执行用户每日任务（分发）
0 9 * * * cd /opt/job_assistant && /opt/job_assistant/venv/bin/python main.py daily >> /var/log/job_assistant.log 2>&1
# 每周一 9:30 执行校招投递热度榜
30 9 * * 1 cd /opt/job_assistant && /opt/job_assistant/venv/bin/python main.py weekly-ranking >> /var/log/job_assistant_weekly.log 2>&1
```

> **时序说明**：总数据库采集（8:00）必须早于用户分发（9:00），确保用户拿到的是当天最新岗位。

### 2.8 校招总数据库初始化（首次部署必做）

首次部署或更新到含总数据库架构的版本后，必须执行以下步骤初始化总数据库并完成首次全量采集：

```bash
cd /opt/job_assistant
source venv/bin/activate

# 1. 初始化数据库表结构（若已存在则跳过）
python -c "from job_db import init_db; init_db(); print('数据库初始化完成')"

# 2. 验证数据库表已创建
python -c "
import sqlite3
conn = sqlite3.connect('data/jobs.db')
cur = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
print('表:', [r[0] for r in cur.fetchall()])
conn.close()
"

# 3. 首次全量采集（遍历全部 488 家公司，耗时较长，建议后台运行）
nohup python -c "from company_crawler import CompanyCrawler; CompanyCrawler().run_initial_crawl()" >> /var/log/job_crawler_initial.log 2>&1 &

# 4. 查看采集进度
tail -f /var/log/job_crawler_initial.log

# 5. 采集完成后验证总数据库统计
python -c "
from job_db import get_stats
print(get_stats())
"
```

**预期结果**：
- `jobs.db` 文件存在于 `data/` 目录
- `get_stats()` 返回总岗位数 > 0、在招岗位数 > 0
- 校招用户执行 `main.py single <user_id>` 能从总库匹配到岗位

> ⚠️ **首次全量采集注意事项**：
> - 488 家公司全量扫描预计耗时 30-60 分钟（受 Tavily 速率限制）
> - 采集过程中 AI 检视会消耗 DeepSeek API 配额
> - 若中途中断，可重新执行 `run_initial_crawl()`，已入库的岗位不会重复（dedup_hash 去重）

---

## 3. 服务器同步核心原则（必读）

> ⚠️ **第一性原则：本地代码修改 ≠ 服务器生效。所有改动必须同步到生产服务器并重启服务，用户才能看到变化。**

### 3.1 为什么必须同步到服务器

本项目采用**单机部署架构**，所有用户请求和定时任务都运行在阿里云轻量应用服务器上：

| 项目 | 值 |
|------|-----|
| 服务器 | 阿里云轻量应用服务器（马来西亚·吉隆坡） |
| 公网 IP | `47.250.216.165` |
| 域名 | `zhaopin-helper.xyz` |
| 应用路径 | `/opt/job_assistant` |
| 服务进程 | `job-callback`（systemd 管理，监听 `127.0.0.1:8080`） |
| 代码来源 | 本地开发机直接 `scp` 上传（服务器 git 仓库无远程 origin） |

**常见误区**：
- ❌ 在本地改完代码就以为用户能看到效果 → 服务跑的是服务器上的旧代码
- ❌ 只改 collector.py 不重启服务 → Python 进程加载的是旧字节码
- ❌ 只在本地测试通过就交付 → 生产环境可能因依赖/数据不同而异常

**正确流程**：本地修改 → 本地测试 → `scp` 上传服务器 → 语法检查 → 重启服务 → 健康检查 → 生产验证

### 3.2 SSH 连接方式（通过 HTTP 代理 CONNECT 隧道）

本地开发机通过 TRAE 环境的 HTTP 代理（`127.0.0.1:18080`）建立 SSH 隧道连接服务器：

```bash
# ~/.ssh/config
Host prod
    HostName 47.250.216.165
    User admin
    Port 22
    IdentityFile ~/.ssh/id_ed25519
    ProxyCommand nc -X connect -x 127.0.0.1:18080 %h %p
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

公钥需预先部署到服务器 `~/.ssh/authorized_keys`。

### 3.3 验证同步是否生效

每次部署后必须执行：

```bash
# 1. 确认服务已加载新代码（看启动时间）
ssh prod "sudo systemctl status job-callback | head -5"

# 2. 健康检查
ssh prod "curl -s http://localhost:8080/health"

# 3. 验证具体修改已生效（以领英过滤为例）
ssh prod "cd /opt/job_assistant && venv/bin/python3 -c '
from collector import _is_allowed_campus_source
assert _is_allowed_campus_source(\"https://www.linkedin.com/jobs/1\") == False
print(\"过滤逻辑已生效\")
'"
```

---

## 4. 更新部署 SOP（标准流程）

> 这是日常迭代的标准部署流程，每次代码更新后执行。
> 注意：服务器 git 仓库无远程 origin，使用 `scp` 上传而非 `git pull`。

在**本地开发机**执行（假设本地代码已修改并通过测试）：

```bash
# === 本地侧 ===

# 1. 上传修改的文件到服务器（按需指定文件）
scp /workspace/job_assistant/collector.py prod:/opt/job_assistant/
# 如需上传多个文件：
# scp collector.py config.py scorer.py job_db.py company_crawler.py user_matcher.py campus_companies.py prod:/opt/job_assistant/

# 若新增了总数据库相关文件，需一并上传：
# scp job_db.py company_crawler.py user_matcher.py campus_companies.py prod:/opt/job_assistant/

# === 服务器侧 ===
ssh prod << 'EOF'
cd /opt/job_assistant

# 2. 清理缓存
sudo find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
sudo find . -name "*.pyc" -delete 2>/dev/null

# 3. 语法检查（必须通过才能继续）
venv/bin/python3 -m py_compile collector.py && echo "语法 OK" || { echo "语法错误，终止部署"; exit 1; }

# 4. （可选）清理坏数据 — 按需执行
# sudo venv/bin/python3 -c "
# import json
# with open('data/users.json', 'r') as f:
#     users = json.load(f)
# # 按需删除指定用户
# for uid in list(users.keys()):
#     if uid in ('test_001',):
#         del users[uid]
# with open('data/users.json', 'w') as f:
#     json.dump(users, f, ensure_ascii=False, indent=2)
# print('清理后用户:', list(users.keys()))
# "

# 5. 重启服务（使新代码生效）
sudo systemctl restart job-callback
sleep 3

# 6. 健康检查
curl -s http://localhost:8080/health
EOF
```

**预期输出**：
```json
{"status": "ok", "uptime_seconds": 3, "service": "job-callback"}
```

**部署 Checklist**（每次必须逐项确认）：
- [ ] 本地代码已通过 `py_compile` 和功能测试
- [ ] `scp` 上传成功（检查文件大小/时间戳）
- [ ] 服务器 `py_compile` 通过
- [ ] `systemctl restart job-callback` 执行完成
- [ ] `/health` 返回 `status: ok`
- [ ] 生产环境验证修改生效（如领英过滤等）
- [ ] 若涉及总数据库变更：`jobs.db` 存在且 `get_stats()` 正常

---

## 5. 验证流程

### 5.1 部署后验证

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

### 5.2 功能验证（91402 修复验证）

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

### 5.3 端到端验证

1. **飞书回调**：在飞书中打开应用，检查 `users.json` 是否新增用户
2. **多维表格**：确认用户专属多维表格已创建，字段完整
3. **每日任务**：`python main.py single <user_id>`，确认岗位写入飞书表格
4. **飞书消息推送**：确认用户收到飞书日报卡片消息

---

## 6. 运维监控

### 6.1 日志查看

```bash
# 回调服务日志
sudo journalctl -u job-callback -n 100 -f

# 每日任务日志
tail -f /var/log/job_assistant.log

# Nginx 日志
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 6.2 健康检查

```bash
# 手动检查
curl -s http://localhost:8080/health

# 可配置监控（如 UptimeRobot）定时访问
https://zhaopin-helper.xyz/health
```

### 6.3 常用排查命令

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

## 7. 回滚 SOP

### 7.1 代码回滚

```bash
cd /opt/job_assistant
git log --oneline -10          # 查看提交历史
git checkout <commit_hash>     # 回滚到指定提交
sudo systemctl restart job-callback
curl -s http://localhost:8080/health
```

### 7.2 服务紧急降级

若飞书 API 大面积故障，可临时停止定时任务：

```bash
# 暂停 cron 任务
crontab -e  # 注释掉 daily 任务行

# 回调服务保持运行（不影响已安装用户查看数据）
```

---

## 8. 数据备份

### 8.1 备份脚本

```bash
#!/bin/bash
# /opt/job_assistant/backup.sh
BACKUP_DIR="/opt/job_assistant/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

cp /opt/job_assistant/data/users.json $BACKUP_DIR/users_$DATE.json
cp -r /opt/job_assistant/data/hashes $BACKUP_DIR/hashes_$DATE
cp /opt/job_assistant/data/jobs.db $BACKUP_DIR/jobs_$DATE.db

# 保留最近 30 天
find $BACKUP_DIR -name "*.json" -mtime +30 -delete
find $BACKUP_DIR -name "*.db" -mtime +30 -delete
```

```bash
# 添加到 cron
0 3 * * * /opt/job_assistant/backup.sh
```

### 8.2 恢复

```bash
cp /opt/job_assistant/backups/users_YYYYMMDD_HHMMSS.json /opt/job_assistant/data/users.json
cp /opt/job_assistant/backups/jobs_YYYYMMDD_HHMMSS.db /opt/job_assistant/data/jobs.db
sudo systemctl restart job-callback
```
