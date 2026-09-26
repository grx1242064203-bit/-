# 04. 开发规范与 Git 工作流

## 1. 开发环境搭建

### 1.1 前置要求

- Python 3.10+（生产环境为 3.8，开发时注意语法兼容性，避免使用 3.10+ 独有语法如 `match-case`）
- Git
- 飞书开发者账号
- WxPusher 账号
- Tavily 或 SerpAPI API Key

### 1.2 本地开发步骤

```bash
# 1. 克隆代码
git clone <repo_url>
cd job_assistant

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 填入真实凭证

# 5. 语法检查
python3 -m py_compile *.py && echo "语法 OK"

# 6. 启动回调服务（本地）
python callback_server.py

# 7. 测试单用户每日任务
python main.py single <user_id>
```

### 1.3 内网穿透（本地接收飞书回调）

```bash
# 方案一：ngrok
ngrok http 8080

# 方案二：cloudflared
cloudflared tunnel --url http://localhost:8080
```

将生成的 HTTPS URL 填入飞书事件订阅的请求地址。

---

## 2. 代码规范

### 2.1 Python 编码规范

- 遵循 PEP 8
- 缩进：4 空格
- 行宽：120 字符（超出可断行）
- 编码：UTF-8，中文注释和字符串直接使用 UTF-8

### 2.2 命名约定

| 类型 | 规范 | 示例 |
|------|------|------|
| 模块/文件 | snake_case | `feishu_client.py` |
| 类 | PascalCase | `FeishuClient`, `UserStore` |
| 函数/方法 | snake_case | `create_bitable`, `_get_existing_hashes` |
| 常量 | UPPER_SNAKE_CASE | `FEISHU_HOST`, `MAX_BODY_SIZE` |
| 私有成员 | 前缀下划线 | `_token`, `_file_lock` |

### 2.3 注释规范

- **模块级 docstring**：每个文件顶部必须有模块说明，包含职责、设计原则
- **类 docstring**：说明类的职责和关键设计
- **函数 docstring**：说明功能、参数、返回值
- **复杂逻辑**：行内注释解释"为什么"而非"是什么"

示例：
```python
"""
飞书 API 客户端。

设计原则(对抗性审查后):
1. tenant_access_token 缓存 + 自动刷新(2小时过期,提前5分钟刷新)
2. 所有写操作带重试(指数退避),应对限流(5次/秒)
"""
```

### 2.4 错误处理规范

- **不静默吞异常**：`except Exception` 必须记录日志
- **降级优先**：单用户失败不影响其他用户，推送失败不影响数据
- **重试策略**：网络请求用指数退避，区分临时错误和永久错误
- **错误信息**：包含上下文（user_id、操作、原始响应），便于排查

### 2.5 配置规范

- **禁止硬编码**：所有敏感信息和可变参数走环境变量
- **配置集中**：所有配置项在 `config.py` 的 `Settings` 中定义
- **默认值**：非必填项提供合理默认值

### 2.6 日志规范

```python
import logging
logger = logging.getLogger(__name__)

# 正确：包含上下文
logger.info(f"用户 {user.id} 写入 {len(new_jobs)} 条新岗位")
logger.error(f"飞书 API 失败 user={user.id} code={code}")

# 错误：无上下文
logger.info("写入成功")
```

---

## 3. Git 工作流

### 3.1 分支策略

| 分支 | 用途 | 生命周期 |
|------|------|----------|
| `main` / `master` | 生产稳定版本 | 长期 |
| `trae/agent-*` | AI Agent 开发分支 | 功能开发期间 |
| `feature/*` | 新功能开发 | 合并后删除 |
| `fix/*` | 问题修复 | 合并后删除 |
| `hotfix/*` | 生产紧急修复 | 合并后删除 |

### 3.2 提交规范（Conventional Commits）

格式：`<type>(<scope>): <subject>`

| type | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修复 bug |
| `refactor` | 重构（不改变功能） |
| `perf` | 性能优化 |
| `docs` | 文档更新 |
| `test` | 测试相关 |
| `chore` | 构建/工具/依赖 |
| `style` | 代码格式（不影响逻辑） |

示例：
```
fix(feishu_client): 修复 wiki node_token 导致 91402 NOTEXIST
feat(onboarding): 创建多维表格后验证 token 有效性
docs: 新增架构决策记录 ADR-001
```

### 3.3 开发流程

```
1. 从 main 创建分支
   git checkout main && git pull
   git checkout -b feature/xxx

2. 开发 + 自测
   # 修改代码
   python3 -m py_compile *.py   # 语法检查
   python main.py single u1     # 功能测试

3. 提交
   git add <files>
   git commit -m "feat(scope): 描述"

4. 推送 + 合并
   git push origin feature/xxx
   # 创建 PR，审查后合并到 main

5. 部署（见 05-部署运维SOP）
```

### 3.4 提交前检查清单

- [ ] `python3 -m py_compile *.py` 语法检查通过
- [ ] 没有遗留的 `print()` 调试语句
- [ ] 没有硬编码的密钥或 token
- [ ] 新增/修改的配置项已同步到 `.env.example`
- [ ] 涉及架构/接口变更已同步更新 `docs/`
- [ ] 敏感信息未提交到 Git

---

## 4. 变更管理

### 4.1 配置变更

修改 `config.py` 或新增环境变量时：
1. 在 `Settings` 中添加字段
2. 更新 `.env.example`
3. 更新 `docs/03-接口规范与配置说明.md`

### 4.2 字段变更（schema.py）

修改 `JOB_FIELDS` 时：
1. 评估对存量用户多维表格的影响（已有字段不会自动变更）
2. 如需存量用户生效，编写迁移脚本
3. 更新 `docs/02-核心模块与数据模型.md`

### 4.3 接口变更

修改飞书/WxPusher API 调用时：
1. 确认飞书开放平台文档
2. 更新 `docs/03-接口规范与配置说明.md`
3. 如涉及回调结构变更，同步更新 `onboarding.py` 的解析逻辑

---

## 5. 安全规范

### 5.1 凭证管理

- `.env` 文件**必须**加入 `.gitignore`
- 生产环境凭证通过服务器环境变量或受保护的 `.env` 文件注入
- `.env.example` 只包含占位符，不含真实凭证

### 5.2 日志安全

- 日志中**不得**打印完整的 `app_secret`、`api_key`、`token`
- 打印敏感信息时只显示前几位：`app_id[:8]...`

### 5.3 输入校验

- 回调请求体大小限制（已实现 1MB）
- 外部输入（如 user_id）不直接用于文件路径拼接，防止路径遍历
- 搜索关键词不直接拼接到 shell 命令
