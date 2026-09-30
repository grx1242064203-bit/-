# 校招岗位推荐系统 — 重构分析与评估报告

> 原则：第一性原则（从目标倒推必要条件）+ 对抗性审查（每个改动都问"如果不做会怎样"）

---

## 一、目标与现状

### 目标
为 27 届校招用户提供高质量的岗位推荐，核心交付物：
1. **飞书岗位总表**：结构化岗位数据供用户浏览
2. **匹配推荐引擎**：根据用户画像推荐合适岗位

### 数据链路
```
源公告表(announcements) 
  → [抓取: TikHub/Playwright] → 正文 content
  → [LLM 拆岗: extract_positions] → 岗位 positions
  → [飞书导出] → 飞书岗位总表
  → [匹配: scorer/user_matcher] → 推荐结果
```

### 当前数据状态
- 公告总数：6133
- 抓取成功：1642（27%），失败：4491（73%，TikHub 额度耗尽+Playwright 未安装）
- LLM 拆岗成功：3913，降级(skipped)：1825，待处理(pending)：395
- 岗位总数：44835

---

## 二、第一性原则：哪些字段真正必要？

### 2.1 匹配引擎实际使用的字段（scorer.py + user_matcher.py）

| 字段 | 填充率 | 来源 | 是否可去正文 |
|------|--------|------|-------------|
| position_title | 100% | LLM(标题) | ✅ |
| job_category | 96% | LLM | ✅ |
| major_category | 96% | LLM | ✅ |
| hard_skills | 100% | LLM | ✅ |
| soft_skills | 100% | LLM | ✅ |
| keywords | 100% | LLM | ✅ |
| city | 100% | **源表** | ✅ |
| min_education | 100% | **源表** | ✅ |
| major_required | 100% | LLM/源表 | ✅ |
| company_tier | 96% | LLM | ✅ |
| difficulty | 96% | LLM | ✅ |
| is_management_trainee | 100% | LLM | ✅ |

**结论：匹配核心字段全部 ≥96% 填充，且不依赖正文抓取。**

### 2.2 飞书总表展示字段

| 字段 | 填充率 | 必要性 |
|------|--------|--------|
| 岗位标题 | 100% | 核心 |
| 公司名称 | 100% | 核心 |
| 公司行业 | 100% | 核心 |
| 公司类型 | 100% | 核心 |
| 岗位分类 | 96% | 核心 |
| 最低学历 | 100% | 核心 |
| 专业大类 | 96% | 核心 |
| 城市 | 100% | 核心 |
| 硬技能 | 100% | 核心 |
| 关键词 | 100% | 核心 |
| 投递链接 | 100% | 核心 |
| JD摘要 | 96% | 中 |
| 难度 | 96% | 中 |
| 是否管培 | 100% | 中 |
| 岗位子类 | 96% | 低 |
| 专业要求 | 100% | 低 |
| **招聘流程** | **21%** | **低(用户要求删除)** |

### 2.3 可删除/弱化的字段

| 字段 | 填充率 | 匹配用? | 飞书用? | 处理 |
|------|--------|---------|---------|------|
| department | 32% | 仅显示 | 否 | LLM不再生成,DB保留空列 |
| recruitment_process | 21% | 否 | 是 | LLM不再生成,飞书移除 |
| province | 39% | 否 | 否 | 保留,LLM从city推断 |
| bonus_points | 11% | 否 | 否 | 空→"" |
| certifications | 100%(多[]) | 否 | 否 | 保留 |
| languages | 100%(多[]) | 否 | 否 | 保留 |
| has_written_test | 100%(多false) | 否 | 否 | 保留 |
| responsibilities | 95% | 否 | 否 | 保留 |

---

## 三、对抗性审查：已发现的问题

### 问题 1：`has_pending()` 死循环（P0 严重）

**位置**：`full_pipeline.py:83-95`

```python
crawl_pending = conn.execute(
    "SELECT COUNT(*) FROM announcements WHERE crawl_status != 'success' OR crawl_status IS NULL"
).fetchone()[0]
```

**问题**：把 `crawl_status='failed'`（4491条）也算作 pending，导致 `has_pending()` 永远返回 True，pipeline 无限循环。

**对抗性审查**：
- 如果不修：pipeline 永远空转，每轮都尝试抓取（浪费 TikHub），但不产生新数据
- 修复成本：1 行 SQL 改动
- 修复方案：`crawl_status = 'pending'`（只统计真正待抓取的，不统计 failed）

### 问题 2：`llm_pending` 查询遗漏失败抓取的公告（P0 严重）

**位置**：`full_pipeline.py:93`

```python
llm_pending = conn.execute(
    "SELECT COUNT(*) FROM announcements WHERE (llm_status NOT IN ('success','skipped') OR llm_status IS NULL) AND crawl_status='success'"
).fetchone()[0]
```

**问题**：只统计 `crawl_status='success'` 的待 LLM 公告。但 4491 条 failed 抓取的公告也需要 LLM 拆岗（用标题降级）。这些公告的 `llm_status='pending'` 但 `crawl_status='failed'`，被遗漏。

**对抗性审查**：
- 实际 `get_announcements_for_llm()` 已经不限制 crawl_status（line 336），所以 enrich 阶段能处理
- 但 `has_pending()` 的 llm_pending 不统计它们，导致逻辑不一致
- 修复方案：移除 `AND crawl_status='success'` 条件

### 问题 3：飞书备份表超 20000 上限（已修复）

**位置**：`sync_to_feishu.py`

**状态**：✅ 已修复（按 major_category 分表）

### 问题 4：TikHub 依赖（设计问题，非 bug）

**问题**：抓取依赖 TikHub（付费），额度耗尽后 73% 抓取失败。

**对抗性审查**：
- 抓取的唯一价值是提供正文（职责、要求、部门、流程）
- 但这些字段都不是匹配核心字段
- 标题降级拆岗已验证可行（31362 条岗位来自标题）
- **结论：抓取不是必要环节，应降级为"有则更好，无则用标题"**

### 问题 5：我之前的错误提案（自我审查）

| 错误提案 | 错误原因 | 正确做法 |
|----------|----------|----------|
| 全量重跑 6133 条 | 3913 条已 success 质量OK，重跑浪费 ¥25+50min | 只跑 2220 条(1825 skipped + 395 pending) |
| 从 DB schema 删除 department/recruitment_process | SQLite 删列需重建表，风险大 | 只停止写入+移除导出，DB列保留空值 |
| 未追踪字段全链路 | department 在 user_matcher 有显示引用 | 先查所有引用点再决定 |

---

## 四、重构方案（最小改动原则）

### 4.1 修改清单

| # | 文件 | 改动 | 风险 |
|---|------|------|------|
| 1 | `llm_enricher.py` | prompt 移除 department/recruitment_process；注入源表元数据；requirements 空→"详见招聘公告" | 低 |
| 2 | `job_db.py` | `has_pending` 修复(实际在 full_pipeline)；insert_positions 不再写 department/recruitment_process（用默认空） | 低 |
| 3 | `full_pipeline.py` | 修复 `has_pending()` 两处 bug | 低 |
| 4 | `feishu_master_tables.py` | POSITION_FIELDS 移除"招聘流程" | 低 |
| 5 | `sync_to_feishu.py` | POS_FIELDS 移除 department/recruitment_process | 低 |
| 6 | `user_matcher.py` | "部门"显示改为可选（空则不显示） | 低 |

### 4.2 数据处理

| 操作 | 范围 | 方式 |
|------|------|------|
| SQL 清洗 requirements | 3913 条 success 的岗位 | `UPDATE positions SET requirements='详见招聘公告' WHERE requirements=''` |
| LLM 重跑 | 1825 条 skipped + 395 条 pending = 2220 条 | 重置 llm_status='pending'，跑 enrich |
| 飞书重新导出 | 全量 | 清空旧表+分表写入 |

### 4.3 不做的事（对抗性决策）

- ❌ 不全量重跑 6133 条（3913 条已 OK）
- ❌ 不从 DB schema 删除列（风险大，无收益）
- ❌ 不安装 Playwright（标题方案已够用）
- ❌ 不续费 TikHub（非必要依赖）
- ❌ 不清空 3913 条 success 的岗位数据

---

## 五、实施步骤

1. 修复 `full_pipeline.py` 的 `has_pending()`
2. 修改 `llm_enricher.py` prompt + fallback 逻辑
3. 修改 `job_db.py` insert_positions（移除两列写入）
4. 修改 `feishu_master_tables.py` POSITION_FIELDS
5. 修改 `sync_to_feishu.py` POS_FIELDS
6. 修改 `user_matcher.py` 部门显示
7. SQL 清洗旧数据 requirements
8. 重置 2220 条公告 llm_status='pending'
9. 运行 enrich 处理 2220 条
10. 飞书分表导出
11. 验证字段填充率

---

## 六、时间与费用估算

| 阶段 | 耗时 | 费用 |
|------|------|------|
| 代码修改（6个文件） | ~30 min | ¥0 |
| SQL 清洗 | <1 min | ¥0 |
| LLM 处理 2220 条（5并发，~4s/条） | ~30 min | ~¥15 |
| 飞书分表导出 | ~10 min | ¥0 |
| 验证 | ~10 min | ¥0 |
| **合计** | **~80 min** | **~¥15** |

---

## 七、验证标准

- [ ] `has_pending()` 在所有 pending 处理完后返回 False
- [ ] 2220 条公告全部 llm_status ∈ {success, skipped}
- [ ] positions 表 requirements 空值率 = 0%（全填"详见招聘公告"）
- [ ] 飞书岗位总表无"招聘流程"列
- [ ] 匹配核心字段填充率 ≥96%
- [ ] pipeline 不再死循环
