# 05. 部署运维 SOP

> 本文档面向运维/部署工程师，指导如何从零部署、日常运维、故障排查校招情报助手。
> 系统为**校招专属**，采用中心化数据流水线 + 多用户分发架构。

---

## 1. 部署架构总览

```
互联网用户
    │
    ▼ HTTPS :443
┌─────────────────────────────────────────────────┐
│  Nginx (反向代理 + SSL 终结)                      │
│  server_name: zhaopin-helper.xyz                 │
└───────────────────┬─────────────────────────────┘
                    │ proxy_pass http://127.0.0.1:8080
                    ▼
┌─────────────────────────────────────────────────┐
│  callback_server.py (systemd: job-callback)       │
│  - 监听 127.0.0.1:8080                            │
│  - 接收飞书事件回调 (app_open / app_install)       │
│  - 提供用户配置页面 API (/api/profile 等)         │
└─────────────────────────────────────────────────┘

定时任务 (cron):
  0 9 * * *    main.py daily            → 数据同步 + 所有用户每日任务
  30 9 * * 1   main.py weekly-ranking   → 每周校招投递热度榜
```

### 1.1 服务器信息

| 项目 | 值 |
|------|-----|
| 服务器 | 阿里云轻量应用服务器（马来西亚·吉隆坡） |
| 公网 IP | `47.250.216.165` |
| 域名 | `zhaopin-helper.xyz` |
| 应用路径 | `/opt/job_assistant` |
| 服务进程 | `job-callback`（systemd 管理） |
| 代码来源 | 本地开发机 `scp` 上传（服务器 git 无远程 origin） |

### 1.2 数据流（校招专属）

```
飞书秋招汇总表(10150条)
    │
    ▼ feishu_source.py  (同步+归一化)
announcements 表(原始招聘链接,后台中间表)
    │
    ▼ fetch_announcements.py  (阶段一: Playwright 并发抓取)
fetch_results.jsonl  (正文文字 + 图片URL, append-only)
    │
    ▼ analyze_daemon.py  (阶段二: LLM 分析, tail -f)
jobs 表(具体岗位,25+ 维度) + companies 表(公司元数据)
    │
    ▼ user_matcher.py  (规则预筛 + AI 评分)
    │
    ▼ daily_runner.py  (写入飞书表 + 日报 + 推送)
用户飞书多维表格 + 飞书卡片 + 微信推送
```

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

# 安装 Playwright + Chromium（阶段一抓取微信公告用）
pip install playwright
playwright install chromium
```

### 2.3 配置环境变量

```bash
cat > /opt/job_assistant/.env << 'EOF'
# 飞书应用凭证(open.feishu.cn 创建商店应用后获取)
FEISHU_APP_ID=cli_xxxxxxxx
FEISHU_APP_SECRET=xxxxxxxx
FEISHU_VERIFICATION_TOKEN=xxxxxxxx
# FEISHU_ENCRYPT_KEY=xxxxxxxx

# LLM 配置(DeepSeek — 简历解析 + 岗位拆分 + JD 分析)
DEEPSEEK_API_KEY=sk-xxxxxxxx

# WxPusher(可选辅助通道,主推送走飞书)
WXPUSHER_APP_TOKEN=AT_xxxxxxxx
ADMIN_WXPUSHER_UID=UID_xxxxxxxx

# 数据存储目录
DATA_DIR=/opt/job_assistant/data

# 服务域名(生成客户配置页链接)
SERVICE_BASE_URL=https://zhaopin-helper.xyz

# 数据源告警接收人(可选,不配置则发给所有用户)
# ALERT_OPEN_ID=ou_xxxxxxxx
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

    client_max_body_size 20M;  # 简历上传

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
# 每日 9:00 执行(内含飞书同步 + AI 分析 + 多用户分发)
0 9 * * * cd /opt/job_assistant && /opt/job_assistant/venv/bin/python main.py daily >> /var/log/job_assistant.log 2>&1
# 每周一 9:30 校招投递热度榜
30 9 * * 1 cd /opt/job_assistant && /opt/job_assistant/venv/bin/python main.py weekly-ranking >> /var/log/job_assistant_weekly.log 2>&1
```

> **说明**：`main.py daily` 内部先执行 `run_sync_and_analyze()`（飞书表同步 + AI 岗位分析），再遍历活跃用户分发岗位。无需单独的采集 cron。

### 2.8 数据库初始化（首次部署必做）

```bash
cd /opt/job_assistant
source venv/bin/activate

# 1. 初始化三表结构(companies + announcements + jobs)
python3 -c "import job_db; job_db.init_db(); print('数据库初始化完成')"

# 2. 验证表结构
python3 -c "
import sqlite3
conn = sqlite3.connect('data/jobs.db')
print('表:', [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()])
conn.close()
"

# 3. 首次全量同步飞书表 + AI 分析(耗时较长,建议后台运行)
nohup python3 main.py sync >> /var/log/job_sync_initial.log 2>&1 &

# 4. 查看同步进度
tail -f /var/log/job_sync_initial.log

# 5. 验证统计
python3 -c "from job_db import get_stats, get_announcement_stats; print('岗位:', get_stats()); print('公告:', get_announcement_stats())"
```

**预期结果**：
- `jobs.db` 包含 `companies`、`announcements`、`jobs` 三张表
- `get_stats()` 返回岗位数 > 0（随 AI 分析进度增长）
- 校招用户执行 `main.py single <user_id>` 能匹配到岗位

---

## 3. 代码同步核心原则（必读）

> ⚠️ **第一性原则：本地代码修改 ≠ 服务器生效。所有改动必须 scp 上传并重启服务，用户才能看到变化。**

### 3.1 SSH 连接方式

本地开发机通过 TRAE 环境的 HTTP 代理（`127.0.0.1:18080`）建立 SSH 隧道：

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

### 3.2 标准更新部署流程

在**本地开发机**执行：

```bash
# === 本地侧：上传修改的文件 ===
scp /workspace/job_assistant/<修改的文件>.py prod:/opt/job_assistant/

# === 服务器侧：验证 + 重启 ===
ssh prod << 'EOF'
cd /opt/job_assistant

# 清理缓存
sudo find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
sudo find . -name "*.pyc" -delete 2>/dev/null

# 语法检查(必须通过)
venv/bin/python3 -m py_compile <修改的文件>.py && echo "语法 OK" || { echo "语法错误,终止"; exit 1; }

# 重启服务
sudo systemctl restart job-callback
sleep 3

# 健康检查
curl -s http://localhost:8080/health
EOF
```

**部署 Checklist**：
- [ ] 本地代码通过 `py_compile` 和功能测试
- [ ] `scp` 上传成功
- [ ] 服务器 `py_compile` 通过
- [ ] `systemctl restart job-callback` 执行完成
- [ ] `/health` 返回 `status: ok`

---

## 4. 数据流水线管理

系统采用**两阶段流水线**，每日由 `main.py daily` 自动触发。也可手动执行各阶段。

### 4.1 每日自动流程（main.py daily）

```bash
python3 main.py daily
```

内部执行顺序：
1. `run_sync_and_analyze()` — 飞书表同步 + AI 岗位分析（所有用户共享）
2. 遍历活跃用户 → `DailyRunner.run()` — 匹配 + 写入飞书 + 日报 + 推送

### 4.2 手动执行数据同步

```bash
# 仅同步飞书表 + AI 分析(不分发用户)
python3 main.py sync
```

### 4.3 手动执行两阶段流水线（调试用）

```bash
# 阶段一：并发抓取公告正文(Playwright)
python3 fetch_announcements.py --workers 4 --limit 1000

# 阶段二：LLM 分析(一次性分析全部已抓取记录)
python3 analyze_announcements.py

# 或两阶段并行(推荐)
python3 run_parallel.py
```

### 4.4 流水线状态查看

```bash
python3 -c "
from job_db import get_stats, get_announcement_stats
print('=== 岗位表(jobs) ===')
print(get_stats())
print('=== 公告表(announcements) ===')
print(get_announcement_stats())
"
```

`announcements.analysis_status` 枚举：

| 值 | 含义 | 处理方式 |
|----|------|---------|
| `success` | 成功拆分出岗位 | - |
| `fetch_blocked` | 微信反爬拦截 | 换 IP / 降速重试 |
| `fetch_failed` | 抓取失败 | 重试 |
| `content_invalid` | 抓到无效正文 | 改进抓取策略 |
| `llm_parse_empty` | LLM 未拆出岗位 | 重试 + 优化 prompt |
| `not_current_grade` | 非本届校招 | 过滤，不重试 |

### 4.5 监控面板

```bash
python3 monitor_panel.py   # 启动 Web 监控面板,端口 8765
```

---

## 5. 验证流程

### 5.1 服务健康检查

```bash
# 服务状态
sudo systemctl status job-callback

# 健康检查
curl -s http://localhost:8080/health

# 公网访问
curl -s https://zhaopin-helper.xyz/health
```

预期输出：
```json
{"status": "ok", "uptime_seconds": 3, "service": "job-callback"}
```

### 5.2 端到端验证

1. **飞书回调**：在飞书中打开应用，检查 `data/users.json` 是否新增用户
2. **多维表格**：确认用户专属多维表格已创建，字段完整
3. **单用户任务**：`python3 main.py single <user_id>`，确认岗位写入飞书表格
4. **飞书推送**：确认用户收到飞书日报卡片消息

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

### 6.2 常用排查命令

```bash
# 服务重启
sudo systemctl restart job-callback

# 查看最近错误
sudo journalctl -u job-callback -n 50 --no-pager | grep -i error

# 手动执行单用户任务(调试)
cd /opt/job_assistant && venv/bin/python main.py single <user_id>

# 查看总数据库统计
venv/bin/python -c "from job_db import get_stats; print(get_stats())"
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
crontab -e  # 注释掉 daily 任务行
# 回调服务保持运行(不影响已安装用户查看数据)
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
# 添加到 cron(每日凌晨 3 点)
0 3 * * * /opt/job_assistant/backup.sh
```

### 8.2 恢复

```bash
cp /opt/job_assistant/backups/users_YYYYMMDD_HHMMSS.json /opt/job_assistant/data/users.json
cp /opt/job_assistant/backups/jobs_YYYYMMDD_HHMMSS.db /opt/job_assistant/data/jobs.db
sudo systemctl restart job-callback
```
