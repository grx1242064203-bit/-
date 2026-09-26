# 12. 管理员运营 SOP

> 本文档面向运营人员，指导如何为付费客户完成开户、配置偏好、验证服务。
>
> **重要变更**：已移除 WxPusher 微信绑定步骤，主推送渠道统一为飞书消息。
> 客户通过飞书应用内的自助配置页面完成求职偏好设置。

---

## 一、客户开户完整流程

```
客户付费 → 发送安装链接 → 客户安装飞书应用 → 客户自助配置求职偏好 → 触发测试 → 交付
```

---

## 二、详细步骤

### 步骤 1：确认客户付费

- 客户通过小红书/微信完成付费
- 记录客户姓名、联系方式、购买套餐、到期日期

### 步骤 2：发送飞书应用安装链接

向客户发送飞书应用安装链接，并附上简要说明：

```
您好！感谢购买招聘情报助手。
请按以下步骤操作：
1. 点击下方链接安装飞书应用
2. 安装后请"打开应用一次"（系统会自动为您创建岗位库）
3. 打开应用后，点击飞书消息中的配置链接，填写求职偏好（支持简历智能解析）
4. 保存偏好后系统会立即为您采集第一批岗位

安装链接：[飞书应用安装链接]
```

### 步骤 3：确认客户已安装并获取 user_id

客户安装并打开应用后，飞书会触发回调，系统自动：
- 创建用户记录（user_id = `{tenant_key}_{open_id}`）
- 创建「招聘情报库」多维表格
- 创建「岗位数据库」和「已关闭岗位」两张表
- 创建字段
- 将多维表格所有权转移给客户
- 发送飞书消息，附带自助配置页面链接

**验证用户已创建**：

```bash
cd /opt/job_assistant
cat data/users.json | python3 -c "import json,sys; d=json.load(sys.stdin); print([k for k in d])"
```

找到新创建的 user_id（通常是最新的那条记录）。

> ⚠️ 如果用户记录的 `feishu_base_token` 为空，说明 onboarding 失败，需排查日志：
> ```bash
> sudo journalctl -u job-callback -n 100 --no-pager | grep -i error
> ```

### 步骤 4：确认客户已配置求职偏好

客户通过飞书消息中的链接打开自助配置页面，可：
- 选择求职角色（实习/校招/社招）
- 粘贴简历文本，AI 自动解析提取学校、学历、专业、技能等
- 手动填写/调整目标岗位方向、专业、学历、技能、目标公司、目标城市
- 保存后系统立即触发首次采集

**验证客户已配置**：

```bash
cd /opt/job_assistant
venv/bin/python -c "
from models import UserStore
store = UserStore()
u = store.get('<user_id>')
if u:
    p = u.profile
    print(f'role={p.role}, major={p.major}, directions={list(p.direction_keywords.keys())}')
"
```

如果客户未配置或配置不完整，`direction_keywords` 为空，则无法采集到匹配岗位。

> ⚠️ 如需手动为客户配置偏好，可编辑 `data/users.json`（编辑前备份，编辑后重启服务）。

### 步骤 5：触发测试运行

```bash
cd /opt/job_assistant
venv/bin/python main.py single <user_id>
```

**预期结果**：
- 日志显示"写入 N 条新岗位"
- 客户的飞书多维表格中出现岗位记录
- 客户收到飞书消息通知（岗位日报卡片）

### 步骤 6：交付确认

向客户发送确认消息：

```
您好！您的招聘情报助手已配置完成。
✅ 已为您创建专属岗位库（飞书云空间 → 招聘情报库）
✅ 已配置您的求职偏好
✅ 已启动岗位采集

每天早上 9:00 您将收到岗位日报推送（飞书消息）。
如有问题请随时联系。

使用手册：[客户使用手册链接]
```

---

## 三、日常运维

### 3.1 每日检查

```bash
# 检查服务状态
sudo systemctl status job-callback

# 检查每日任务日志
tail -n 50 /var/log/job_assistant.log

# 检查健康状态
curl -s http://localhost:8080/health
```

### 3.2 手动触发单用户任务

```bash
cd /opt/job_assistant
venv/bin/python main.py single <user_id>
```

### 3.3 更新客户偏好

1. 编辑 `data/users.json` 中对应用户的 `profile`
2. `sudo systemctl restart job-callback`
3. 手动触发一次验证：`venv/bin/python main.py single <user_id>`

### 3.4 客户退订/到期处理

```bash
# 删除用户（会保留飞书多维表格，仅停止服务）
cd /opt/job_assistant
venv/bin/python -c "
from models import UserStore
store = UserStore()
store.delete('<user_id>')
print('已删除用户 <user_id>')
"
```

### 3.5 查看用户列表

```bash
cd /opt/job_assistant
venv/bin/python -c "
from models import UserStore
store = UserStore()
for u in store.list_active():
    print(f'{u.id} | plan={u.plan} | expire={u.expire_date} | last_run={u.last_run_at}')
"
```

---

## 四、故障排查

### 4.1 客户安装后未创建多维表格

```bash
# 查看回调日志
sudo journalctl -u job-callback -n 100 --no-pager

# 常见原因：
# 1. 飞书应用权限不足（需要 drive:drive）
# 2. 网络问题
# 3. 应用未配置事件订阅回调地址
```

### 4.2 每日任务无新岗位

```bash
# 手动运行查看详细日志
cd /opt/job_assistant
venv/bin/python main.py single <user_id> 2>&1 | tail -50

# 常见原因：
# 1. 搜索 API 配额耗尽（检查 TAVILY_API_KEY 额度）
# 2. 用户 direction_keywords 为空（需配置偏好）
# 3. 所有岗位已推送过（去重）
```

### 4.3 飞书消息推送失败

```bash
# 检查飞书凭证配置
grep FEISHU /opt/job_assistant/.env

# 检查用户是否有 feishu_open_id
grep -A2 '"feishu_open_id"' data/users.json

# 常见原因：
# 1. FEISHU_APP_SECRET 错误或过期
# 2. 飞书应用缺少消息发送权限（im:message）
# 3. 应用未发布或用户未安装
```

### 4.4 飞书写入失败（91402）

```bash
# 执行 token 迁移
cd /opt/job_assistant
venv/bin/python main.py migrate-tokens

# 如果仍失败，查看具体错误
venv/bin/python main.py single <user_id> 2>&1 | grep -i error
```

---

## 五、数据备份

```bash
# 手动备份
cp /opt/job_assistant/data/users.json /opt/job_assistant/backups/users_$(date +%Y%m%d).json

# 恢复备份
cp /opt/job_assistant/backups/users_YYYYMMDD.json /opt/job_assistant/data/users.json
sudo systemctl restart job-callback
```

---

## 六、套餐与到期管理

| 套餐 | 价格 | 有效期 | 到期日期设置 |
|------|------|--------|-------------|
| 体验版 | 9.9 元 | 3 天 | 当天 +3 天 |
| 秋招版 | 199 元 | 9-11 月 | 2026-11-30 |
| 春招版 | 149 元 | 2-4 月 | 2026-04-30 |
| 全年版 | 399 元 | 1 年 | 当天 +1 年 |

到期后 `list_active()` 不再返回该用户，每日任务自动跳过。
