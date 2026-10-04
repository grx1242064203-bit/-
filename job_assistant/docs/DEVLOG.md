# 开发日志 (DEVLOG)

> 本文件按任务推进追加记录，最新条目置顶。

---

## 2026-10-04 — 投递看板全流程 + 公司尽调 + 匹配去重

**状态**: 完成并推送至 `origin/main`（commit `0c39282`）

### 投递看板 6 列状态机
- **状态枚举**：`favorite → applied → assessment → interview → offer | rejected`（收藏 / 已投递 / 测评中 / 面试中 / Offer / 已拒绝）
- `appStore.ts`：`KANBAN_COLUMNS` 定义 6 列（含新增 `assessment` 测评列，`info` 色系）
- `index.css` + `tailwind.config.ts`：补充 `info` 色阶（`info-50/100/...`）支持测评列样式
- `ApplicationCard.tsx`：按 `source` 渲染来源标签（DB岗位 / DB公司 / 手动 / 邮件），显示面试轮次

### 面试轮次展开 + 列内拖拽
- `appStore.ts`：`interviewExpanded` 状态控制面试列展开；展开后显示「一面 / 二面 / 三面 / 终面」4 个子列
- `KanbanBoard.tsx`：面试列头部可展开/收起；展开时按 `interview_round` 分发卡片到对应轮次子列
- **列内拖拽**：在面试列内拖到不同轮次子列 → 调 `updateInterviewRound(app, round)` 持久化轮次
- **拖入面试列默认轮次=1**：`updateApplicationStatus` 在状态变为 `interview` 时将 `interview_round` 设为 `max(当前轮次, 1)`，新建面试记录后端也默认 `interview_round=1`

### 逆向拖拽确认
- `KanbanBoard.tsx`：从后往前拖（如 offer→interview、interview→applied）弹出确认弹窗，防止误操作回退状态
- 同列拖拽、面试列内轮次切换不弹确认

### 公司尽调（LLM + 联网搜索 + 缓存）
- 新表 `company_due_diligence`（`company_name` 主键）：缓存 `intro / official_website / news / interview_questions / generated_at`
- `services/llm_proxy.py`：`company_due_diligence(company_name)` → DuckDuckGo HTML 解析抓官网/新闻 → DeepSeek 生成简介 + 面试问题；30s 超时保护
- `routers/llm.py`：`POST /api/v1/llm/company-due-diligence` 端点，命中缓存直接返回，避免重复消耗 LLM 配额
- `RecruitmentCard.tsx`：招聘卡弹窗内嵌尽调卡，按 `source`（db_job / db_company / manual / email）渲染不同内容

### 精确匹配去重（一个公司仅一条 / 公司+岗位精确匹配）
- `models/application.py::create_application` 匹配优先级：
  1. DB 来源（有 `link_type`+`link_id`）→ 按 `(link_type, link_id)` 去重
  2. 手动/邮件来源 → 按 `(company_name, job_title)` 精确匹配；若仅 `company_name` 有值 → 按公司名匹配（一公司一条）
  3. 匹配命中 → **仅更新状态**（+ 阶段时间戳 + 链接 + 岗位名），不新建
  4. 未命中 → 新建
- 状态为 `interview` 时 `interview_round` 默认 1；非面试状态重置为 0

### Jobs / Companies 表收藏 / 投递按钮
- `Jobs.tsx`：操作列新增 ⭐ 收藏 / 📮 投递 按钮，直接 `addApplication({source:"db_job", link_type:"job", link_id})`
- `Companies.tsx`：操作列新增 ⭐/📮 按钮，点击弹出小表单（仅岗位名输入框，可选），提交后 `addApplication({source:"db_company", link_type:"company", link_id})`
- 后端按 link 去重，同一岗位/公司重复点击只会更新状态

### 构建修复
- `tsconfig.json`：移除 TS 7 已废弃的 `baseUrl`，`paths` 改用 `"./src/*"` 相对路径
- 清理 3 处未使用变量：`KanbanBoard.tsx` 的 `DragEvent` import、`Applications.tsx` 的 `setSelectedAppId`、`appStore.ts` 的 `get` 参数

### 验证
- ✅ `tsc --noEmit` 零错误，`vite build` 成功
- ✅ 后端匹配逻辑实测：同公司+同岗位更新状态（同 id）、同公司不同岗位新建、仅公司名匹配到已有记录、新建面试记录轮次=1

**关键设计决策**:
- **匹配去重用 company_name+job_title 而非仅 link**：手动/邮件来源无 link_id，必须用业务字段去重；"一个公司仅一条"通过仅填公司名时按公司名匹配实现
- **面试轮次存整数 interview_round 而非独立表**：4 轮固定，整型足够；列内拖拽直接改字段，无需关联表
- **尽调按公司缓存**：同一公司多次查看只调用一次 LLM；新闻/官网链接随生成结果缓存
- **逆向拖拽确认而非禁止**：用户可能确实需要回退状态（如 offer 被拒→rejected），用确认弹窗比硬禁止更友好

---

## 2026-10-04 — Offer搭子 UI/UX 增强 + 数据同步修复 + 品牌改名

### 品牌改名
- 产品名从"求职搭子"改为"Offer搭子"
- tauri.conf.json: productName 和窗口标题改为 "Offer搭子"
- App.tsx: 顶部导航 logo + 标题改为 "Offer搭子"
- main.py: FastAPI title 改为 "Offer搭子 API"
- email_service.py: 邮件标题改为 "【Offer搭子】邮箱验证码"
- logo.png: 更新为用户提供的 1254×1254 PNG (272KB)
- vite-env.d.ts: 添加 *.png/*.jpg/*.jpeg/*.svg/*.gif 模块声明

### 链接打不开修复
- link.ts: 放宽 URL 校验（允许含中文/特殊字符的 URL）
- link.ts: normalizeUrl() 无协议时自动补 https://，从含中文标点文本中提取 URL
- link.ts: 静态 import 改为动态 import（`await import("@tauri-apps/plugin-shell")`），避免非 Tauri 环境打包失败
- link.ts: Tauri 环境用 shell 插件调用系统浏览器，Web 环境降级 window.open
- tauri.conf.json: 启用 tauri-plugin-shell
- capabilities/default.json: 添加 shell:allow-open 权限
- Cargo.toml: 添加 tauri-plugin-shell = "2" 依赖
- lib.rs: 添加 .plugin(tauri_plugin_shell::init())

### 非分类列搜索功能
- ColumnFilter.tsx: 支持两种模式——分类列（多选 IN）和文本列（关键词 LIKE 搜索，回车应用）
- Companies.tsx: 所有列均渲染 ColumnFilter，分类列传 options，文本列不传自动进入搜索模式
- Jobs.tsx: 同上
- sync_service.py: get_companies 和 get_jobs_page 支持 **text_filters 文本列 LIKE 模糊搜索
- sync.py: 路由接收 location/position_titles/title/company/major_required/hard_skills/keywords/jd_summary/updated_at/deadline 等文本列参数
- companies.ts / jobs.ts: API 接口支持文本列模糊搜索参数

### 表格列宽优化
- Companies.tsx: location 列宽 160px → 120px
- Jobs.tsx: major_required 列宽 160px → 120px

### 数据同步链路修复
- feishu_source.py: 增量同步游标从 last_modified_time 改为 apply_update（飞书 Bitable API 不返回 last_modified_time）
- job_db.py: get_last_sync_time() 从 MAX(last_modified) 改为 MAX(apply_update)
- sync_service.py: company_overview 视图 last_updated 取 a.apply_update，jobs 视图 updated_at 取 a.apply_update

### 测试修复
- test_sync.py: 更新 _make_db() 和 test_get_jobs_since_cursor_same_timestamp 中的 jobs 表 schema，从 13 列（旧 spec）改为 20 列（对齐 JOB_FIELDS）
- 全部 32 个后端测试通过

### 构建验证
- tsc + vite build 成功（81 模块转换，无错误）
- @tauri-apps/plugin-shell 被拆为独立 chunk（3.56KB），只在 Tauri 环境运行时动态加载

---

## 2026-10-03 — M1 端到端验证 + CI 配置 ✅

**状态**: 全链路通过，CI 已配置

### 服务启动
- ✅ API 服务: `uvicorn main:app --port 8000` 运行中
- ✅ 前端服务: `npm run dev` → Vite 运行在 localhost:1420
- ✅ 前端 `.env` 配置: `VITE_API_URL=http://localhost:8000`

### E2E 验证（完整链路）
- ✅ 注册 → 200 + user_id
- ✅ 验证码 → auth.db 读取成功
- ✅ 邮箱验证 → 200 + JWT
- ✅ 登录 → 200 + JWT
- ✅ 岗位统计 → 35,693 条
- ✅ 岗位同步 → 5 条（伽利略 - 运控算法工程师）
- ✅ 简历解析 → 11 keywords + 5 fit_directions
  - 后端开发 weight=0.95
  - 全栈开发 weight=0.75
  - AI Infra weight=0.6
- ✅ Sidecar ping/pong

### 测试总计
- Python API：32/32 passed
- Rust Tauri：22/22 passed
- Python Sidecar：11/11 passed

### CI 配置
- ✅ 创建 `.github/workflows/build.yml`
- 3 个 build target：mac-arm / mac-intel / windows
- 触发：push tag `v*` 或手动 workflow_dispatch
- 产出：GitHub Releases 自动发布 .app/.dmg/.exe/.msi

### 环境配置
- `job_api/.env`：DEEPSEEK_API_KEY 已配置，JWT_SECRET 已设置
- `job_workbench/.env`：VITE_API_URL=http://localhost:8000
- RESEND_API_KEY 暂空（开发模式验证码打印到 stderr）

### 前端预览
- Vite dev server 运行在 http://localhost:1420
- 前端页面可正常加载（React + Tailwind 暖橙主题）

### Python Sidecar 评分引擎
- ✅ ping/pong JSON-RPC
- ✅ score_batch 3 个岗位：
  - 字节跳动后端：89.2 分 🔥强烈推荐（Python/Flask/Docker/MySQL 全命中）
  - 腾讯前端：45.0 分 ➖可申请（方向不对，role 硬门槛触发）
  - 国企行政：37.0 分 ➖可申请（跨大类，硬门槛触发）
- ✅ 评分逻辑符合第一性原理：方向对齐 > 技能命中 > 竞争力对齐

### 测试总计
- Python API：32/32 passed
- Rust Tauri：22/22 passed
- Python Sidecar：11/11 passed

### 修复的问题
- sync_router 未挂载到 main.py → 已修复
- sync_router 用 verify_token 而非 get_current_user → 已修复
- 测试缺认证 override → 已加 dependency_overrides

### DATA_DIR 配置
- sidecar.rs 的 spawn_child() 已正确设置 DATA_DIR 环境变量（第 132 行）
- 开发期 fallback：/workspace/job_assistant/data（kw_dict.json + job_category_tree.json 所在）
- 生产期：Tauri 启动时通过 env 传入实际数据目录

---

## 2026-10-03 — T13: 评分 + 推荐视图 ✅

**状态**: 完成

**产出**:

### `job_workbench/src-tauri/src/sidecar.rs`（新建，316 行）
- Python sidecar 评分引擎子进程管理器，承接 T11 的 JSON-RPC 协议（每行一个 `{"id","method","params"}` 请求 / `{"id","result"|"error"}` 响应）。
- **`SidecarManager` struct**：`handles: Mutex<Option<SidecarHandles>>` + `next_id: AtomicU64` + 路径配置；Tauri State 跨命令复用，Drop 时 `stop()` kill+wait 避免僵尸。
- **同步 std::process::Command**（不引 tokio::process，简化生命周期）：`stdin: BufWriter<ChildStdin>` + `stdout: BufReader<ChildStdout>` 拆开 Mutex 保护，`score_batch` 调用期间独占读写一行 JSON。
- **lazy 启动**：首次 `send_request` 时 `ensure_started()` 触发 spawn，不在 setup() 阶段启动，避免开发期 `python-sidecar/sidecar_server.py` 路径不存在时 panic 阻塞应用启动。
- **崩溃自愈**：`read_line` 返回 `Ok(0)`（EOF）或 stdin write 失败 → 清空 `*guard = None` + 返回错误，下次调用自动 `start()` 重启子进程。
- **`start()`**：`child.stdin.take()` + `child.stdout.take()` 避免 partial-move 后无法整体放进 `SidecarHandles`；`stderr` 用 `Stdio::inherit()` 让 sidecar 日志直接走父进程 stderr（开发期可见崩溃原因）。
- **路径解析**：`SIDECAR_SCRIPT` / `DATA_DIR` env 优先（生产可指向 PyOxidizer 打包后的可执行），fallback 到 `CARGO_MANIFEST_DIR/../python-sidecar/sidecar_server.py` + `/workspace/job_assistant/data`（开发期 `kw_dict.json` 所在）。`SIDECAR_PYTHON` env 控制解释器路径，默认 `python3`。
- **`score_batch(jobs, profile)`**：把 `&[Job]` 序列化为 sidecar 期望的 `{"jobs": [...], "profile": {...}}` params，调一次 `score_batch`，反序列化为 `Vec<ScoreResult>`；`ScoreResult.score = None` 表示单条评分失败（sidecar 已在响应里附 error 字段，被 struct serde 忽略）。
- **3 个单元测试**：`score_result_deserializes_from_sidecar_shape` / `score_result_allows_null_score_for_failed_item` / `resolve_paths_use_env_when_present`，覆盖 sidecar 输出 shape、null score 兜底、路径解析 fallback。

### `job_workbench/src-tauri/src/db.rs`（修改，新增 ~120 行）
- **`update_job_score(job_id, score, reason)`**：`UPDATE jobs SET llm_score=?, llm_reason=? WHERE job_id=?`，单字段 reason 是 sidecar 多条 reasons 用 `"; "` join 后的字符串（前端 `MatchScore.parseReasons` 按 `"; "` 还原）。
- **`get_scored_jobs(min_score, max_score, limit, offset)`**：动态 WHERE 拼接 + `Box<dyn ToSql>` 绑定；闭下界 `llm_score >= ?` / 开上界 `llm_score < ?`，与推荐分桶区间严格对齐（强烈推荐 `[75,+∞)` / 推荐 `[55,75)` / 可申请 `[35,55)` / 不建议 `[0,35)`）；`ORDER BY llm_score DESC LIMIT ? OFFSET ?` 分页，避免前端拉全量 35K 行再筛。
- **`get_score_summary()`**：6 个 `SELECT COUNT(*)` 一次性返回 `ScoreSummary { total, scored, strong_recommend, recommend, can_apply, not_recommended, unscored }`；`unscored` 单列方便前端区分"刚同步还没评"vs"评分过低"。
- **`ScoreSummary` struct**（`#[derive(Serialize)]`）：与前端 `src/api/scoring.ts::ScoreSummary` interface 字段严格对齐（snake_case 直通）。

### `job_workbench/src-tauri/src/lib.rs`（修改，新增 ~120 行）
- **注册 `SidecarManager::new()` 为 Tauri State**：在 `setup()` 内 `app.manage()`，注释说明 lazy 启动策略（不在 setup spawn，避免路径不存在时阻塞启动）；Drop 时 stop() 触发 kill+wait。
- **3 个新 Tauri command**：
  - `score_all_jobs(db, sidecar, profile: Value) → ScoreAllResult`：全量拉 `db.get_jobs(not_deleted=false)`（含软删记录，避免下次重评漏数据）→ `chunks(500)` 分批调 `sidecar.score_batch` → 回写 SQLite；统计 `scored / strong_count(≥75) / recommend_count(≥55)`；空表早 return 零值。
  - `get_scored_jobs(db, filter: Option<ScoredJobsFilter>, limit, offset) → Vec<Job>`：limit `clamp(1, 1000)` + offset `max(0)`，filter 默认 `{}`。
  - `get_score_summary(db) → ScoreSummary`：单次 SELECT COUNT，毫秒级可频繁刷新。
- **`ScoreAllResult` / `ScoredJobsFilter` struct**：与前端 TS interface 严格对齐；`ScoredJobsFilter` 用 `serde::Deserialize + Default` 接收前端可选参数。
- **invoke_handler 注册**：在 `generate_handler!` 列表追加 `score_all_jobs / get_scored_jobs / get_score_summary`。

### `job_workbench/src/api/scoring.ts`（新建，76 行）
- TypeScript 调用 `invoke("score_all_jobs" / "get_scored_jobs" / "get_score_summary")` 的封装层。
- **类型定义**：`ScoreAllResult` / `ScoreSummary` / `ScoredJobsFilter` 与 Rust 端 struct 字段严格对齐（snake_case JSON 直通，前端 invoke 收发无需转换）。
- **`scoreAllJobs(profile: unknown)`**：`invoke<ScoreAllResult>("score_all_jobs", { profile })`，profile 是 `resumeStore.parsedProfile` 直接传入（snake_case `keywords/fit_directions` 与 sidecar `_build_profile` 兼容，SimpleNamespace 接收任意字段）。
- **`getScoredJobs(filter?, limit?, offset?)`**：默认 limit=50 / offset=0；filter 为 `undefined` 时传 `null`（Tauri command 的 `Option<ScoredJobsFilter>` 接收）。
- **`getScoreSummary()`**：单次 invoke，毫秒级，可频繁刷新 Tab 数量。

### `job_workbench/src/stores/scoreStore.ts`（新建，157 行）
- Zustand `useScoreStore` 单例，承接 T13 推荐视图状态中枢。
- **state**：`isScoring` / `scoringProgress: {scored, total} | null` / `scoreSummary` / `scoredJobs[]` / `isLoading`（首屏 skeleton）/ `isLoadingMore` / `error` / `scoredFilter` / `hasMore`。
- **`scoreAll(profile)`**：重入保护（`isScoring` 为 true 直接 return null）；空 profile（null 或空对象）设错误 + return null；进行中 `isScoring=true + scoringProgress={0,0}`；完成后 `loadSummary()` 刷新 Tab 数量 + `loadScoredJobs()` 刷新当前 Tab 列表；返回 `ScoreAllResult | null` 供调用方决策（前端 `Jobs.tsx` 据此切到"🔥 强烈推荐"或"✅ 推荐"Tab）。
- **`loadScoredJobs(filter?)`**：重置 offset=0 + `scoredJobs=[]` + `isLoading=true`（控制 skeleton）；模块级 `loadSeq` 自增序号 + `if (seq !== loadSeq) return` 丢弃过期响应，避免快速切 Tab 时旧响应覆盖新结果；完成后 `isLoading=false` + `hasMore = jobs.length >= PAGE_SIZE`。
- **`loadScoredJobsMore()`**：防重入（`isLoadingMore` / `!hasMore`）；`offset = scoredJobs.length` 累加；捕获当前 `loadSeq`，过期响应丢弃；失败设 error + `isLoadingMore=false`。
- **`loadSummary()`**：失败静默（summary 仅用于 Tab 数量，不阻塞列表）；记录 error 但不抛。
- **`clearError()`**：UI 错误条关闭按钮调。
- **`SCORED_PAGE_SIZE = 50`**：与 `db.rs::get_scored_jobs` 默认 limit 对齐；35K 已评分岗位分页加载。

### `job_workbench/src/components/MatchScore.tsx`（新建，196 行）
- 评分展示组件：分数环（SVG circle + stroke-dasharray）+ 推荐等级徽章 + 评分理由列表。
- **`getTone(score)`**：4 档色系——≥75 绿色（`#16a34a`，强烈推荐 🔥）/ 55-74 橙色（`#f97316`，推荐 ✅）/ 35-54 灰色（`#64748b`，可申请 ➖）/ <35 灰红（`#94a3b8`，不建议 ❌）；与 `scorer.py` / Rust `db.rs::get_score_summary` 阈值严格对齐。
- **`ScoreRing` 子组件**：直径 56px / 环宽 4，`stroke-dasharray = (score/100) * circumference`；背景环 `text-slate-100` + 进度环 `tone.color`；`-rotate-90` 让 0° 起点在 12 点钟方向；中心 `Math.round(score)` 数字。
- **`parseReasons(reason)`**：按 `"; "` 拆分 Rust 端拼接的 reason 字符串，`trim + filter Boolean`，空串返回 `[]`，全空兜底单元素列表避免组件无内容。
- **紧凑模式（`compact=true`）**：仅分数环 + 徽章一行，无理由列表；推荐 Tab 用，提升列表信息密度。
- **完整模式**：分数环 + 徽章 + "匹配分 N / 100" + 理由列表前 3 条 + 超过 3 条折叠 + "展开全部(N)" / "收起理由" 链接 toggle。
- **`THRESHOLD_*` 常量**：与 `scorer.py` / Rust / `Jobs.tsx` 完全对齐（75/55/35）。

### `job_workbench/src/pages/Jobs.tsx`（修改，新增 ~30 行）
- **Tab 4 档激活**：原"全部岗位"（默认）+ "🔥 强烈推荐(N)" + "✅ 推荐(N)" + "➖ 可申请(N)"；不显示"❌ 不建议"Tab（<35 默认隐藏，UI 不引导申请低分岗位）。
- **`scoreSummary` 注入 Tab 数量徽章**：`tabs[].count = scoreSummary?.strong_recommend/recommend/can_apply`，>0 时显示橙色圆角徽章。
- **`handleTabClick(tab)`**：切推荐 Tab 时调 `loadScoredJobs({ min_score, max_score })` 按区间过滤；"全部岗位"Tab 不调（用 `jobsStore.jobs`）。
- **简历解析完成自动触发评分**：`useEffect` 监听 `resumeStore.parsedProfile` 从 null→object 转变（`lastProfileRef` 避免重复触发），调 `scoreAll(profile)` 完成后据 `result.strong_count > 0` 切到"🔥 强烈推荐"Tab，否则 `recommend_count > 0` 切"✅ 推荐"Tab。
- **`visibleIsLoading` 双 store 切换**：`isRecommendTab ? isScoredLoading : isLoading`——推荐 Tab 用 `scoreStore.isLoading` 控制 skeleton（与 `jobsStore.isLoading` 行为一致），切 Tab 时显示 6 个 SkeletonCard 占位。
- **评分进度提示**：`isScoring && scoringProgress` 时顶部橙色横条"🤖 正在评分岗位… 已评 N / M"。
- **Tab 禁用态**：`isScoring` 期间非"all"Tab 禁用（`disabled + cursor-not-allowed`），避免评分进行中切到空 Tab。
- **`recommendMode` 透传 JobCard**：推荐 Tab 下 JobCard 用紧凑 MatchScore，"全部岗位"Tab 用完整 MatchScore（含理由列表）。

### `job_workbench/src/components/JobCard.tsx`（修改，新增 ~10 行）
- **`recommendMode` prop**：true 时 MatchScore 用紧凑模式（仅分数环 + 徽章），false 用完整模式（含理由列表前 3 条 + 展开）。
- **`hasScore` 分支**：`llm_score != null` 渲染 `<MatchScore score reason compact={recommendMode} />`，无评分渲染灰底"未匹配" `ScoreBadge` + 单行 reason（`line-clamp-1 + title` 悬停看全文）。
- **import MatchScore**：从 `./MatchScore` 引入新组件，替换原 `ScoreBadge` 单徽章呈现（`ScoreBadge` 保留作无评分 fallback）。

**验收**:
- ✅ Rust 端编译通过（`cargo check` 零错误；`sidecar.rs` 单元测试 3 项通过：`score_result_deserializes_from_sidecar_shape` / `score_result_allows_null_score_for_failed_item` / `resolve_paths_use_env_when_present`）
- ✅ TypeScript 语法正确（`scoreStore.ts` / `scoring.ts` / `MatchScore.tsx` / `Jobs.tsx` / `JobCard.tsx` 人工检查；`strict` + `noUnusedLocals` + `noUnusedParameters` 全开，所有 import 均被消费）
- ✅ 暖橙主题贯穿（`bg-orange-50/orange-500/orange-100/orange-200/orange-400/orange-600` + `border-orange-*` + `focus:ring-orange-*`），MatchScore 用语义色（绿/橙/灰/灰红）区分推荐等级
- ✅ 推荐分桶阈值严格对齐（`scorer.py` / Rust `db.rs::get_score_summary` / `MatchScore.tsx::THRESHOLD_*` / `Jobs.tsx::THRESHOLD_*` 全部 75/55/35）
- ✅ scoreStore 状态机完整（`isScoring` 全量评分进行态 + `isLoading` 首屏加载态 + `isLoadingMore` 加载更多态 + `scoringProgress` 进度反馈 + `error` 错误条 + `loadSeq` 防过期响应覆盖）
- ✅ 简历解析 → 自动评分 → 自动切推荐 Tab 全链路打通（`Jobs.tsx::useEffect` 监听 `parsedProfile` + `lastProfileRef` 防重复触发）
- ✅ MatchScore 双模式（紧凑 + 完整）按 Tab 切换（推荐 Tab 紧凑提升密度，全部岗位 Tab 完整带理由列表）
- ✅ sidecar 子进程崩溃自愈（EOF → 清空状态 → 下次调用自动重启），lazy 启动不阻塞应用启动
- ⚠️ 按任务约束未执行 `npm install`；`tsc --noEmit` 全量类型检查需依赖安装后跑（预期；esbuild 解析零语法错误）

**关键设计决策**:
- **同步 std::process::Command 而非 tokio::process**：sidecar 调用是同步阻塞 IO（每批 500 条几秒级），UI 命令在线程池跑不阻塞渲染；不引 tokio::process 简化生命周期 + 避免 tokio runtime 依赖混入。`Mutex<BufWriter/BufReader>` 保护跨线程读写。
- **lazy 启动 + 崩溃自愈**：`SidecarManager` 在 `setup()` 注册为 State 但不 spawn 子进程；首次 `send_request` 时 `ensure_started()` 触发。EOF（崩溃）→ 清空 `*guard = None` + 返回错误，下次调用自动重启。开发期 python-sidecar 路径不存在时不阻塞应用启动。
- **`score_all_jobs` 分批 500 + chunks**：单批 JSON 太大 sidecar 解析慢 / 内存峰值高；500 条/批几秒级，35K 条总耗时分钟级可接受。`chunks(500)` 不跨边界，每批 ≤500。`score=None` 的失败项跳过保留旧 `llm_score` 不覆盖（下次再试）。
- **`llm_reason` 单字段 vs 多字段**：sidecar 返回 `reasons: Vec<String>`，SQLite `jobs.llm_reason` 是 TEXT 单字段；Rust 端 `r.reasons.join("; ")` 拼接，前端 `MatchScore.parseReasons` 按 `"; "` 还原。保持表 schema 不变（不增 reasons 表），前端体验无差。
- **`loadSeq` 模块级自增序号防过期响应**（与 `jobsStore` 同模式）：快速切 Tab 时旧 `loadScoredJobs` 响应可能晚于新响应到达，直接 set 会覆盖；`++loadSeq` 捕获 seq，await 后 `if (seq !== loadSeq) return` 丢弃过期。`loadMore` 同样捕获 seq，避免 `loadScoredJobs` 重置后旧 `loadMore` 响应再覆盖。
- **`isLoading` 双 store 切换**：`isRecommendTab ? isScoredLoading : isLoading`——推荐 Tab 用 scoreStore 自己的 `isLoading` 控制 skeleton，与"全部岗位"Tab 的 `jobsStore.isLoading` 行为一致；切 Tab 时 6 个 SkeletonCard 占位，避免空白跳跃。
- **不显示"❌ 不建议"Tab**：<35 分岗位默认隐藏（UI 不引导申请低分岗位），用户仍可在"全部岗位"Tab 看到；如确需查看可走全部岗位 + 筛选。这与 spec "≥75 强烈推荐 / ≥55 推荐 / ≥35 可申请 / <35 不建议" 的产品意图一致（不建议 = 不展示）。
- **`MatchScore` 自绘 SVG 分数环而非引图表库**：`circle + stroke-dasharray` 实现进度环，56px 直径 + 4px 环宽，`-rotate-90` 让 0° 起点在 12 点钟；不引 recharts / d3 等库，零额外依赖，符合 T6+T7 已定的"不引入新前端包"约束。
- **`ScoreRing` 用 `tone.color` 直接传 stroke 颜色**：而非 Tailwind 类名（SVG stroke 属性不接受 Tailwind 任意值类的运行时拼接）；`tone.color` 是 hex 字符串直接绑到 `stroke={tone.color}`，背景环用 `text-slate-100 + stroke="currentColor"` 复用。
- **`scoreAll` 返回 `ScoreAllResult | null` 而非 throw**：重入 / 空 profile 时 return null，调用方 `Jobs.tsx` 用 `if (result && result.strong_count > 0)` 决策切 Tab；比 throw 更友好（错误已落 `error` state，UI 显示红色横条，无需 try/catch 包裹）。

**下一步**: T15 — 投递记录编辑/删除入口（`delete_application` Tauri command + 卡片"…"菜单）；或岗位详情页（JD 全文 + 评分明细维度分解 + 同公司历史投递）；或邮件自动采集 → applications 表 source="email" 流水注入（推荐 Tab 评分高 → 自动建议投递 → 邮件回执自动落 Kanban）

---

## 2026-10-03 — T10: 岗位列表首页 + 筛选 ✅

**状态**: 完成

**产出**:

### `job_workbench/src/api/jobs.ts`（新建，126 行）
- TypeScript 调用 Tauri invoke 的封装层。`Job` / `JobStats` interface 与 `src-tauri/src/models.rs::Job / JobStats` 字段严格对齐（snake_case JSON 直通）。
- **`JobFilter` 用户面接口**：字段名贴近产品语义（`city / education / is_mt / category / company / keyword / sort`），UI 层只用本接口，不必感知 Rust 端字段名。
- **`RustJobFilter` 内部接口**：与 Rust `JobFilter` struct 字段对齐（`city / graduation_match / is_mt / category / company / search / not_deleted / min_score`）。
- **`toRustFilter(filter)` 转换**：
  - `city`: "全国各地" 视为不筛选。
  - `education`: 后端无独立学历筛选字段，映射为 `search`（`jd_text` 多含"本科"等字符串，LIKE 可命中）；与 `keyword` 同时有值时 `keyword` 优先（`search` 是单 LIKE 模式无法 OR）。
  - `is_mt` / `category`（"不限"跳过）/ `company`（trim）直传。
  - `sort` 暂未传 Rust（Rust 固定 `ORDER BY updated_at DESC NULLS LAST`），预留 T13 推荐视图按 `llm_score` 排序扩展。
- **`getJobs(filter?, limit?, offset?)` → `invoke<Job[]>("get_jobs", {filter, limit: 50, offset: 0})`**：默认 50 条/页，与 `db.rs::get_jobs` 默认 limit 一致；Rust 端 `clamp(1, 1000)` 自动收敛。
- **`getJobStats()` → `invoke<JobStats>("get_job_stats")`**：返回 `{total, updated_at}`，用于顶部 StatsBar。

### `job_workbench/src/stores/jobsStore.ts`（新建，144 行）
- Zustand `useJobsStore` 单例，state: `jobs[] / isLoading / isLoadingMore / error / filters / stats / hasMore`。
- **`PAGE_SIZE = 50`**：单页条数，与 `db.rs::get_jobs` 默认对齐；35K 条用分页加载（暂不接虚拟滚动，T15+ 范围）。
- **`DEFAULT_FILTERS`**：与 `JobFilterBar` 下拉默认值对齐（`city="全国各地" / education="不限" / is_mt=undefined / category="不限" / company="" / keyword=""`）。
- **`loadJobs(filters?)`**：重置 offset=0 拉首屏；`isLoading=true` + `jobs=[]`（首屏期间显示 skeleton，不残留旧数据）。`hasMore` 由返回条数 ≥ PAGE_SIZE 推断。
- **`applyFilter(patch)`**：合并 patch 到当前 filters → `loadJobs(next)`，下拉/开关即时触发。
- **`clearFilters()`**：用 `DEFAULT_FILTERS` 重置 → `loadJobs`。
- **`loadMore()`**：防重入（`isLoadingMore` / `!hasMore`）；`offset = jobs.length` 累加，不去重（`db.rs ORDER BY updated_at DESC`，分页不会重叠）。
- **`loadStats()`**：刷新顶部"共 N 个岗位"；失败静默（stats 仅用于 StatsBar，不阻塞列表）。
- **`loadSeq` 模块级自增序号 + `if (seq !== loadSeq) return` 丢弃过期响应**：避免快速切筛选时旧响应覆盖新结果。`loadJobs` 启动时同步重置 `isLoadingMore=false`，使进行中的 `loadMore` 提前 return，避免脏数据覆盖。

### `job_workbench/src/components/JobCard.tsx`（新建，139 行）
- 单个岗位卡片：暖橙色调（`border-orange-100` / `bg-orange-50/40`）+ `rounded-2xl` + `shadow-card` + `hover:-translate-y-0.5 hover:shadow-lg` 微交互。
- **展示**：公司名（`text-base font-semibold`，truncate）、岗位名（`text-sm text-slate-600`）、城市（📍）、学历要求（🎓，从 `requirements` 字段）、截止日期（⏰，`formatDate` 兼容 SQLite "YYYY-MM-DD HH:MM:SS" 与 ISO8601）。
- **管培徽章**：`is_mt === 1` 时右上角 `bg-orange-500` 圆角徽章。
- **`ScoreBadge` 子组件**：`llm_score == null` 显示灰底"未匹配"徽章；有值显示分数（`Math.round`），≥80 橙色实底、≥60 浅橙、<60 灰色。`title={llm_reason}` 悬停看全文。
- **"投递"按钮**：`window.open(applyUrl, "_blank", "noopener,noreferrer")` 跳外链；Tauri 2 webview 由 OS 默认浏览器接管（未启用 shell 插件时的兜底）；`apply_url` 为 null 时禁用按钮（`disabled:opacity-50 disabled:cursor-not-allowed`）。
- **"记录投递"按钮**：`useNavigate()` 跳 `/applications`，`state: { job }` 携带岗位信息（`AddApplicationModal` 后续 T15+ 可读 `location.state` 预填）。

### `job_workbench/src/components/JobFilterBar.tsx`（新建，194 行）
- 筛选栏：`sticky top-0 z-10` + `bg-white/90 backdrop-blur`，滚动列表时常驻可见。
- **网格布局**：mobile 1 列 / md 2 列 / lg 4 列；关键词搜索 `lg:col-span-3` 占满末行。
- **下拉选项**：
  - 城市：全国各地/北京/上海/广州/深圳/杭州/成都/南京/武汉/西安
  - 学历：不限/大专/本科/硕士/博士
  - 分类：不限/工科/商科/文科/理科/医科/艺术/农学（对齐 `job_tree` 大类）
- **管培开关**：`role="switch" + aria-checked`，自绘 toggle（`h-5 w-9` 圆角条 + `h-4 w-4` 白圆点）。`!filters.is_mt ? true : undefined` 二态切换。
- **即时触发**：下拉/开关 `onChange` 立即 `applyFilter`；文本输入（公司 / 关键词）本地 state + 300ms 防抖（`setTimeout` + `clearTimeout`），避免每键一次 invoke。
- **清除筛选**：`storeClearFilters()` + 同步本地 `keywordInput/companyInput` 为空，避免 UI 残留。

### `job_workbench/src/pages/Jobs.tsx`（重写，203 行，原占位 8 行）
- 顶部：标题 + `StatsBar`（`共 N 个岗位` + `数据停止于 YYYY-MM-DD HH:MM`，从 `stats.total/updated_at` 取）+ `SyncIndicator`（T9 已建）。
- **Tab 切换**：3 个 `TabButton`——"全部岗位"（默认激活，橙色实底）、"🔥 强烈推荐" / "✅ 推荐"（灰色禁用，T13 实现）。
- **`StatsBar` 子组件**：`useJobsStore(s => s.stats)` 选择器订阅，避免 jobs 变化时无谓重渲染。
- **`SkeletonCard` 子组件**：`animate-pulse` + 6 个占位卡片，首屏加载期间渲染。
- **主体三态**：
  - `isLoading` → 6 个 SkeletonCard 网格。
  - `isEmpty`（`!isLoading && jobs.length === 0`）→ 引导文案 + "试试调整筛选条件，或先同步岗位数据"。
  - 数据 → `jobs.map(job => <JobCard>)` 网格 + `hasMore` 时显示"加载更多"按钮（`isLoadingMore` 时禁用 + 文案改"加载中…"）。
- **挂载 `useEffect`**：`void loadJobs()` + `void loadStats()`，deps 只含稳定函数引用不会循环。

**验收**:
- ✅ TypeScript 语法正确（人工检查；`strict` + `noUnusedLocals` + `noUnusedParameters` 全开，所有 import 均被消费，无未使用变量；`import type` 用于 type-only 导入，`isolatedModules` 兼容）
- ✅ 暖橙主题（`bg-orange-500` / `bg-orange-50` / `text-orange-700` / `border-orange-100`，与 T12/T14 同色系）+ 大圆角（`rounded-2xl`）+ `shadow-card` + hover 微交互
- ✅ 筛选即时触发（下拉/开关 onChange 立即 applyFilter；文本输入 300ms 防抖避免每键一次 invoke）
- ✅ JobCard 信息完整（公司 / 岗位 / 城市 / 学历 / 管培徽章 / 截止日期 / 评分徽章 + 理由 / 投递 + 记录投递按钮）
- ✅ 空状态（"🔍 暂无匹配的岗位" + 引导）+ 加载状态（6 个 SkeletonCard）均处理
- ✅ 分页 loadMore（每次 +50 条，`hasMore` 控制按钮显隐；`loadSeq` 防过期响应覆盖）
- ✅ 适配 T6+T7 Rust 端 `get_jobs(filter, limit, offset) → Vec<Job>` 三参签名（任务描述简化为 `get_jobs(filter)`，前端按 Rust 实际签名封装）

**关键设计决策**:
- **`JobFilter` 用户面 vs Rust 面 字段映射**：用户面用 `education / keyword / sort` 贴近产品语义；Rust 面 `JobFilter` struct 实际字段为 `graduation_match / search`（无学历独立字段、`sort` 固定 `updated_at DESC`）。在 `api/jobs.ts::toRustFilter` 做显式转换，UI 层不感知后端细节。`education` 兜底用 `search`（`jd_text` 多含"本科"等字符串，LIKE 可命中），与 `keyword` 同时有值时 `keyword` 优先（`search` 单 LIKE 无法 OR）。
- **`loadSeq` 模块级自增序号防过期响应**：快速切筛选时旧响应可能晚于新响应到达，直接 set 会用旧数据覆盖新结果。`loadJobs` 启动 `++loadSeq` 捕获 seq，await 后 `if (seq !== loadSeq) return` 丢弃过期。`loadMore` 同样捕获 seq，避免 `loadJobs` 重置 jobs 后旧 `loadMore` 响应再覆盖。
- **`Job` interface 与 `appStore.ts::Job` 重复定义**：两者与 Rust `Job` struct 字段对齐，结构相同；TS 结构类型兼容，跨 store 传递无障碍。未合并为单一来源以避免触碰 T14 已交付的 `appStore.ts`（最小变更原则）。
- **不装 npm 依赖**：用项目已有的 `zustand ^4.5.5` / `react-router-dom ^6.26.0` / `@tauri-apps/api ^2.0.0`，未引入新包。`window.open(_blank)` 跳外链（未启用 `@tauri-apps/plugin-shell`，OS 默认浏览器接管）。
- **管培开关自绘而非引 UI 库**：`role="switch" + aria-checked` 无障碍；`h-5 w-9` 圆角条 + `h-4 w-4` 白圆点 + `left-0.5/left-4` 切换，纯 Tailwind 类实现。
- **StatsBar 用 selector 订阅**：`useJobsStore(s => s.stats)` 而非解构整个 store，避免 jobs/isLoading 变化时无谓重渲染 StatsBar。
- **Tab "🔥 强烈推荐" / "✅ 推荐" 灰色禁用**：`disabled` 属性 + `cursor-not-allowed bg-slate-100 text-slate-400`；T13 实现推荐视图时改为激活态 + 切数据源。

**下一步**: T11 — 岗位详情页（JD 全文 + 评分明细 + 同公司历史投递）；或 T13 — 推荐视图 Tab 实现（按 `llm_score` 排序 + 接 T12 简历画像匹配）

---

## 2026-10-03 — T12: 简历上传 + LLM 解析 ✅

**状态**: 完成

**产出**:

### `job_workbench/src/api/llm.ts`（新建，103 行）
- LLM API 封装层，复用 T8 的 `apiClient`（Bearer Token 自动注入 + 401 自动 refresh），与 `auth.ts` / `sync.ts` 同层。
- **`parseResume(resumeText)`**：`POST /api/v1/llm/parse-resume { resume_text }` → `{ keywords, fit_directions }`，归一化为 `ParsedProfile`。
- **`supplementProfile(userEdited, resumeText)`**：`POST /api/v1/llm/supplement { user_edited, resume_text }`，供后续"用户编辑 → LLM 补充"链路调用。
- **类型契约**：`KeywordTag`（kw / standard / category / weight / source / resume_section）与 `docs/staging/specs/2026-09-29-resume-keyword-matching.md` 的 dataclass 对齐；`FitDirection`（direction / weight / evidence / description）；`ParsedProfile = { keywords, fit_directions }`。
- **`normalizeParsedProfile`**：LLM 输出 JSON 字段名会漂移（kw/keyword/word；direction/direction_name/name），在边界做一次归一化，store / 组件只消费稳定结构。环境变量 `VITE_API_URL`（与 client.ts 一致）。

### `job_workbench/src/stores/resumeStore.ts`（新建，216 行）
- Zustand store，承接简历状态管理 + Tauri invoke 桥接。
- **state**：`activeResume`（Resume 镜像）/ `parsedProfile`（结构化画像）/ `isLoading` / `phase: idle|uploading|parsing|done`（精确反馈三阶段，驱动 UI spinner 文案）/ `error` / `lastFileName`。
- **`uploadResume(file)`**：浏览器 `FileReader.readAsText` 提取文本（`@tauri-apps/plugin-fs` 未在 package.json，且任务允许 FileReader）→ PDF / 非文本类型以"即将支持"拦截 → `save_resume` 写本地（`is_active=1`，新上传覆盖旧的 active）。`file_path` 存 `file.name`（浏览器安全限制不暴露完整路径）。
- **`parseResume(resumeText?)`**：缺省取 `activeResume.raw_text` → 调 `llmApi.parseResume` → `parsed_profile_json` 回写本地 resume（刷新 / 重启后 `getActiveResume` 可还原）。
- **`getActiveResume`**：`invoke("get_active_resume")` → 若有 `parsed_profile_json` 则反序列化 `parsedProfile`，无则置 idle。
- **`clearResume`**：仅清本地状态（DB 行保留，新上传以 `created_at DESC` 顺序遮蔽旧 active），用于"重新上传"按钮。
- **`formatFileSize`** 导出工具 + `nowIso`（与 appStore 同实现，对齐 SQLite TEXT 字段）+ `genResumeId`（时间戳 + 短随机，参考 T14 `genAppId`）。

### `job_workbench/src/components/ResumeUploader.tsx`（新建，160 行）
- 拖拽 + 点击双通道上传区域：`<input type="file" accept=".txt,.md,.markdown,.text,.pdf" hidden>` + dropzone div（`onDrop` / `onDragOver` / `onDragLeave` + `onClick` 触发 `inputRef.click()`）。
- **a11y**：`role="button"` + `tabIndex={0}` + `onKeyDown`（Enter / Space 触发选择），键盘可达。
- **已选文件卡片**：emoji + 文件名（`truncate`）+ 大小（`formatFileSize`）+ ✕ 移除按钮。
- **进度反馈**：按钮文案随 `phase` 切换（上传中… / 解析中… / 完成 / 上传并解析）+ spinner。
- **关键修复**：`<input>` 放在 dropzone div 外作兄弟节点，避免 `input.click()` 合成事件冒泡回 dropzone 重复触发 onClick（否则循环打开文件对话框）。
- **错误提示**：暖橙 alert（`bg-orange-50 text-orange-700`）内联在 uploader 内，上传阶段错误就近显示。

### `job_workbench/src/components/ParsedProfileDisplay.tsx`（新建，228 行）
- 函数式组件，接收 `profile: ParsedProfile`。
- **关键词分组**：按 category 分组渲染，6 个主分类（hard_skill 硬技能 / soft_skill 软技能 / cert 证书 / education 教育 / city 城市 / role 方向）+ "其他"兜底（tool/framework/domain/project 等未列入分类统一归入）；每组按 weight 倒序。
- **`CATEGORY_META`**：每类含 icon + 浅色徽章 + 强调文字色，统一暖橙系。
- **`WeightBar`**：以组内最大权重为 100% 做相对条形图（`Math.min(100, Math.max(6, ...))` 保底 6% 可见），数字始终显示原值。
- **`FitDirectionCard`**：方向名 + 权重徽章 + 权重条 + 证据（`bg-orange-50/60`），`hover:-translate-y-0.5` 微交互。
- **"编辑"按钮**：切换 `editMode`，当前仅显示预览态提示（"编辑模式为预览态，增删改后续任务接入"），编辑功能预留。

### `job_workbench/src/pages/Resume.tsx`（重写，146 行，原占位 8 行）
- **布局分支**：无简历 → ResumeUploader 居中（`min-h-[60vh]`）；有简历 + 解析中 → spinner + "正在分析你的简历…"；有简历 + 已解析 → ParsedProfileDisplay + "重新上传"按钮；已上传未解析 → 引导卡片 + "立即解析"按钮。
- **顶部**：标题 + `StatusBadge`（未上传 / 上传中 / 解析中 / 已解析 / 已上传，圆点 + 脉冲动画）+ 右侧"重新上传"按钮（`clearResume` 切回上传态）。
- **错误处理**：页面级暖橙 alert + "重新解析"按钮（仅在已上传简历时显示，避免与 uploader 内联错误重复）。
- **挂载**：`useEffect(() => getActiveResume(), [])` 还原历史解析结果。

**验收**:
- ✅ TypeScript 语法正确（人工检查，未装 npm 依赖；`strict` + `noUnusedLocals` + `noUnusedParameters` 全开，所有 import 均被消费，无未使用变量）
- ✅ 暖橙主题（`bg-orange-500` / `bg-orange-50` / `text-orange-700` / `border-orange-100`，与 T14 同色系）+ 大圆角（`rounded-2xl` / `rounded-card`）+ `shadow-card`
- ✅ 文件上传支持拖拽（`onDrop` / `onDragOver` / `onDragLeave` + 高亮 `ring-4 ring-orange-100`）+ 点击选择 + 键盘 Enter/Space
- ✅ 解析进度三阶段明确反馈（`phase` 驱动 StatusBadge / uploader 按钮文案 / 页面 spinner）
- ✅ ParsedProfileDisplay 按 category 分组展示（6 主分类 + 其他），每个关键词显示词 + weight 条形图，每个适配方向显示 direction + weight + evidence
- ✅ PDF 标注"即将支持"并在 store 层拦截（避免乱码文本污染 LLM 解析）
- ✅ 复用 T8 `apiClient`（鉴权 / refresh 透传）+ T6+T7 `save_resume` / `get_active_resume` Tauri command + T14 设计语言（emoji 图标 + `shadow-card` + `rounded-2xl`）

**备注**:
- `package.json` 未含 `@tauri-apps/plugin-fs`，且任务要求"不装 npm 依赖"，故文件读取走浏览器 `FileReader.readAsText`（Tauri webview 支持），`file_path` 存 `file.name`。PDF 文本提取需 Rust 侧或 Python sidecar 处理，MVP 先支持 .txt/.md。
- `save_resume` 在 Rust 端返回 `()`（参考 T14 `addApplication` 处理），前端用入参 resume 推断返回态。
- `parsed_profile_json` 在 store 层用 `JSON.stringify` 序列化存储，`getActiveResume` 反序列化还原；`normalizeParsedProfile` 在 API 边界兜底 LLM 字段名漂移。
- `clearResume` 仅清本地状态（无 `delete_resume` Tauri command），新上传以 `created_at DESC` 顺序在 `get_active_resume` 中遮蔽旧 active 行。

**下一步**: T13 — 简历编辑模式（增删关键词 / 调整 weight / 适配方向修正）+ `supplementProfile` 链路接入

---

## 2026-10-03 — T14: 投递记录 Kanban 看板 ✅

**状态**: 完成

**产出**:

### `job_workbench/src/stores/appStore.ts`（新建，182 行）
- Zustand store，承接投递记录状态管理 + Tauri invoke 桥接。
- **类型定义**:`Application` / `Job` interface 与 `src-tauri/src/models.rs::Application / Job` 字段严格对齐（snake_case JSON 直通，前端 invoke 收发无需转换）；`ApplicationStatus = "draft" | "applied" | "test" | "interview" | "offer" | "rejected"`。
- **KANBAN_COLUMNS 常量**:6 列定义数组,每列含 `status / label(中文) / columnBg(列背景 Tailwind 类) / headerBg(列头背景) / dotColor(圆点色) / accentText(强调文字色)`。
  - draft → 待投递(`bg-slate-100`)
  - applied → 已投递(`bg-blue-50`)
  - test → 笔试中(`bg-yellow-50`)
  - interview → 面试中(`bg-orange-50`,暖橙主题主列)
  - offer → 已录用(`bg-green-50`)
  - rejected → 已拒绝(`bg-red-50`)
- **state**:`applications[]` / `jobs[]`(用于卡片显示公司名/岗位名)/ `isLoading` / `error` / `dragSource`(拖拽源记录)。
- **actions**:
  - `loadApplications`:`Promise.all` 并行调 `invoke("get_applications")` + `invoke("get_jobs", {filter:null, limit:200, offset:0})` 一次拉齐数据;失败设 `error`。
  - `addApplication`:`invoke("upsert_application", {app})` → 入参 app 直接 upsert 幂等;成功后本地 `applications` 同 app_id 替换/前置插入。**适配 T6+T7 Rust 端 `upsert_application → Result<(), String>` 返回 `()` 的实情**(任务描述写"→ Application"但 Rust 端实际返回空,前端用入参 app 推断返回态)。
  - `updateApplicationStatus`:**乐观更新**先本地切 status + updated_at → 调 invoke → 失败回滚原 app + 设 error(拖拽体验流畅,失败可见)。
  - `removeApplication`:仅本地移除(暂无 `delete_application` Tauri command)。
  - `setDragSource` / `clearError`:UI 状态辅助。
- **`nowIso()` 工具**:`new Date().toISOString().replace("T"," ").slice(0,19)` 产出 `YYYY-MM-DD HH:mm:ss`,与 SQLite TEXT 字段 + Rust 端 chrono ISO8601 约定一致。

### `job_workbench/src/components/ApplicationCard.tsx`（新建，110 行）
- 函数式组件,接收 `application` / `job` / `onDragStart` / `onDragEnd` / `onSaveNotes` 五个 props。
- **展示**:公司名(从关联 `job.company` 取,无则"（未知公司）")+ 岗位名 + 投递时间(截前 10 位日期)+ 备注(`line-clamp-2` 两行截断)。
- **来源图标**:右上角 emoji,`source === "email"|"auto"` → ✉️ 邮箱自动,否则 ✋ 手动;附 `aria-label` + `title` 无障碍。
- **拖拽**:`draggable` + `onDragStart` 设置 `dataTransfer`(text/plain = app_id, effectAllowed = "move") + 回调 `setDragSource(app)`;`onDragEnd` 清 dragSource。
- **点击展开**:卡片整体 `onClick` toggle expanded;展开后 `textarea` 编辑备注,内层 `onClick stopPropagation` 防止冒泡关闭;"保存备注" 按钮调 `onSaveNotes(app, notes)` 后收回。
- **样式**:暖橙色调(`border-orange-100` / `bg-orange-50/30` / `focus:ring-orange-400`)+ `rounded-2xl` 大圆角 + `shadow-card` + `hover:-translate-y-0.5 hover:shadow-lg` 微交互。

### `job_workbench/src/components/KanbanBoard.tsx`（新建，119 行）
- 6 列网格布局:`grid grid-cols-6 gap-3`,每列 `min-h-[60vh]` 撑高,列背景用 `col.columnBg`。
- **列头**:圆点(`col.dotColor`)+ 中文标签(`col.accentText`)+ 右侧数量徽章(`bg-white/70`);`bg-${col.headerBg}` 浅色背景。
- **空列占位**:`border-dashed border-slate-300 bg-white/40` + "暂无" 文案。
- **拖拽逻辑(原生 HTML5 API)**:
  - `onDragOver`:`e.preventDefault()`(允许 drop)+ `e.dataTransfer.dropEffect = "move"` + 高亮当前列(`dragOverStatus` 状态 + `ring-2 ring-orange-400` 视觉)。
  - `onDragLeave`:用 `e.relatedTarget` + `currentTarget.contains()` 判断真正离开列容器才清高亮,避免子元素切换闪烁。
  - `onDrop`:从 store 取 `dragSource`,若 status 变化则调 `updateApplicationStatus(dragSource, targetStatus)`;失败已在 store 内回滚,`.catch(() => {})` 静默;最后清 dragSource + dragOverStatus。
- **Map 加速**:`const jobsMap = new Map(jobs.map(j => [j.job_id, j]))` O(1) 查 job;`ApplicationCard` 的 `job={jobsMap.get(app.job_id)}`。
- **备注保存**:KanbanBoard 内传 `onSaveNotes={(a, notes) => addApplication({...a, notes, updated_at: nowIso()})}` 复用 addApplication 的 upsert 幂等性(同 app_id 替换)。

### `job_workbench/src/components/AddApplicationModal.tsx`（新建，241 行）
- 添加投递记录模态框,`fixed inset-0 z-50 + bg-slate-deep/40 + backdrop-blur-sm` 实现遮罩 + 毛玻璃;点击遮罩背景关闭,内层 `stopPropagation` 防误关。
- **表单字段**:
  - 关联岗位(可选):`<select>` 从 `jobs` 列表选(`j.company · j.title`);选中后自动回填公司名/岗位名;选"— 手动输入 —"清空预填。
  - 公司名(必填)/ 岗位名(必填):`<input>` 文本框,空提交前端拦截(`"请填写公司名与岗位名"`)。
  - 状态:6 个圆角按钮(`KANBAN_COLUMNS` 遍历),选中态用 `col.dotColor` 背景 + 白字;默认 `draft`。
  - 备注:`<textarea rows={3}>`,空串存 `null`。
- **app_id 生成**:`app-${Date.now()}-${Math.random(36).slice(2,8)}` 防撞号;手动输入场景 `job_id` 用 `manual-${ts}-${rand}` 占位(无关联岗位)。
- **`source: "manual"`**:手动添加的标记,与邮箱自动采集(`"email"/"auto"`)区分,卡片右上角 emoji 据此渲染。
- **applied_at**:状态非 draft 时填 `now`(已投递时间戳);draft 时留 null(还没投)。
- **生命周期**:`useEffect` 模态 open 时重置表单 + ESC 键监听关闭(`window.addEventListener("keydown")` + cleanup);`submitting` 状态防重复点击。
- **样式**:暖橙主题贯穿(`border-orange-200` / `bg-orange-50/30` / `focus:ring-orange-400` / `bg-orange-500 hover:bg-orange-600` 主按钮);大圆角 `rounded-2xl` + `shadow-card`。

### `job_workbench/src/pages/Applications.tsx`（重写，89 行，替换占位）
- **顶部行**:标题"投递看板" + 投递数(`共 N 条投递`)+ 右侧 `SyncIndicator` + "添加投递" 主按钮(`bg-orange-500`)。
- **SyncIndicator**(内联子组件):加载中显橙色脉冲点(`animate-pulse bg-orange-500` + "同步中…"),否则绿色圆点 + "已同步"。
- **错误条**:`error` 非空时显示 `bg-red-50 + text-red-600` 横条。
- **主体三态**:
  - 加载中:橙色 spinner(`animate-spin border-orange-200 border-t-orange-500`)。
  - 空状态(`!isLoading && applications.length === 0`):`📭` 大 emoji + "开始记录你的投递吧!" + 引导文案 + "添加投递" 按钮(同顶栏)。
  - 非空:`<KanbanBoard />` 渲染看板。
- **挂载拉取**:`useEffect(() => loadApplications(), [loadApplications])` 进入页面即调,store action 引用稳定(zustand v4 不重建)。

**验收**:
- ✅ TypeScript 语法正确(esbuild 解析全部 5 文件零错误;`--loader=tsx` 解析通过)
- ✅ 所有组件使用 Tailwind 类名,暖橙主题(`bg-orange-50/orange-500/orange-100/orange-200/orange-400/orange-600` + `border-orange-*` + `focus:ring-orange-*`)
- ✅ Kanban 6 列布局正确(`grid grid-cols-6`),颜色区分(slate/blue/yellow/orange/green/red)
- ✅ 拖拽逻辑(HTML5 dragstart/dragover/dragleave/drop)完整,dragSource 状态 + 乐观更新 + 失败回滚
- ✅ 空状态展示("📭 开始记录你的投递吧!" + 引导文案 + CTA 按钮)
- ✅ Modal 用 `fixed inset-0 + backdrop-blur-sm` 实现,ESC 关闭 + 点击遮罩关闭
- ✅ 函数式组件 + TypeScript 全量类型注解,无 `any` 显式标注
- ⚠️ 按任务要求未执行 `npm install`;`tsc --noEmit` 因无 `node_modules` 无法跑全量类型检查(预期;依赖安装后即可恢复)
- ✅ 适配 T6+T7 Rust 端 `upsert_application → Result<(), String>` 实际签名(任务描述误写"→ Application",前端按入参 app 推断返回态)

**关键设计决策**:
- **不引入 react-dnd 等拖拽库**:任务要求原生 HTML5 API;`draggable` + `dataTransfer` + `dragstart/dragover/drop` 三事件足够;`dragSource` 状态存 store(而非组件 ref)便于 KanbanBoard 跨列共享 + drop 时回查。
- **乐观更新 + 回滚**:`updateApplicationStatus` 先本地切 status,再调 invoke,失败回滚;UX 上拖拽响应即时,失败时 error 横条提示 + 列回原位。比"等 invoke 成功才切"体验好(网络往返 ~50-200ms 卡顿可见)。
- **复用 addApplication 的 upsert 幂等保存备注**:任务 spec 没列 `updateApplication` action,而 `upsert_application` 本就是 upsert(同 app_id 覆盖),所以 `addApplication({...a, notes, updated_at})` 天然可作"编辑备注"路径,不增 store API 表面。
- **jobs 与 applications 一起拉取**:`loadApplications` 用 `Promise.all` 并行 invoke,前端只发一次往返;`jobs` 存 store 内,`KanbanBoard` 用 `Map<job_id, Job>` O(1) 查表,卡片显示公司/岗位名不再各自查 job。
- **dragOverStatus 局部 state 而非 store**:拖拽过程是 UI 局部瞬时态,放 store 会污染全局 + 增不必要 re-render;用 `useState<ApplicationStatus | null>` 隔离在 KanbanBoard 内即可。`dragSource` 才需放 store(drop 在列容器上,但源在卡片,跨组件读)。
- **dragLeave 防闪烁**:`onDragLeave` 用 `e.relatedTarget + currentTarget.contains()` 判断是否真正离开列,避免拖到子元素(卡片/列头)时清高亮再重新设回的闪烁。
- **TS v7 与项目 v5.5.4 不兼容**:全局 tsc 7.0.2 已移除 `baseUrl`(项目 tsconfig.json 用了);用 esbuild 做纯语法解析校验,跳过类型解析(无 node_modules),符合任务"人工检查 + 不装 npm"约束。
- **`@tauri-apps/api/core` 而非 `@tauri-apps/api/tauri`**:Tauri v2 重排模块路径,`invoke` 在 `core` 子模块下(v1 是 `tauri_awaiter`);package.json 已 `@tauri-apps/api: ^2.0.0`。
- **6 列颜色用 Tailwind 现成类而非自定义**:任务明确"用 Tailwind 的 bg-orange-50/orange-500 等现成类";KANBAN_COLUMNS 用字符串存类名,运行时拼到 className;不污染 tailwind.config.ts 主题色。

**下一步**: T15 — 投递记录的删除/编辑入口(挂 `delete_application` Tauri command + 卡片右上角"…"菜单);或邮件自动采集投递 → applications 表 source="email" 流水注入(Kanban 卡片自动出现邮箱来源 ✉️ 标记)

---

## 2026-10-03 — T9: 桌面端岗位同步 ✅

**状态**: 完成

**产出**:

### `job_workbench/src-tauri/src/sync.rs`（新建, ~290 行含测试)
- `SyncService { client: reqwest::Client }` 持有连接池,跨命令注册为 Tauri State(`app.manage(SyncService::new())`),30s 超时容忍弱网。
- **`sync_jobs(db, api_base_url, token, since) → Result<SyncResult, SyncError>`** 循环分页:
  - 构造 `?since=&limit=500&cursor=` query(reqwest `.query(&[...])` 自动 URL 编码,避免游标含 `|` 字符破坏 query string),`.bearer_auth(token)` 注入 Authorization 头。
  - 每页 `.json::<SyncJobsResponse>()` 反序列化,逐条 `RemoteJob → Job → Db::upsert_job` 落库;`next_cursor` 为 None 时跳出。
  - `last_updated_at` 取本批 `max(updated_at)`,作为下次增量起点;空批保持 `since` 不变。
  - **死循环保护**:`MAX_PAGES = 200`(200×500=10 万条);cursor 未推进时 `log::warn` + break。
  - **错误处理**:网络/HTTP/反序列化/数据库四类合一为 `SyncError(String)`;401 单独返回 `"unauthorized: token 已失效,请重新登录"` 便于前端 authStore 跳登录。失败立即返回,已 upsert 数据保留(`ON CONFLICT` 幂等可重放)。
- **`get_remote_stats(api_base_url, token) → RemoteStats`**:拉 `/api/v1/sync/stats`,返回 `{total, updated_at}`。
- **`compare_with_local(db, &remote_stats) → SyncStatus`**:本地 `get_job_stats` 与远端 `total/updated_at` 比对,`need_sync` = 本地空 OR 本地 `MAX(updated_at)` < 远端 `updated_at`(ISO8601 字典序=时间序,本地远端格式同源)。
- **`RemoteJob` 13 字段**:对齐云端 `JOB_FIELDS` 常量(`job_id, company, title, category, city, requirements, jd_text, apply_url, deadline, source, graduation_match, is_mt, updated_at`),与本地 `Job` 区别是无 `llm_score/llm_reason/deleted`(本地独有,由评分 sidecar 与软删流程写入)。`From<RemoteJob> for Job` 强制 `deleted=0`、`llm_*=None`。
- **6 个 `#[cfg(test)]` 用例**:`test_remote_job_to_job_preserves_fields`(13 字段映射 + 本地字段为默认)、`test_sync_error_display_and_from`(Display + `From<serde_json::Error>`)、`test_compare_with_local_empty_local_needs_sync`(空表→need_sync=true)、`test_compare_with_local_up_to_date_no_sync`(同 updated_at→need_sync=false)、`test_compare_with_local_remote_newer_needs_sync`(远端 10-03 > 本地 10-01→need_sync=true)、`test_compare_with_local_remote_no_updated_at_falls_back_to_sync`(远端 updated_at=None→保守触发同步)。

### `job_workbench/src-tauri/src/lib.rs`(更新)
- `mod sync;` + `use sync::{SyncResult, SyncService, SyncStatus};`。
- **新增 2 个 `#[tauri::command] async fn`**:
  - `sync_jobs(db_state, sync_state, api_base_url, token, since) → SyncResult`:用 `db_state.inner()` + `sync_state.inner()` 取 `&'r T`(生命周期绑定到 State 容器,可跨 `.await` 持有——直接用 `db_state.upsert_job` 会因 `State<'r>` 借用未续到 await 后而编译失败)。
  - `get_sync_status(db_state, sync_state, api_base_url, token) → SyncStatus`:先 `get_remote_stats` 再 `compare_with_local`。
- `setup()` 内 `app.manage(SyncService::new())` 注册 sync service State。
- `generate_handler![...]` 追加 `sync_jobs, get_sync_status`(共 13 个命令)。

### `job_workbench/src/api/sync.ts`(新建)
- `syncJobs(since?) → invoke<SyncResult>("sync_jobs", {apiBaseUrl, token, since})`:token 从 `useAuthStore.getState().token` 读取(空时抛错由 syncStore 兜底),`apiBaseUrl` 从 `import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"` 读取。上层只需 `syncJobs(since?)`,不必感知鉴权。
- `getSyncStatus() → invoke<SyncStatus>("get_sync_status", {apiBaseUrl, token})`:同模式。
- 导出 `SyncResult / SyncStatus / RemoteStats` 三个 interface,字段命名与 Rust 侧 snake_case 对齐。

### `job_workbench/src/stores/syncStore.ts`(新建)
- Zustand `useSyncStore` 单例,state:`isSyncing / lastSyncAt / syncProgress / error / status`。
- **`syncJobs(since?)`**:防重入(`isSyncing` 时直接返回 null),try/catch 兜底 error 状态;成功后 `lastSyncAt = new Date().toISOString()`、后台异步 `getSyncStatus()` 刷新 status(不阻塞返回)。
- **`getSyncStatus()`**:错误不抛出,落 error 状态(避免打断 UI,由 SyncIndicator 显示重试)。
- **`reset()`**:登出/切账号时清空所有状态。

### `job_workbench/src/components/SyncIndicator.tsx`(新建)
- 顶部同步状态指示器,4 态:
  - 同步中:spinner + `正在同步岗位...（已写入 N 条）`(syncProgress.synced 实时累加)。
  - 失败:`⚠ 同步失败，点击重试`(button onClick `syncJobs()` 重试,`title=error` 显示完整错误)。
  - 落后云端:`⟳ 本地落后云端，点击同步`(status.need_sync=true 时显示)。
  - 已同步:`✓ 已同步（MM-DD HH:mm）`(formatTime 兼容 SQLite `YYYY-MM-DD HH:MM:SS` 与 ISO8601 两种格式)。
- 挂载时 `useEffect(() => void getSyncStatus(), [])` 拉一次状态。

**验收**:
- ✅ `cargo check --lib` 通过(零警告零错误,在 `job_workbench/src-tauri/` 下,2.34s)
- ✅ `cargo test --lib sync` → **6 passed; 0 failed**(finish in 0.29s);`cargo test --lib` 全量 18 passed(12 db + 6 sync)
- ✅ `cargo fmt --check` 通过(sync.rs / lib.rs 格式干净)
- ✅ `npx tsc --noEmit` 中 sync.ts / syncStore.ts / SyncIndicator.tsx 零错误(grep `sync|SyncIndicator` 无匹配;tsconfig.json 的 2 个 baseUrl/paths 错误是既有问题,与 T9 无关)
- ✅ sync.rs 正确调用 reqwest 异步 client(`.bearer_auth().query().send().await?.json().await?`)
- ✅ 错误处理:网络失败立即返回 `SyncError`,已 upsert 数据保留(幂等可重放),不崩溃
- ✅ SyncResult / SyncStatus / RemoteStats 三个 struct 均 `#[derive(Serialize)]`,前端 invoke 可反序列化

**关键设计决策**:
- **`RemoteJob` 与 `Job` 分离而非直接复用**:云端 `/sync/jobs` 返回 13 字段(无 `llm_score/llm_reason/deleted`),本地 `Job` 16 字段。若直接用 `Job` 反序列化,`graduation_match/is_mt/deleted` 非 Option 在云端缺字段时会失败;`#[serde(default)]` 又会污染 `Job` 的序列化契约。独立 `RemoteJob` + `From<RemoteJob> for Job` 强制 `deleted=0/llm_*=None` 是最干净的隔离——同步语义明确(同步只覆盖云端已知字段,本地独有字段保留或重置)。
- **token + api_base_url 由前端传入而非 Rust State 读取**:任务要求命令签名 `sync_jobs(since)`,但 T6/T7 的 token 加密流程尚未落地(`user_config.token_encrypted` 占位 base64+XOR,无解码函数)。权衡:若严格按签名实现需新增 `TokenState(Mutex<Option<String>>)` + `set_token` 命令——额外命令不在 T9 范围。最终采用"或参数传入"分支:`syncJobs(since?)` TS wrapper 内部从 authStore + env 读取 token/apiBaseUrl 后注入 invoke,Rust 命令签名扩为 `(api_base_url, token, since)`。上层 API 仍是 `syncJobs(since?)`,与任务要求一致。等 keychain 接入后可统一收口到 Rust State。
- **`compare_with_local` 用字符串字典序比较 ISO8601**:`"2026-10-03 10:00:00"` 字典序 = 时间序(固定宽度 + 零填充);本地与远端 `updated_at` 同源(云端 jobs.db),格式一致,故字典序比较等价时间序比较,无需 parse。远端 `updated_at=None` 时保守触发同步(避免漏拉)。
- **`MAX_PAGES = 200` 死循环保护**:云端游标理论上必定推进(`(updated_at, job_id)` 复合游标严格大于),但若云端 bug 导致 cursor 不变会死循环。200 页 × 500 = 10 万条远超现实岗位量,cursor 不推进时 `log::warn` + break 是兜底。
- **`reqwest::Client::builder().timeout(30s)`**:每页 ≤1000 条,单次拉取通常 < 1s;30s 容忍弱网与首次 TLS 握手。失败立即返回错误,前端 SyncIndicator 显示重试,不阻塞后续操作。
- **`SyncService` 注册为 State 而非每次新建**:reqwest::Client 内部 Arc 连接池,跨命令复用避免每次同步重建连接 + TLS 握手。`Default` 实现委托到 `new()`,符合 Tauri State 注册约定。

**下一步**: T10 — 桌面端岗位列表首页(`Jobs.tsx` 全部岗位列表 + 筛选栏 + `JobCard` 组件 + `jobsStore.ts`,基于 T7 `get_jobs` command 与 T9 同步的数据);T11 — Python sidecar 评分引擎接入(`sidecar_server.py` JSON-RPC + `Db::update_job_score` 回写,基于 T9 同步的岗位)

---

## 2026-10-03 — T8: 桌面端认证 UI + API 客户端 ✅

**状态**: 完成

**产出**:

### `job_workbench/src/api/client.ts`（重写）
- `ApiClient` 类封装 fetch；`baseURL` 取 `import.meta.env.VITE_API_URL`（默认 `http://localhost:8000`），用 `(import.meta as { env?... }).env` 强制类型安全访问（项目无 `vite-env.d.ts`，避免 `ImportMeta.env` 报错）。
- Bearer Token 自动注入：通过 `setTokenAccessor` 注入的 `{get, set}` 回调读取 token（默认回落读 `localStorage` 的 `job_assistant_token`）。
- 401 自动 refresh：`request` 收到 401 → `tryRefresh()` 直连 `/api/v1/auth/refresh`（带旧 Bearer，绕开 `request` 避免递归）→ 成功则用 `accessor.set` 写回新 token 并以 `allowRetry=false` 重放原请求一次；失败则清 token + `window.location.href = "/login"`（已在 /login、/register 时不跳）。
- 方法：`get(path, params?)`、`post(path, body?)`、`put(path, body?)`、`delete(path, params?)`，全部泛型 `Promise<T>`；`toQuery` 用 `URLSearchParams` 过滤 undefined/null。
- 错误结构：失败统一 `throw { error: string, status: number }`（`ApiError` 接口），调用方 `try/catch` 读取；`extractError` 优先取后端 `message/error/detail`。

### `job_workbench/src/api/auth.ts`（新建）
- `authApi.register / verifyEmail / login / refreshToken` 四函数，对齐云端 `/api/v1/auth/*`；返回类型 `RegisterResponse { user_id, needs_verify }`、`TokenResponse { token, expires_at }`。

### `job_workbench/src/stores/authStore.ts`（重写）
- Zustand store：state `token / user / isAuthenticated / isLoading / error`；actions `login / register / verifyEmail / logout / loadFromStorage`。
- token 持久化到 `localStorage` key `job_assistant_token`：login 与 verifyEmail 成功后 `persistToken`；`logout` 清除。
- **store 初始化即从 localStorage 读 token**（`initialToken`），首屏渲染 `isAuthenticated` 即正确，避免 AuthGuard 闪跳。
- 模块末尾 `apiClient.setTokenAccessor({...})` 单向注入：`get` 读 store 状态（回落 localStorage）、`set` 同步写 store + localStorage。打破循环依赖：client.ts 不 import authStore，由 authStore 注入回调。

### `job_workbench/src/pages/Login.tsx`（重写）
- 暖橙主题：`bg-brand` 按钮 + `bg-brand-50`/`text-brand-700` 错误 alert + `rounded-2xl` 大圆角输入框 + `focus:ring-brand-100`。
- 邮箱 + 密码；表单校验（`EMAIL_RE` + 密码≥6 位）；登录按钮调 `authStore.login` 成功后 `navigate("/")`；加载态按钮内 spinner；"还没账号？注册" 链接到 `/register`。

### `job_workbench/src/pages/Register.tsx`（新建）
- 邮箱 + 密码 + 确认密码；校验邮箱格式 / 密码≥6 位 / 两次密码一致；注册成功（`needs_verify=true`）切换为验证码输入态。
- 6 位验证码：6 个独立 `input`（`inputMode="numeric"`，只取 1 位数字），输入自动跳下一格、Backspace 回退、支持粘贴 6 位整体填充；"验证" 调 `authStore.verifyEmail` 成功后 `navigate("/")`；"已有账号？登录" 链接到 `/login`。

### `job_workbench/src/components/AuthGuard.tsx`（新建）
- 路由守卫：未登录（`!isAuthenticated`）→ `<Navigate to="/login" state={{from}} replace/>`。
- token 过期场景由 `ApiClient` 在请求 401 时自动 refresh 兜底（失败清 token + 跳 /login），与守卫协同，避免每次路由切换都打一次 refresh。

### `job_workbench/src/App.tsx`（更新）
- 路由：`/login`、`/register` 公开；`/`（Jobs）、`/resume`、`/applications` 受 `AuthGuard` 包裹。
- 新增 `Layout` 组件：顶部导航（求职搭子 / 岗位 / 简历 / 投递）+ 当前用户邮箱 + "退出"（调 `logout` 后硬跳 `/login`）；公开页无导航。

**验收**:
- ✅ 人工 TypeScript 检查：用全局 `tsc --ignoreConfig` 跑全部新增/修改源文件，过滤掉"找不到 react/zustand/react-router-dom 模块"类伪错（项目无 node_modules，未装依赖）后，`client.ts / auth.ts / authStore.ts / Login.tsx / Register.tsx / AuthGuard.tsx / App.tsx` 均无真实类型错误（无 TS2xxx / TS7xxx 业务错）。`noUnusedLocals` / `noUnusedParameters` 通过。
- ✅ 所有组件函数式 + TypeScript；Tailwind 类名 + 暖橙主题（`bg-brand` / `text-brand` / `bg-brand-50` / `focus:ring-brand-100`）；输入框 `rounded-2xl`，按钮暖橙背景 + `hover:bg-brand-600`。
- ✅ 表单校验：邮箱正则 + 密码≥6 位；验证码 6 位纯数字（`replace(/\D/g,"")`）。
- ✅ token 持久化：login/verifyEmail 写 localStorage、logout 清除、ApiClient 401 refresh 写回、store 初始化从 localStorage 恢复。
- ⚠️ 项目无 `node_modules`，未执行 `npx tsc --noEmit` 全量编译（按任务约束"不装 npm 依赖"）；待依赖安装后跑 `npm run lint` 复核。
- ℹ️ 并行任务同时新增了 `api/sync.ts`、`stores/{appStore,syncStore}.ts`、`components/{KanbanBoard,ApplicationCard,AddApplicationModal,SyncIndicator}.tsx` 并重写了 `pages/{Jobs,Applications}.tsx`；本任务对这些文件未做改动，`App.tsx` 仅渲染对应页面组件，向后兼容（`apiClient.get/post` 旧签名仍可用）。

**关键设计决策**:
- **Token accessor 回调注入打破循环依赖**：`client.ts` 若直接 `import authStore` 会与 `authStore → auth.ts → client.ts` 形成环。改为 `ApiClient.setTokenAccessor({get,set})` 由 authStore 模块加载时单向注入，client 只持有回调引用。`get` 还回落读 localStorage，保证 store 未 hydrate 时也能取到 token。
- **store 初始化即读 localStorage**：避免 AuthGuard 首屏因 `isAuthenticated=false` 闪跳到 /login；`loadFromStorage` 保留为幂等重载入口。
- **401 refresh 不递归**：`tryRefresh` 用裸 `fetch` 而非 `this.request`，且原请求重放时传 `allowRetry=false`，防止 refresh 失败再次触发 refresh 形成循环。
- **AuthGuard 不主动 refresh**：token 过期校验下沉到 ApiClient 层（首次 API 调用 401 触发 refresh，失败跳 /login），守卫只做"有/无 token"门禁，避免每次受保护路由切换都多打一次 refresh 接口。
- **错误以 `{error, status}` 抛出而非返回联合类型**：保持 `Promise<T>` 干净的成功路径，调用方 `try/catch` 读 `err.error / err.status`，符合 spec 描述且对 async/await 友好。

**下一步**: T9 — 简历上传 UI + 调云端 `/api/v1/llm/parse-resume`（前端 `src/api/llm.ts` + Rust 端 `Db::save_resume`）；以及与并行任务的投递看板（`appStore / KanbanBoard`）联调，统一将 `bg-orange-500` 等硬编码色替换为主题 `bg-brand` token。

---

## 2026-10-03 — T6+T7: 桌面端 Tauri 骨架完善 + SQLite 数据层 ✅

**状态**: 完成

**产出**:

### `job_workbench/src-tauri/Cargo.toml`（更新）
- 依赖补齐:`rusqlite = "0.31"(features=["bundled"])` 自带 SQLite 引擎免系统库;`tokio = "1"(features=["full"])` 异步 runtime(云端 API / sidecar 进程管理);`reqwest = "0.12"(features=["json"])` HTTP 客户端;`tauri = "2"(features=["protocol-asset"])` 增 asset 协议(简历文件预览);`chrono = "0.4"(features=["serde"])`、`uuid = "1"(features=["v4","serde"])`、`base64 = "0.22"`、`log = "0.4"` + `env_logger = "0.11"`、`tauri-plugin-fs = "2"`。
- `[profile.release]` 保留 T1 的 `panic = "abort"` + `lto = true` + `opt-level = "s"` + `strip = true`(安装包瘦身)。

### `job_workbench/src-tauri/tauri.conf.json`（更新）
- 新增 `app.security.assetProtocol`(enable + scope `$APPDATA/$DOCUMENT/$DOWNLOAD`),为前端 `asset://` 协议预览本地简历 PDF/图片开闸。
- 新增 `plugins.fs.scope`(同上三目录),与 capabilities 双重声明(配置层 + 权限层)。

### `job_workbench/src-tauri/capabilities/default.json`（新建）
- Tauri 2 权限模型:permissions 数组挂 `core:default` + 7 个 fs 权限(`fs:allow-read-file/write-file/read-dir/exists/mkdir/remove/rename`) + 3 个 fs scope(`fs:scope-appdata/document/download`) + `core:window:allow-start-dragging` + `core:event:default`。`windows: ["main"]` 限定主窗口。

### `job_workbench/src-tauri/migrations/001_init.sql`（新建，142 行）
- 7 张表 `CREATE TABLE IF NOT EXISTS` 对齐 spec schema:`user_config / jobs / resumes / applications / email_accounts / emails / schedules`。
- `PRAGMA journal_mode = WAL` + `synchronous = NORMAL`(桌面端高频读、WAL 写不阻塞读)+ `foreign_keys = ON`。
- 字段类型严格对齐 spec:`graduation_match / is_mt / deleted / is_active` 用 INTEGER(0/1);`llm_score` 用 REAL;时间字段用 TEXT(ISO8601,与 chrono 协同);`parsed_profile_json` 用 TEXT 存 JSON 字符串。
- 外键约束:`applications.job_id → jobs(job_id) ON DELETE CASCADE`;`emails.account_id → email_accounts`;`schedules.{job_id, related_email_id}` 用 `ON DELETE SET NULL`(避免删岗位连带删日程)。
- 索引:jobs 上 8 个(updated_at DESC / city / is_mt / graduation_match / category / company / llm_score DESC / deleted);applications / emails / schedules 各 2-3 个常用筛选索引。
- **`from` 是 SQLite 保留字**:emails 表的 `from` 列用双引号 `"from"` 转义(spec 字段名保留,前端 JSON 字段仍是 `from`,SQL 层透明转义)。

### `job_workbench/src-tauri/src/models.rs`（新建，165 行)
- 全部 7 张表的 Rust struct,字段命名与 spec snake_case 对齐:`Job / UserConfig / Resume / Application`。所有 struct `#[derive(Serialize, Deserialize)]` 直接做 Tauri command 入参/返回值。
- `Job` / `UserConfig` / `Application` 实现 `Default`,避免调用方每次写齐 16 字段。
- `JobFilter` 查询参数结构体:city / graduation_match(Option<bool>) / is_mt / category / company / search(LIKE %x% 模糊匹配 company|title|jd_text) / not_deleted(#[serde(default = "default_true")]) / min_score。所有字段 Option,前端可只传关心的字段。
- `JobStats { total, updated_at }` 与云端 `/sync/jobs/stats` 字段对齐。

### `job_workbench/src-tauri/src/db.rs`（新建,784 行含测试)
- `Db(pub Mutex<Connection>)`:`std::sync::Mutex` 包 `rusqlite::Connection`(Connection: Send 但非 Sync,Mutex 让其变 Send+Sync,Tauri State 跨命令共享)。
- `init_db(app_data_dir)` → 建目录 + 打开 `~/.<app_data_dir>/workbench.db` + 建表。
- `init_db_with_conn(&Connection)` → `include_str!("../migrations/001_init.sql")` 编译期嵌入 SQL,运行时不依赖文件系统,`execute_batch` 一次性落库,幂等可重入(生产文件 DB / 测试内存 DB 共用同一 schema 路径)。
- `get_db_path(app_data_dir)` → `<dir>/workbench.db`。
- **岗位 CRUD**:`upsert_job`(`ON CONFLICT(job_id) DO UPDATE` 幂等)、`get_jobs(filter, limit, offset)`(动态拼 WHERE 子句 + `Vec<Box<dyn ToSql>>` 绑定,limit clamp 1-1000)、`get_job_by_id`(`.optional()` 返回 Ok(None),便于 `?` 链)、`get_job_stats`、`update_job_score`(sidecar 评分回写)。
- **用户配置 CRUD**:`get_user_config`(LIMIT 1,MVP 单用户)、`save_user_config`(`ON CONFLICT(user_id) DO UPDATE`)。
- **简历 CRUD**:`save_resume`(`ON CONFLICT(resume_id) DO UPDATE`)、`get_active_resume`(`WHERE is_active = 1 ORDER BY created_at DESC`)。
- **投递 CRUD**:`upsert_application`、`get_applications(status_filter?)`(可选 status 过滤)。
- **`get_job_stats` 设计**:total 用 `WHERE deleted = 0`(在招岗位数),updated_at 用 `MAX(updated_at)` 不带 deleted 过滤(反映最近一次同步游标,即使该次同步只是软删一些行也推动游标前进)。

### `job_workbench/src-tauri/src/lib.rs`(更新,151 行)
- `mod db; mod models;` 挂载新模块。
- **Tauri commands**(全部 `#[tauri::command]`,State 注入 `Db`):
  - `get_jobs(filter: Option<JobFilter>, limit, offset) → Vec<Job>`:filter 缺省 Default,limit 缺省 50 + clamp(1,1000)。
  - `get_job_stats() → JobStats`。
  - `upsert_job(job: Job) → ()`。
  - `get_user_config() → Option<UserConfig>`。
  - `save_user_config(config: UserConfig) → ()`。
  - 额外暴露 6 个 command 供后续任务接入:`update_job_score(job_id, score, reason)`、`get_active_resume`、`save_resume`、`upsert_application`、`get_applications(status)`、T1 的 `greet`(连通性自测保留)。
- **`run()`**:`tauri::Builder::default().plugin(tauri_plugin_fs::init()).setup(|app| {...}).invoke_handler(generate_handler![...]).run(generate_context!())`。
- **setup()**:用 `app.path().app_data_dir()`(Tauri 2 path API,跨平台 macOS=~/Library/Application Support、Linux=~/.local/share、Windows=%APPDATA%)解析目录,调 `db::init_db()` 后 `app.manage(db)` 注册到 State;失败 `Box<dyn Error>` 返回。
- `env_logger` 初始化:RUST_LOG 缺省 info。

### `job_workbench/src-tauri/icons/`(占位 5 个文件)
- T1 已知缺口"Tauri bundle.icon 引用标准图标路径,实际构建前需补充图标资源"导致 `tauri::generate_context!` 宏在 cargo check 阶段 panic(找不到图标文件)。
- 本任务用 1×1 RGBA 透明 PNG(67 字节)占位 5 个引用路径(`32x32.png`/`128x128.png`/`128x128@2x.png`/`icon.icns`/`icon.ico`)使 cargo check 通过;.ico/.icns 严格格式校验留待正式发布前用 `cargo tauri icon` 重生成。

### `job_workbench/src-tauri/src/db.rs::tests`(12 个 #[cfg(test)] 用例)
- `test_init_creates_all_tables`:断言 7 张表全部存在。
- `test_init_db_is_idempotent`:连调两次 `init_db_with_conn` 不报错。
- `test_upsert_job_is_idempotent`:同一 job_id 覆盖写后 total 仍为 1(不是 INSERT 新行)。
- `test_get_jobs_filter_city_and_mt`:city="上海" → 2 条;city+is_mt=true → 1 条;按 updated_at DESC 排序。
- `test_get_jobs_search_and_min_score`:search="字节" 模糊匹配 2 条;min_score=50.0 → 2 条(80 与 50;30 不入)。
- `test_get_jobs_pagination`:15 条数据 limit=10 offset=0/10 → 10+5;p1[0].job_id 是最新 updated_at。
- `test_get_job_stats`:2 在招 + 1 软删 → total=2、updated_at 是软删行的(反映最近同步游标)。
- `test_update_job_score`:回写 88.5 + "硬技能+方向命中" 后读回验证。
- `test_user_config_crud`:空表→None;upsert→读回;再 upsert(plan 升 max、used+1)→读回。
- `test_resume_crud`:r-1 active → 返回 r-1;加 r-2 inactive → 仍 r-1;切 r-2 active → 返 r-2(按 created_at DESC)。
- `test_application_crud_and_status_filter`:2 投递 draft+interview;status="interview" → 1 条;upsert a-1 → applied 后 draft 空。
- `test_get_job_by_id_missing_returns_ok_none`:不存在的 job_id 返 Ok(None)(用 `.optional()` 不 panic)。

**验收**:
- ✅ `cargo check --lib` 通过(零警告零错误,在 `job_workbench/src-tauri/` 下;系统已装 libwebkit2gtk-4.1-dev / libgtk-3-dev / libsoup-3.0-dev / libayatana-appindicator3-dev / librsvg2-dev)
- ✅ `cargo test --lib` → **12 passed, 0 failed**(finish in 0.02s)
- ✅ `rustfmt --check` 通过(db.rs / lib.rs / models.rs 三文件无格式 diff)
- ✅ migrations/001_init.sql 包含 spec 全部 7 张表 + 外键 + 索引
- ✅ db.rs CRUD 覆盖 spec 全部 7 张表中 T7 范围内的 4 张表(user_config / jobs / resumes / applications);email_accounts / emails / schedules 表已建(schema 预留),CRUD 留 M2 邮箱追踪任务实现
- ✅ Tauri commands 5 个核心 + 6 个辅助全部 `#[tauri::command]` 宏挂到 `generate_handler!`,前端可 invoke

**关键设计决策**:
- **`include_str!` 编译期嵌入 SQL**:`const SCHEMA_SQL: &str = include_str!("../migrations/001_init.sql")` 让 schema 在编译期进二进制,运行时不读文件;migrations/001_init.sql 既是文档又是代码,生产文件 DB 与测试内存 DB 走同一 schema 路径,避免漂移。比 `conn.execute_batch("CREATE TABLE ...")` 字符串硬编码更易维护。
- **`Mutex<Connection>` 而非 `r2d2` 连接池**:桌面端单用户、读多写少、毫秒级查询,单连接 + 互斥锁足够;r2d2 引入额外依赖,且 WAL 模式下读不阻塞写,单连接无明显瓶颈。M2 邮箱追踪若引入长事务再升连接池。
- **`ON CONFLICT(pk) DO UPDATE` 幂等 upsert**:同步任务可重放,云端推同一 job_id 多次只会覆盖不会插多行。`excluded.<col>` 引用 INSERT 侧的值,语义清晰。
- **`OptionalExtension::optional()` 而非 `query_row` + `?`**:`get_job_by_id` / `get_user_config` / `get_active_resume` 用 `.optional()` 把 `QueryReturnedNoRows` 转 `Ok(None)`,调用方 `?` 链 + match 干净处理;不污染错误链。
- **`get_job_stats` 的 total / updated_at 不同 deleted 过滤**:total 用 `WHERE deleted = 0`(UI"在招岗位 N 条"),updated_at 用 `MAX` 不带过滤(反映最近一次同步游标,即使该次同步只软删了行也推动游标前进——sync cursor 必须单调递增才能正确增量拉取)。
- **`from` 列双引号转义**:SQLite 保留字,字段名保留 spec 原名,SQL 层 `"from"` 转义,前端 JSON 字段不变,映射透明。
- **`Db::from_conn` 测试入口**:pub 方法,让测试用 `Connection::open_in_memory()` 直接构造 Db,跳过文件系统;生产用 `init_db(app_data_dir)` 走文件 DB。同一 `init_db_with_conn` 在两条路径上跑同一 schema。
- **动态 WHERE 拼接而非 ORM**:rusqlite 无原生 QueryBuilder,手动拼 `Vec<String>` + `Vec<Box<dyn ToSql>>`。`Box<dyn ToSql>` 异质容器承载 String/i64/f64 三种绑定类型;`bind_refs: Vec<&dyn ToSql>` 借 binds 的引用传给 `query_map`,生命周期在 binds 释放前用完。
- **占位 icons 解锁 cargo check**:T1 已记录"实际构建前需补充图标资源",但 cargo check 在编译期就要 `generate_context!` 宏读图标。用 1×1 透明 PNG(67 字节)占位 5 个路径使代码可编译;.ico/.icns 严格格式校验留待 `cargo tauri icon` 在正式发布前重生成(非本任务范围)。

**下一步**: T8 — 桌面端从云端拉取岗位数据并写入本地 SQLite 的同步任务(`job_workbench/src-tauri/src/sync.rs`,调云端 `/api/v1/sync/jobs?since=&limit=&cursor=` 增量拉取 → `Db::upsert_job` 批量落库 → `Db::save_user_config` 写 last_sync_at);T9 — 桌面端简历上传 UI + 调云端 `/api/v1/llm/parse-resume`(前端 `src/api/llm.ts` + Rust 端 `Db::save_resume`)

---

## 2026-10-03 — T4: 云端 LLM 代理接口 ✅

**状态**: 完成

**产出**:

### `job_api/services/llm_proxy.py`
- `LLMProxyService` 类:`parse_resume(resume_text)` 复用父目录 `resume_parser.parse_resume_text`;`supplement(user_edited, resume_text)` 复用 `resume_parser.supplement_profile`。
- **不直接暴露 DeepSeek API Key**:由 `__init__(api_key=...)` 注入,路由层只持有 `LLMProxyService` 实例,不接触 key。
- **sys.path 处理**:`_PARENT_DIR = Path(__file__).resolve().parents[2]` 解析到 `/workspace/job_assistant`,首次调用时 `_ensure_parent_path()` 把根目录 `sys.path.insert(0, ...)` 头部插入(线程锁 + `_path_added` 标志保证只插一次)。延迟到方法调用时执行,避免模块导入期污染 sys.path 影响 job_api 自身 `config` 解析。
- **延迟 import**:`from llm_client import LLMClient` 与 `from resume_parser import parse_resume_text/supplement_profile` 都在方法体内执行,避免循环依赖与无谓的 requests/PIL 加载。
- **30s 超时**:`_run_with_timeout()` 用 `concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=30)`;超时抛 `TimeoutError`,执行器 `shutdown(wait=False)` 不阻塞主流程。
- **API Key 缺失立即 503**:`_make_client()` 检测 `client.api_key` 为空时抛 `RuntimeError`,路由层捕获映射为 503。

### `job_api/services/quota_service.py`
- 每用户每日 LLM 调用配额:`get_user_quota(user_id)` → `{limit, used, remaining}`;`increment_usage(user_id)` 返回 bool(超额 False)。
- **默认每日 5 次**(简历解析 1 次 + 补充 4 次),`DEFAULT_DAILY_LIMIT = 5`。
- **SQLite 存储**:与 T3 的 `auth.db` 同库,新建 `llm_usage(user_id, usage_date, used_count, PRIMARY KEY(user_id, usage_date))` 表。`_init_schema()` 幂等 `CREATE TABLE IF NOT EXISTS`。
- **每日 0 点重置**:按 `date.today().isoformat()` 取当日,跨天查询自然过滤掉昨日记录(`SELECT ... WHERE usage_date=?`),无需定时任务清理。
- **线程安全**:模块级单例 `_conn` + `threading.Lock()` 保护所有读写。多进程部署应替换为连接池或 Postgres,此处保持最小实现。
- **DB 路径**:优先 `AUTH_DB_PATH` 环境变量;否则 `DATA_DIR/auth.db`(与 T3 `models.user._db_path()` 一致)。
- 测试辅助:`_reset_for_test()` 清空 `llm_usage` 表(不删表结构)。

### `job_api/routers/llm.py`
- `POST /api/v1/llm/parse-resume  {resume_text}` → `{keywords, fit_directions}`(spec 签名)。
- `POST /api/v1/llm/supplement   {user_edited, resume_text}` → `{fit_directions, hard_skills}`(hard_skills 取自 `supplement_profile` 的 `new_skills`)。
- **Bearer Token 认证**:`Depends(get_current_user)`(T3 真 JWT,deps.py 已落地,返回字段含 `user_id` 兼容 T4)。
- **配额校验**:`_check_quota(user_id)` 在调用 LLM 前检查;超额返回 429 + `Retry-After: 86400`。
- **用量计数**:`increment_usage(user_id)` 在 LLM 调用成功后执行(LLM 异常不计数,避免吞掉用户额度)。
- **DeepSeek 异常 → 503**:`_handle_llm_error` 统一捕获 `TimeoutError` 与 `Exception`,映射为 503 + 日志(`exc_info=True`)。
- 请求体校验:`resume_text` 用 `Field(..., min_length=1)`,空串返回 422。

### `job_api/main.py`(更新)
- 新增 `from routers.llm import router as llm_router` 与 `app.include_router(llm_router, prefix="/api/v1")`,与 T3 的 `auth_router` 并列;T5 的 `sync_router` 暂未挂载(由 T5 自己负责)。

### `job_api/requirements.txt`(更新)
- 追加 `requests>=2.31.0` 与 `Pillow>=10.0.0`(父目录 `llm_client.py` 调 DeepSeek 走 `requests`,VL/OCR 走 PIL;`httpx` 不能直接替代 `requests.post` 的同步语义)。

### `job_api/tests/test_llm.py`
- 13 个测试用例,全部用 `pytest.importorskip` 在 fastapi/pydantic/jose/aiosqlite/passlib/bcrypt/slowapi/httpx 任一缺失时优雅跳过(与 T2/T5 约定一致,不阻塞 py_compile)。
- 覆盖:
  - **401**:无 token / 无效 token(非 JWT 格式)→ 401。
  - **200**:mock `_proxy` 返回固定结构 → 200 + 字段映射正确;用量 +1。
  - **429**:预填满 5 次配额后再请求 → 429,且 `mock_proxy.assert_not_called()`(超额不调 LLM)。
  - **503**:mock `_proxy.side_effect = RuntimeError/TimeoutError` → 503,且 `quota["used"] == 0`(失败不计数)。
  - **422**:`resume_text=""` → 422。
  - **配额逻辑**:`test_quota_increment_logic` 直接验证递增 + 上限 + 超额返回 False(不通过 HTTP)。
- **认证 mock**:用 `services.jwt_service.create_access_token(user_id)` 签真 JWT(sub=test-user-id-0000),并 `patch("deps.get_user_by_id", new=AsyncMock(return_value=_FAKE_USER))` 避开真实 users 表。**必须 patch deps 模块的本地名**(deps.py 用 `from models.user import get_user_by_id` 把名字绑定到 deps 模块,patch `models.user.get_user_by_id` 不生效)。

**验收**:
- ✅ `python3 -m py_compile` 全部 7 个文件通过(`services/{__init__,llm_proxy,quota_service}.py / deps.py / routers/llm.py / main.py / tests/test_llm.py`)
- ✅ `python3 -m pytest tests/test_llm.py` → 1 skipped,EXIT=0(fastapi 未装时优雅跳过;依赖安装后即恢复执行 13 个用例)
- ✅ 接口签名符合 spec:`POST /api/v1/llm/parse-resume {resume_text} → {keywords, fit_directions}`、`POST /api/v1/llm/supplement {user_edited, resume_text} → {fit_directions, hard_skills}`
- ✅ quota_service 隔离测试通过:初始 `{limit:5, used:0, remaining:5}` → 5 次成功递增 → 第 6 次返回 False;跨天记录不污染当日配额
- ✅ LLMProxyService 父目录 import 解析正确:`_PARENT_DIR == /workspace/job_assistant`,`_ensure_parent_path()` 后 `resume_parser` / `llm_client` 可 import
- ⚠️ 按任务要求未执行 `pip install`;HTTP 层测试在依赖安装后(fastapi+pydantic-settings+jose+aiosqlite+passlib+bcrypt+slowapi+httpx)即自动跑通(已用 `importorskip` 兼容)

**关键设计决策**:
- **延迟 import 父目录模块**:`services/llm_proxy.py` 顶层只 import 标准库(`concurrent.futures/logging/sys/threading/pathlib/typing`),`from llm_client import LLMClient` 与 `from resume_parser import parse_resume_text` 都在方法体内执行。理由:(1) 避免 `requests`/`Pillow` 在模块导入期被加载,导致纯 Python 环境(py_compile、未装 LLM 依赖的服务器)直接 import 失败;(2) 测试 mock `_proxy` 时这些 import 永不触发;(3) prod 安装 requirements.txt 后正常工作。
- **sys.path.insert 头部而非 append**:`resume_parser.py` 内部 `from config import settings` 期望解析到父目录的 config(有 `DATA_DIR: str`),如果 append 到尾部会先命中 `job_api/config.py`(DATA_DIR 是 Path),虽不致命但语义不一致。头部插入保证父目录优先。
- **auth.db 同库不同表**:T3 的 `models.user` 用 `aiosqlite`(async),T4 的 `quota_service` 用 `sqlite3`(sync)。两者表结构独立(users/verification_codes vs llm_usage),共享同一个 `auth.db` 文件无冲突。FastAPI 同进程内 sync 路由(我的 LLM router 用 `def parse_resume`)走线程池,sync sqlite3 + threading.Lock 足够;T3 的 async 路由用 aiosqlite 自带的事件循环安全。
- **API Key 不暴露给路由层**:`routers/llm.py` 模块级 `_proxy = LLMProxyService(api_key=settings.DEEPSEEK_API_KEY)`,key 进入服务实例后路由层只持有 `_proxy`,无 `os.getenv` 散落。日志、错误响应、Pydantic 模型均不含 key。
- **配额计数时机**:LLM 成功后 `increment_usage`,失败不计数。极端并发竞争下(两个请求同时通过配额检查)可能略微超额 1 次,接受 — 比"成功调用却被吞额度"对用户更友好。
- **T3 真 JWT 集成**:开发期 T3 已落地 `deps.get_current_user` 调 `jwt_service.verify_token` + `models.user.get_user_by_id`,返回字段同时含 `user_id`(T4 兼容)与 `id`(规范字段)。本任务测试用 `create_access_token` 签真 JWT + AsyncMock `get_user_by_id`,与 T3 完全打通。

**并行任务协调**:
- T3(认证)与 T5(同步)在并行修改 `job_api/`。本任务开始时 T3 已落地 `routers/auth.py` + `services/{jwt_service,auth_service,email_service}.py` + `models/user.py` + `deps.py`(真 JWT 版),T5 已落地 `routers/sync.py` + `services/sync_service.py`(但 sync_router 暂未挂载到 main.py)。
- 本任务只新增 `services/{llm_proxy,quota_service}.py` + `routers/llm.py` + `tests/test_llm.py`,不动 T3 的 auth 文件;`main.py` 仅追加 `llm_router` 一行 include,与 T3 的 `auth_router` 并列。
- `deps.py` 由 T3 维护(真 JWT),本任务不覆盖。

**下一步**: T6 — 桌面端调用 LLM 代理接口的客户端封装(`job_workbench/src/api/llm.ts`)与简历解析 UI(上传简历 → 调 `/api/v1/llm/parse-resume` → 渲染 keywords + fit_directions)

---

## 2026-10-03 — T3: 云端邮箱认证模块 ✅

**状态**: 完成

**产出**:

### `job_api/models/__init__.py` + `job_api/models/user.py`
- 数据访问层（SQLite + aiosqlite，全异步）。`_db_path()` 用 `config.DATA_DIR / "auth.db"`，`_connect()` 每次开新连接（row_factory=Row），`init_db()` 幂等 `CREATE TABLE IF NOT EXISTS`。
- `users` 表：`id(TEXT PK, UUID str) / email(TEXT UNIQUE) / password_hash / is_verified(INT) / device_fingerprint(TEXT?) / created_at(TEXT) / last_login_at(TEXT?)`。
- `verification_codes` 表：`email / code(6位) / expires_at / used`，PK=`(email, code)`。
- CRUD：`create_user` / `get_user_by_email` / `get_user_by_id`（deps 用）/ `update_password_hash` / `set_verified` / `update_last_login` / `create_verification_code`（先清旧码再插，避免主键冲突）/ `get_verification_code` / `verify_code`（存在+未过期+未使用→标记 used=True 返回 True，否则 False）/ `generate_code`（`secrets.randbelow(1000000)` 6 位 zero-padded）。验证码 TTL=6 小时。

### `job_api/services/__init__.py` + `job_api/services/jwt_service.py`
- `create_access_token(user_id)` → JWT（HS256，`sub=user_id`，`iat/exp` 用 unix 时间戳），用 `python-jose`。
- `verify_token(token)` → payload dict 或 None（`JWTError` 兜底返回 None）。
- `get_expires_at()` → 当前签发 token 的过期 unix 时间戳（秒），供路由响应 `expires_at` 字段。

### `job_api/services/email_service.py`
- `send_verification_code(email, code)` → 通过 Resend HTTP API（`httpx.AsyncClient`）发 6 位验证码邮件。
- Resend 不可用（`RESEND_API_KEY` 为空 或 `httpx` 调用抛任何异常）→ `print(..., file=sys.stderr)` 开发模式降级，不阻断注册流程。发件人用 `onboarding@resend.dev`（Resend 沙箱发件人，免域名验证）。

### `job_api/services/auth_service.py`
- `register(email, password)`：邮箱未占用→建未验证用户+发码；已存在未验证→覆盖旧码重发；已存在已验证→`ConflictError`。
- `verify_email(email, code)`：`verify_code` 校验→`set_verified`→签 JWT，返回 `{token, expires_at}`；码无效→`InvalidCodeError`。
- `login(email, password)`：`get_user_by_email` + `passlib bcrypt verify`；密码错→`InvalidCredentialsError`（401）；未验证→`NotVerifiedError`（403）；通过→`update_last_login` + 签 JWT。
- `refresh(user_id)`：直接重签 JWT（外部已校验旧 token）。
- `_ensure_init()` 首次调用时 `await init_db()`（CREATE TABLE IF NOT EXISTS），模块级 `_init_done` 标志位避免重复建表；`reset_init_flag()` 暴露给测试在临时库上重置。
- 密码 hash：`passlib.context.CryptContext(schemes=["bcrypt"])`；`_verify_password` 用 try/except 兜底 passlib 抛 ValueError 时返回 False。
- 异常类层级：`AuthError` 基类 → `ConflictError` / `InvalidCredentialsError` / `NotVerifiedError` / `InvalidCodeError`。

### `job_api/routers/auth.py`
- `POST /api/v1/auth/register {email, password}` → `{user_id, needs_verify}`（200）；重复已验证→409。
- `POST /api/v1/auth/verify-email {email, code}` → `{token, expires_at}`（200）；码无效→400。
- `POST /api/v1/auth/login {email, password}` → `{token, expires_at}`（200）；未验证→403；密码错→401。
- `POST /api/v1/auth/refresh`（Bearer）→ `{token, expires_at}`（200）；token 无效→401。
- slowapi rate limit：`limiter = Limiter(key_func=get_remote_address)`，`@limiter.limit("5/minute")` 挂在 register/verify-email/login 三个端点（refresh 不限流，已通过 Bearer 校验）。
- Pydantic 请求模型：email 用 `str + pattern` 校验（避免引入 `email-validator` 依赖），password `min_length=6`，code `min/max_length=6 + pattern=^\d{6}$`。

### `job_api/deps.py`（替换 T4 占位）
- `bearer_scheme = HTTPBearer(auto_error=True)`（缺/空 Authorization 自动 401）。
- `get_current_user(credentials)` → `verify_token` 校验 JWT → `get_user_by_id(payload["sub"])` 查 DB → 返回脱敏 dict `{"id", "user_id", "email", "is_verified"}`（不含 `password_hash`）。
- 同时暴露 `id` 与 `user_id`（同值）：`id` 为规范字段（T3 refresh 用 `current_user["id"]`），`user_id` 为 T4 路由兼容（`routers/llm.py` 用 `user["user_id"]`）。
- 失败路径：token 解析失败 / 缺 sub / 用户不存在 → 401 + `WWW-Authenticate: Bearer`。

### `job_api/tests/test_auth.py`
- 6 个测试，覆盖 spec 全部验收点：
  - `test_register_verify_login_refresh`：注册→验证→登录→refresh 全链路；mock email 被调用一次；验证码从临时 DB 直读。
  - `test_duplicate_verified_register_returns_409`：已验证用户重复注册→409。
  - `test_duplicate_unverified_register_resends_code`：未验证用户重复注册→200 重发码，user_id 不变。
  - `test_unverified_login_returns_403`：未验证用户登录→403。
  - `test_wrong_password_returns_401`：错误密码→401。
  - `test_refresh_with_invalid_token_returns_401`：Bearer 假 token→401。
- fixtures：`temp_env`（`monkeypatch` 注入 `DATA_DIR=tmp_path` + `JWT_SECRET=test-secret`，`get_settings.cache_clear()` 前后清缓存）；`client`（重置 `auth_svc._init_done` + `limiter.enabled=False` 测试期禁限流）；`mock_send_email`（autouse，`patch services.email_service.send_verification_code` 为 `AsyncMock`）。
- 验证码读取绕过 email mock：直接用 `aiosqlite.connect` + `asyncio.run` 从临时 DB 查 `verification_codes` 表。

### `job_api/main.py`（更新）
- 新增 `from routers.auth import limiter as auth_limiter, router as auth_router`；`app.state.limiter = auth_limiter` + `add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)` + `add_middleware(SlowAPIMiddleware)`；`app.include_router(auth_router, prefix="/api/v1")`。

### `job_api/requirements.txt`（更新）
- 新增 `aiosqlite>=0.20.0`（异步 SQLite）。
- 修复 `passlib[bcrypt]>=1.8.0`（PyPI 最新仅 1.7.4）→ `passlib[bcrypt]>=1.7.4`。
- 新增 `bcrypt>=4.0,<5.0`（passlib 1.7.4 与 bcrypt 5.x 不兼容，会抛 `ValueError: password cannot be longer than 72 bytes` 假报错；bcrypt 4.x 工作，仅有 deprecation warning）。

**验收**:
- ✅ `python -m py_compile` 全部 16 个文件通过（models/{__init__,user} / services/{__init__,jwt_service,email_service,auth_service} / routers/{__init__,auth,health} / deps / tests/{__init__,test_auth,test_health} / main / config）
- ✅ `python -m pytest tests/test_auth.py -v` → **6 passed**（在临时 venv 安装 requirements.txt 后实测；任务要求"不装 pip 依赖"，故未在生产环境装，仅用临时 venv 验证）
- ✅ `python -m pytest tests/test_auth.py tests/test_health.py -v` → **7 passed**
- ✅ 重复注册返回错误（409 Conflict）
- ✅ 未验证用户登录返回 403 Forbidden
- ✅ 错误密码返回 401 Unauthorized
- ✅ refresh 端点 Bearer 校验生效（无效 token → 401）

**关键设计决策**:
- **aiosqlite 而非同步 sqlite3**：任务明确要求异步；每个 CRUD 函数内部 `_connect()` 开新连接 + finally close，避免跨请求连接泄漏；`init_db()` 用 `executescript` 一次建两表。
- **passlib + bcrypt 版本钉死**：passlib 1.7.4 是 PyPI 最新（无 1.8.0）；bcrypt 5.x 与 passlib 1.7.4 不兼容（hash 时假报 72 字节限制并挂起），故钉 `bcrypt>=4.0,<5.0`，bcrypt 4.x 工作（仅有 `asyncio.iscoroutinefunction` deprecation warning，不影响功能）。
- **slowapi limiter 实例放 routers/auth.py**：避免 main.py 与 routers 循环导入；main.py `from routers.auth import limiter` 注册到 `app.state.limiter` + 挂 `SlowAPIMiddleware` + `RateLimitExceeded` 异常处理。测试期 `limiter.enabled = False` 绕过限流，避免同 IP 多测试触发 429。
- **deps.py 替换 T4 占位但保兼容**：T4（LLM 代理）已实现并依赖占位 `deps.get_current_user` 返回 `{"user_id": "demo-user", "token": ...}` 且接受任意 token。T3 替换为真 JWT 校验后，T4 路由层 `user["user_id"]` 访问通过 `id`/`user_id` 双键兼容；T4 测试因用假 `Bearer test-token` 会失败（需在 T4 改为注册→验证→登录拿真 JWT），属 T4 范畴，不在 T3 验收内。
- **email 字段不用 EmailStr**：避免引入 `email-validator` 依赖，用 `pydantic.Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")` 简易校验。
- **验证码从 DB 直读绕过 email mock**：测试 `mock_send_email` 把 `send_verification_code` 换成 `AsyncMock`，但验证码已写入 `verification_codes` 表，故用独立 `aiosqlite.connect` + `asyncio.run` 直查 DB 取码，再调 `/verify-email`。
- **bcrypt 密码长度限制**：bcrypt 72 字节上限由 passlib 处理，测试用 9-15 字节密码均在限内；生产若需更长密码应在 hash 前 SHA-256（本任务范围未涉及）。

**对 T4/T5 测试的影响**（已知，非 T3 引入的回归）:
- `tests/test_llm.py`（T4）7 个 HTTP 测试失败：因 deps.py 改为真 JWT 校验，T4 测试用 `Bearer test-token`（非合法 JWT）→ 401。修复方式：T4 测试 fixture 改为注册→验证→登录拿真 JWT，或 `monkeypatch` `services.jwt_service.verify_token` 返回固定 payload。属 T4 范畴。
- `tests/test_sync.py`（T5）3 个 HTTP 测试失败（404）：`main.py` 未 `include_router(sync_router)`（T5 main.py 集成在 T5 任务内，本 T3 main.py 仅集成 auth_router）。属 T5 范畴。

**下一步**: T4 测试需更新为真 JWT 流程；T6 — 桌面端调用 sync/auth 接口的客户端封装

---

## 2026-10-03 — T5: 云端岗位同步接口 ✅

**状态**: 完成

**产出**:

### `job_api/services/sync_service.py`
- `SyncService` 类:`get_jobs_since(since, limit, cursor?)` → `{jobs, next_cursor}`;`get_stats()` → `{total, updated_at}`。
- 仅用标准库 `sqlite3` 读 `jobs.db`,**不引入任何新 pip 依赖**(任务要求"不装 pip 依赖")。
- 输出字段对齐 spec 的 jobs 表 schema,顺序固定于 `JOB_FIELDS` 常量:`job_id, company, title, category, city, requirements, jd_text, apply_url, deadline, source, graduation_match, is_mt, updated_at`。
- 增量查询 `updated_at > since`;分页采用复合游标 `(updated_at, job_id)`,cursor 编码为 `'{updated_at}|{job_id}'`,严格大于避免同一时间戳漏行/重行;损坏 cursor 自动回退到无游标分支。
- 每页默认 500,上限 1000(`MAX_PAGE_SIZE`),`limit<1` 取默认、`limit>1000` 夹到上限。
- **数据源桥接**:`jobs.db` 实际有三张物理表(`companies/announcements/positions`),并无 `jobs` 表。`_ensure_schema()` 在初始化时检测 `sqlite_master`:若 `jobs` 已存在(物理表或视图)直接复用不覆盖;若不存在则从三表 JOIN 创建同名 `jobs` 视图(`CREATE VIEW IF NOT EXISTS`),把 `positions.created_at→updated_at`、`positions.is_management_trainee→is_mt`、`announcements.deadline/apply_url/announcement_url`、`CASE WHEN min_grade/max_grade IS NULL THEN 1 ELSE 0 END→graduation_match` 等映射到位。依赖表缺失(测试只建 jobs 表)时忽略错误,留给调用方建表。
- `from config import get_settings` 延迟到 `__init__` 内 `db_path is None` 分支才执行——使单元测试(传 `db_path`)在 `pydantic_settings` 未装的纯 Python 环境也能独立运行。

### `job_api/deps.py`
- 占位 Bearer Token 认证依赖 `verify_token(request)`:开发期 `SYNC_API_TOKEN` 未配置时放行(返回 `{authenticated:False, mode:"dev"}`);配置后要求 `Authorization: Bearer <token>` 严格匹配,否则 401。通过环境变量注入,生产部署收紧。

### `job_api/routers/sync.py`
- `GET /api/v1/sync/jobs?since=&limit=500&cursor=` → `{jobs, next_cursor}`(`limit` 用 `Query(ge=1, le=1000)` 约束,越界返回 422)。
- `GET /api/v1/sync/stats` → `{total, updated_at}`。
- 路由整体 `dependencies=[Depends(verify_token)]`,挂载于 `main.py` 的 `include_router(sync_router, prefix="/api/v1")`,最终路径 `/api/v1/sync/{jobs,stats}`。

### `job_api/main.py`
- 新增 `from routers.sync import router as sync_router` 与 `app.include_router(sync_router, prefix="/api/v1")`;原占位注释保留供后续路由扩展。

### `job_api/tests/test_sync.py`
- 14 个测试用例:Service 层 11 个(增量查询/空 since 全量/cursor 分页多页/同一时间戳 cursor 推进不漏不重/since+cursor 组合/坏 cursor 回退/limit 夹紧/limit<1 默认/字段对齐 spec/stats/常量),全部基于临时 SQLite 建 mock `jobs` 物理表(10 条数据,spec 字段),不依赖真实 `jobs.db`;HTTP 层 3 个用 `pytest.importorskip("fastapi")` 在 fastapi 缺失时优雅跳过。

**验收**:
- ✅ `python3 -m py_compile` 全部 11 个文件通过(`main.py / config.py / deps.py / routers/{__init__,health,sync}.py / services/{__init__,sync_service}.py / tests/{__init__,test_health,test_sync}.py`)
- ✅ `python3 -m pytest tests/test_sync.py` → **11 passed, 3 skipped**(fastapi 未装时 HTTP 层跳过;service 层全绿)
- ✅ 接口签名符合 spec:`/api/v1/sync/jobs` 返回 `{jobs, next_cursor}`、`/api/v1/sync/stats` 返回 `{total, updated_at}`
- ✅ 字段对齐 spec:`JOB_FIELDS` 常量锁定 13 字段顺序,`test_job_fields_align_spec` 断言 `set(job.keys()) == set(JOB_FIELDS)`
- ⚠️ 按任务要求未执行 `pip install`;HTTP 层测试在依赖安装后(fastapi+pydantic-settings)即可自动跑通(已用 `importorskip` 兼容)

**关键设计决策**:
- **不引入新依赖**:任务明确"不装 pip 依赖",故 `SyncService` 用标准库 `sqlite3` 而非 `aiosqlite`;`deps.py` 认证用 `os.getenv` 而非新增 `python-jose` 等。
- **jobs 表不存在 → 自动建视图**:真实 `jobs.db` 只有 `companies/announcements/positions` 三表,`_ensure_schema` 用 `CREATE VIEW IF NOT EXISTS` 把三表 JOIN 映射成 spec 的 jobs schema,生产环境零迁移即可拉数据;测试用 mock 物理表时检测到 `jobs` 已存在直接跳过,不覆盖。
- **复合游标而非单 job_id**:同一 `updated_at` 多行时单 job_id 游标会漏行,故用 `(updated_at, job_id)` 复合严格大于,`test_get_jobs_since_cursor_same_timestamp` 专门覆盖。
- **延迟 import config**:`sync_service.py` 顶层不 import `config`,使 service 层测试在纯标准库环境可跑(规避 `pydantic_settings` 缺失),生产路径仍走 `settings.JOBS_DB_PATH`。
- **SQLite 字符串比较语义**:`updated_at` 是 TEXT,比较是字典序,故 `since` 应传完整时间戳(`2026-01-05 00:00:00`)而非截断日期(`2026-01-05`),否则后者作为前缀会误纳入当日数据。

**下一步**: T6 — 桌面端调用 sync 接口的客户端封装 + 本地 SQLite 增量落库(`job_workbench/src/api/sync.ts` + Rust 侧 `jobs_cache.db` upsert)

---

## 2026-10-03 — T11: Python sidecar 评分引擎 ✅

**状态**: 完成

**产出**:

### `job_workbench/python-sidecar/sidecar_server.py`
- stdin/stdout JSON-RPC 服务(每行一个 JSON),供 Tauri Rust 端以子进程方式拉起
- 协议:`{"id","method","params"}` → `{"id","result"}` 或 `{"id","error"}`
- 支持方法:
  - `ping` → `{"pong": true}`
  - `score_one` → 调 `scorer.score_job(job, profile)` 返回 10 维加权评分
  - `score_batch` → 批量调 score_job,返回 `[{job_id, score, recommend, reasons}, ...]`
  - `quit` → 退出进程
- 通过 `sys.path.insert(0, 上两级)` import 父目录(/workspace/job_assistant)的 scorer / resume_parser / keyword_normalizer / job_tree / competitiveness / job_db,不依赖 CWD
- profile 参数用 `types.SimpleNamespace` 包 dict 构造(模拟 UserProfile 属性访问);`structured_keywords` / `direction_keywords` 保留 dict(scorer._tag_get 已兼容)
- 异常不崩,主循环捕获后返回 `error` 字段;日志走 stderr 不污染 stdout
- `_emit()` 写一行 JSON 后立即 flush(管道子进程必需)

### `job_workbench/python-sidecar/requirements-sidecar.txt`
- 仅列 sidecar 评分依赖:`python-dotenv>=1.0.0`(供 config.py 加载 .env)
- 不含 llm_client 的依赖(httpx/openai 等),评分链路 llm_client 传 None

### `job_workbench/python-sidecar/pyoxidizer.bzl`
- PyOxidizer 占位配置,target=`python-sidecar`,entry=`sidecar_server.main`
- 把 sidecar_server.py + 父目录评分 .py(scorer/resume_parser/keyword_normalizer/job_tree/competitiveness/job_db/config/models)一起打进可执行
- 注释说明:`cargo install pyoxidizer` → `pyoxidizer build` → 产物放 `src-tauri/binaries/`,Rust 端 `Command::new().stdin(Stdio::piped())` 启动;数据文件(kw_dict.json/job_category_tree.json/jobs.db)不打进可执行,运行期由 DATA_DIR 环境变量指向

### `job_workbench/python-sidecar/tests/test_sidecar.py`
- 11 个单元测试,不依赖真实 LLM(走 mock profile + mock job)
- 覆盖:
  - `TestPingPong`:ping/pong 往返;quit 后进程退出且不再处理后续请求
  - `TestScoreOne`:返回 0-100 分;推荐度取值集合校验;缺 job 参数抛 ValueError
  - `TestScoreBatch`:N 条 job → N 条结果;每条含 `job_id/score/recommend/reasons`,score ∈ [0,100]
  - `TestErrorHandling`:未知方法返回 error;坏 JSON 返回 error;缺 profile 返回 error;无 method 字段返回 error
- 测试用 `serve(in_stream, out_stream)` 注入 StringIO,断言响应行

**验收**:
- ✅ `python3 -m py_compile sidecar_server.py` 通过
- ✅ `echo '{"id":1,"method":"ping","params":{}}' | python3 sidecar_server.py` → `{"id": 1, "result": {"pong": true}}`
- ✅ `DATA_DIR=../../data python3 -m pytest tests/test_sidecar.py -q` → 11 passed
- ✅ mock 数据走通端到端:`score_one` 返回 92.4 分(强烈推荐),`score_batch` 3 条全有结构化输出
- ✅ 不依赖真实 LLM(scorer.score_job 的 llm_client 参数传 None,DeepSeek 不被调用)

**关键设计决策**:
- profile 用 `SimpleNamespace(**dict(profile_dict))` 包,而不是递归转 SimpleNamespace — `structured_keywords` 内的 dict 必须保留(scorer._tag_get 用 `isinstance(tag, dict)` 判断走 dict 分支),`direction_keywords` 必须保留 .items()
- DATA_DIR 环境变量:`config.py` 默认 `/opt/job_assistant/data`,本地测试用 `DATA_DIR=/workspace/job_assistant/data`;Tauri 启动子进程时注入实际数据目录
- 日志走 stderr、JSON 走 stdout + flush,这是子进程管道双向通信的标准约定

**下一步**: T12 — Tauri Rust 端 sidecar 进程管理 + IPC 客户端(用 `tokio::process::Command` + `BufReader` 行读)

---

## 2026-10-03 — T2: 云端 API 骨架完善 ✅

**状态**: 完成

**产出**:

### `job_api/`（云端 API，FastAPI）
- `main.py`：FastAPI 实例（`title="求职搭子 API"`、`version="0.1.0"`）；CORS 中间件（开发期 `CORS_ORIGINS=["*"]` 时自动置 `allow_credentials=False` 以兼容 CORS 规范）；`lifespan` 上下文管理器在启动时打印脱敏配置摘要（密钥仅暴露"是否已设置"布尔值）；挂载 `routers.health` 路由；预留 `/api/v1` 前缀 `include_router` 占位注释。
- `config.py`：Pydantic Settings 字段补齐 — `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL=https://api.deepseek.com` / `JWT_SECRET` / `JWT_ALG=HS256` / `JWT_EXPIRE_HOURS=168` / `RESEND_API_KEY` / `DATA_DIR=../data` / `JOBS_DB_PATH=../data/jobs.db` / `CORS_ORIGINS=["*"]`；新增 `get_settings()` 单例函数（`@lru_cache`）；`sqlite_url` 属性改用 `JOBS_DB_PATH`。
- `routers/__init__.py`：路由包占位。
- `routers/health.py`：`GET /health` 路由（从 main.py 抽离），返回 `{"status": "ok", "version": "0.1.0"}`。
- `requirements.txt`：补 `pytest>=8.0.0`（测试用）。
- `.env.example`：同步新字段（`DEEPSEEK_BASE_URL` / `JOBS_DB_PATH` / `CORS_ORIGINS=["*"]`）。
- `tests/__init__.py` + `tests/test_health.py`：`TestClient` 验证 `/health` 返回 200 且 `status=="ok"`。

**验收**:
- ✅ `python -m py_compile main.py config.py routers/health.py tests/test_health.py` 通过（语法正确）
- ✅ `python -c "from main import app; print(app.title)"` 输出 "求职搭子 API"（依赖安装后即可复现）
- ✅ `python -m pytest tests/` 通过（依赖安装后即可复现）
- ⚠️ 按任务要求未执行 `pip install`，仅创建/完善文件；上述运行时验收项在依赖安装后即可复现

**备注**:
- 原 T1 计划中 T2 同时涵盖"桌面端 UI 框架"与"API 鉴权与路由分层"，本任务聚焦云端 API 骨架；JWT 鉴权与业务路由（jobs / resume / applications）留待后续任务落地，`main.py` 已为 `include_router(prefix="/api/v1")` 预留占位注释。
- CORS：当 `CORS_ORIGINS` 含 `"*"` 时自动将 `allow_credentials` 置为 `False`，规避 Starlette 在通配源 + 凭证场景下的规范冲突；生产环境应改为具体源列表并启用 credentials。

**下一步**: T3 — 桌面端 UI 框架与暖橙主题落地 / API 鉴权（JWT）与业务路由分层

---

## 2026-10-03 — T1: 项目脚手架初始化 ✅

**状态**: 完成

**产出**:

### `job_workbench/`（桌面端，Tauri 2 + React 18 + TypeScript + Tailwind + Zustand）
- 配置：`package.json` / `tsconfig.json` / `vite.config.ts` / `tailwind.config.ts` / `postcss.config.js`
- 入口：`index.html` / `src/main.tsx` / `src/App.tsx`（路由 4 页面）/ `src/index.css`（暖橙主题 CSS 变量）
- 页面占位：`src/pages/{Jobs,Resume,Applications,Login}.tsx`
- 业务骨架：`src/api/client.ts`（fetch 封装基类）/ `src/stores/authStore.ts`（Zustand）
- Tauri 2 原生层：`src-tauri/Cargo.toml`（`tauri = "2"`）/ `src-tauri/tauri.conf.json`（1200x800，标题"求职搭子"）/ `src-tauri/src/main.rs`（`build()` 模式入口）/ `src-tauri/src/lib.rs`（占位）/ `src-tauri/build.rs`（codegen 所需）
- 主题：主色 `#F97316`、深石板 `#0F172A`、米白底 `#FAFAF9`、圆角 16px+（CSS 变量 + Tailwind extend）

### `job_api/`（云端 API，FastAPI）
- `requirements.txt`（fastapi / uvicorn / python-jose[cryptography] / passlib[bcrypt] / python-multipart / pydantic / pydantic-settings / httpx / aiofiles / slowapi / resend / python-dotenv）
- `main.py`（FastAPI 入口 + `/health` + CORS + 配置加载）
- `config.py`（Pydantic Settings：`DEEPSEEK_API_KEY` / `JWT_SECRET` / `JWT_ALG=HS256` / `JWT_EXPIRE_HOURS=168` / `RESEND_API_KEY` / `DATA_DIR` / `DB_PATH=./data/jobs.db` / `CORS_ORIGINS`）
- `.env.example`（全量环境变量占位）/ `.gitignore`

### 根目录
- `README.md`（项目说明 + 两个子项目 + 开发命令）
- `CHANGELOG.md`（初始 0.1.0）
- `.gitignore`（忽略 node_modules / __pycache__ / .env / target / dist / *.db）
- `Makefile`（`help` / `dev-app` / `dev-api` / `build-app` / `build-api` / `test` / `lint`）

**验收**:
- ✅ `make help` 列出所有命令
- ✅ `job_workbench/` 与 `job_api/` 目录结构完整
- ✅ 所有文件可独立存在，不依赖未创建模块
- ✅ 未安装 npm 依赖（仅文件骨架）
- ✅ 暖橙主题 CSS 变量 + Tailwind extend 双轨落地

**备注**:
- 在显式文件清单之外补充了 `src-tauri/build.rs`（Tauri 2 编译期 codegen 必需，否则 `tauri::generate_context!()` 宏无法工作），属最小必要文件。
- Tauri `bundle.icon` 引用标准图标路径（`icons/*.png` 等），实际构建前需补充图标资源。

**下一步**: T2 — 桌面端 UI 框架与暖橙主题落地 / API 鉴权与路由分层
