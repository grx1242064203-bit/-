# M1 计划：求职搭子桌面工作台 MVP

spec: docs/staging/specs/2026-10-03-desktop-workbench.md
milestone: M1 (see docs/ROADMAP.md)

goal: 用户能注册登录、浏览全部岗位、上传简历自动评分、看到推荐岗位、记录投递

## 任务清单

- [ ] T1: 项目脚手架初始化
goal: 创建 job_workbench（桌面端）+ job_api（云端 API）两个项目骨架，含 README/CHANGELOG/.gitignore/Makefile
files: job_workbench/, job_api/, README.md, CHANGELOG.md, .gitignore, Makefile
acceptance: `make help` 列出所有可用命令；两个目录结构存在且可运行
spec: specs/2026-10-03-desktop-workbench.md#八目录结构

- [ ] T2: 云端 API 骨架
goal: FastAPI 入口 + 配置加载 + 健康检查 + CORS
files: job_api/main.py, job_api/config.py, job_api/requirements.txt
acceptance: `make serve-api` 后 `curl localhost:8000/health` 返回 200
spec: specs/2026-10-03-desktop-workbench.md#三接口契约

- [ ] T3: 云端认证模块
goal: 邮箱注册 + 验证码 + 登录 + JWT 签发/校验，含 rate limit
files: job_api/routers/auth.py, job_api/services/email_service.py, job_api/models/user.py, job_api/services/jwt_service.py
acceptance: pytest 跑通注册→验证→登录全流程，返回有效 token
spec: specs/2026-10-03-desktop-workbench.md#认证

- [ ] T4: 云端 LLM 代理
goal: /llm/parse-resume 接口，代理 DeepSeek 调用 resume_parser.py，含订阅校验 + 每日配额限流
files: job_api/routers/llm.py, job_api/services/llm_proxy.py, job_api/services/quota_service.py
acceptance: POST /llm/parse-resume 传入简历文本，返回 keywords + fit_directions；超额返回 429
spec: specs/2026-10-03-desktop-workbench.md#llm-代理

- [ ] T5: 云端岗位同步接口
goal: /sync/jobs 增量拉取接口，从 jobs.db 读取岗位数据返回
files: job_api/routers/sync.py, job_api/services/sync_service.py
acceptance: GET /sync/jobs?limit=500 返回 500 条岗位 + next_cursor
spec: specs/2026-10-03-desktop-workbench.md#数据同步

- [ ] T6: Tauri 桌面端脚手架
goal: Tauri 2 + React 18 + TypeScript + Tailwind + Zustand，含路由 + 暖橙色主题
files: job_workbench/src-tauri/, job_workbench/src/, job_workbench/package.json, job_workbench/tailwind.config.ts
acceptance: `make dev-app` 打开窗口，显示暖橙色主题的空白页面
spec: specs/2026-10-03-desktop-workbench.md#六技术栈

- [ ] T7: 桌面端 SQLite 层
goal: Rust 侧 db.rs，建表（user_config/jobs/resumes/applications/email_accounts/emails/schedules），含岗位 CRUD
files: job_workbench/src-tauri/src/db.rs, job_workbench/src-tauri/migrations/001_init.sql
acceptance: Rust 单元测试插入岗位+查询成功
spec: specs/2026-10-03-desktop-workbench.md#四本地数据库-schemasqlite

- [ ] T8: 桌面端认证 UI + API 客户端
goal: 登录/注册页面 + 邮箱验证码输入 + token 存储 + API client 基类
files: job_workbench/src/pages/Login.tsx, job_workbench/src/pages/Register.tsx, job_workbench/src/api/client.ts, job_workbench/src/stores/authStore.ts
acceptance: 桌面端能完成注册→验证→登录，token 存入本地，跳转首页
spec: specs/2026-10-03-desktop-workbench.md#认证

- [ ] T9: 桌面端岗位同步
goal: sync.rs 从云端 /sync/jobs 拉取增量数据写入本地 SQLite，含进度 + 失败重试
files: job_workbench/src-tauri/src/sync.rs, job_workbench/src/stores/syncStore.ts
acceptance: 启动后自动同步，本地 SQLite 有 500+ 岗位，日志显示同步成功
spec: specs/2026-10-03-desktop-workbench.md#数据同步

- [ ] T10: 桌面端岗位列表首页
goal: Jobs.tsx 全部岗位列表（按更新时间倒序）+ 筛选栏（城市/学历/管培/分类/公司）+ 搜索 + JobCard 组件
files: job_workbench/src/pages/Jobs.tsx, job_workbench/src/components/JobCard.tsx, job_workbench/src/stores/jobsStore.ts
acceptance: 能浏览全部岗位，筛选"上海+本科+管培" < 100ms
spec: specs/2026-10-03-desktop-workbench.md#首页设计核心差异化

- [ ] T11: Python sidecar 评分引擎
goal: sidecar_server.py（stdin/stdout JSON-RPC）打包 scorer.py + 依赖，Tauri sidecar.rs 管理进程生命周期
files: job_workbench/python-sidecar/sidecar_server.py, job_workbench/src-tauri/src/sidecar.rs, job_workbench/python-sidecar/pyoxidizer.bzl
acceptance: sidecar 接收 1 个岗位 + 简历画像 JSON，返回 0-100 分 + 理由
spec: specs/2026-10-03-desktop-workbench.md#评分策略复用现有算法体系llm-仅解析简历

- [ ] T12: 桌面端简历上传 + LLM 解析
goal: Resume.tsx 上传 PDF/图片→提取文本→调云端 /llm/parse-resume→存本地 SQLite，支持用户编辑画像
files: job_workbench/src/pages/Resume.tsx, job_workbench/src/api/llm.ts, job_workbench/src/stores/resumeStore.ts
acceptance: 上传 PDF 简历 < 15s 返回结构化画像，存入本地，首页自动切换推荐视图
spec: specs/2026-10-03-desktop-workbench.md#m1-包含

- [ ] T13: 桌面端评分 + 推荐视图
goal: 简历解析后触发 sidecar 全量评分，Jobs.tsx 增加推荐 Tab（🔥强烈推荐/✅推荐/➖可申请），评分缓存
files: job_workbench/src/pages/Jobs.tsx, job_workbench/src/components/MatchScore.tsx, job_workbench/src/stores/scoreStore.ts
acceptance: 简历解析后自动评分（秒级），推荐 Tab 显示 🔥强烈推荐+✅推荐 岗位
spec: specs/2026-10-03-desktop-workbench.md#推荐视图简历解析后自动启用

- [ ] T14: 桌面端投递记录 Kanban
goal: Applications.tsx Kanban 看板（draft/applied/test/interview/offer/rejected），手动添加 + 拖拽 + 关联岗位
files: job_workbench/src/pages/Applications.tsx, job_workbench/src/components/KanbanBoard.tsx, job_workbench/src/stores/appStore.ts
acceptance: 能添加投递记录，拖拽改变状态，关联到已有岗位
spec: specs/2026-10-03-desktop-workbench.md#m1-包含

## 并行组

- [parallel] T2, T6  （云端骨架 + 桌面端骨架，互不依赖）
- [parallel] T3, T4, T5  （认证/LLM代理/同步，依赖 T2 但互不依赖）
- [parallel] T11  （sidecar，仅依赖 T1 的项目结构）
- T7 依赖 T6
- T8 依赖 T3, T6
- T9 依赖 T5, T7
- T10 依赖 T7, T9
- T12 依赖 T4, T6
- T13 依赖 T10, T11, T12
- T14 依赖 T6

## 依赖链（关键路径）

T1 → T2 → T4 → T12 → T13（LLM 解析 + 评分推荐，核心卖点）
T1 → T6 → T7 → T9 → T10 → T13（数据 + 列表 + 评分，基建）
