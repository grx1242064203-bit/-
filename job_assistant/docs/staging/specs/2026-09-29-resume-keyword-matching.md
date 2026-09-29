
# Spec: 简历关键词结构化提取 + 加权匹配引擎

**创建日期**：2026-09-29
**状态**：设计完成 → 进入编码
**核心目标**：将现有纯字面匹配升级为「简历结构化关键词 → 标准化归一化 → 加权分层匹配」的高精度管线

---

## 一、决策（永久）

### 1. 数据模型变更

**contract**：在 `UserProfile`（[models.py](file:///workspace/job_assistant/models.py#L24-L52)）中新增一个结构化字段，不替换现有 `core_skills` / `direction_keywords`，保持向后兼容。

**data shape**：

```python
# models.py UserProfile 新增字段
structured_keywords: List[KeywordTag] = field(default_factory=list)
# KeywordTag dataclass
@dataclass
class KeywordTag:
    kw: str                   # 原始关键词
    standard: str             # 标准化后关键词（归一化后的 canonical form）
    category: str              # 分类: skill/hard_skill/soft_skill/tool/framework/domain/cert/education/city/role/project
    weight: float              # 权重 0.1-5.0
    source: str                # 来源: resume_llm/manual/normalizer
    resume_section: str        # 简历出处: education/experience/project/skill/other
```

### 2. 新增模块

| 模块 | 职责 | 依赖 |
|---|---|---|
| `resume_parser.py` | 简历文本 → 结构化关键词 | LLMClient, llm_enricher（复用 VL OCR） |
| `keyword_normalizer.py` | 关键词标准化归一化（同义词/缩写/中英文） | 内置同义词词典（MVP 硬编码 JSON） |
| `scorer.py`（重写） | 加权分层匹配 + 匹配理由可解释 | keyword_normalizer |

**invariant**：`scorer.py` 必须同时支持旧版手动关键词和新版结构化关键词（向后兼容），通过 `UserProfile.structured_keywords` 是否为空来判断使用哪条路径。

### 3. 关键词标准化词典

MVP 阶段用硬编码 JSON 文件（`data/kw_dict.json`），不引入外部依赖：

```json
{
  "redis": ["Redis", "redis", "分布式缓存", "缓存中间件", "内存数据库"],
  "mysql": ["MySQL", "mysql", "关系型数据库", "RDBMS"],
  "distributed_systems": ["分布式系统", "分布式架构", "微服务", "Microservices"],
  "scrum": ["Scrum", "敏捷开发", "敏捷方法", "Agile"],
  "machine_learning": ["机器学习", "Machine Learning", "ML", "监督学习", "无监督学习"],
  "backend_development": ["后端开发", "后端工程师", "服务端开发", "Server-side", "Back-end"]
}
```

**invariant**：标准化词典支持热加载（文件变更自动生效），不需要重启服务。

### 4. 匹配评分公式

**分层加权**（替换现有的硬编码分）：

```
总分 = Σ(维度权重 × 维度命中分)

维度          维度权重    命中分计算
─────────────────────────────────────────
skill匹配     0.30       Jaccard(用户关键词set, 岗位keywords set) × 100
hard_skill    0.20       岗位hard_skills命中数 / 岗位hard_skills总数 × 100
soft_skill    0.05       岗位soft_skills命中数 × 20（上限100）
cert匹配      0.10       CFA/CPA/法考等：命中即100，不命中即0
education     0.15       学历达标(>=岗位min_education)即100，不达标0
major匹配     0.05       专业大类吻合即100
city匹配      0.10       目标城市包含岗位城市即100
role匹配      0.05       岗位类别匹配用户方向即100
```

**invariant**：
- 总分范围 0-100
- 每个维度同时输出 `match_reasons: List[str]` 供前端展示"为什么匹配"
- 硬门槛过滤：学历不达标的岗位直接过滤（不进入评分池）

### 5. 简历解析 Prompt

复用 [POSITION_EXTRACT_PROMPT](file:///workspace/job_assistant/llm_enricher.py#L33-L91) 的风格，新增简历专用 prompt，输出与 `KeywordTag` 对齐的 JSON：

```python
RESUME_PARSE_PROMPT = """你是简历解析专家。请从以下简历中提取结构化关键词。

简历文本:
\"\"\"{resume_text}\"\"\"

请输出 JSON 数组（严格 JSON）:
[
  {{
    "kw": "原始关键词",
    "category": "skill|hard_skill|soft_skill|tool|framework|domain|cert|education|city|role|project",
    "weight": 1.0-5.0的浮点数（出现频率/重要性越高权重越高）,
    "resume_section": "education|experience|project|skill|other"
  }}
]

提取规则:
1. 硬技能(hard_skill): 编程语言/框架/工具/技术栈，如 Python/Java/Spring/Docker/K8s
2. 软技能(soft_skill): 沟通/团队/领导力/项目管理
3. 证书(cert): CFA/CPA/法考/PMP/阿里云认证等
4. 领域(domain): 金融/电商/教育/医疗/制造业
5. 教育(education): 学校/专业/学历
6. 其他(other): 出现频率低且不属于以上类别的
7. weight 赋值: 项目经历中出现=3-5，技能列表出现=2-3，其他地方出现=1-2
8. 只提取简历中明确出现的，严禁编造
"""
```

### 6. 测试框架

**contract**：独立于 pipeline 的纯 Python 脚本 `test_keyword_matching.py`，不依赖数据库，直接构造测试数据跑匹配逻辑。

**数据来源**：
- 简历文本：2-3 份构造的典型简历（后端开发/产品经理/金融三个方向）
- 测试岗位：15-20 条手工构造的岗位 dict，字段与 [llm_enricher.py 输出格式](file:///workspace/job_assistant/llm_enricher.py#L41-L67) 完全对齐

**断言方式**：
1. 每条岗位的匹配分数在合理区间（预期匹配的岗位分数 ≥ 60，明显不匹配的 ≤ 30）
2. 同方向岗位排序正确（后端开发简历 → 后端岗排前，前端岗排后）
3. 匹配理由非空（`match_reasons` 至少包含 1 条）

---

## 二、Working Notes（实现中，随时清理）

### 2026-09-29
- scorer.py 现有实现：7 维度硬编码分（职业类型匹配 25 + 行业匹配 15 + 公司类型 10 + 技能关键词 15 + 学历 15 + 专业 10 + 城市 10），纯字符串包含匹配，无结构化关键词。重写时需保留 `score_job()` 函数签名，在内部切换到新逻辑。
- UserProfile 现有字段：`direction_keywords: Dict[str, List[str]]`（方向→关键词列表）和 `core_skills: List[str]`，新字段 `structured_keywords` 是补充而非替换。
- 同义词词典 MVP 只覆盖校招高频词汇（Redis/MySQL/Python/Java/Spring/分布式/敏捷/CFA 等），约 50-100 组，不追求全。
- 不引入 embedding（MVP 阶段），后续可加。
- 测试用简历直接在代码中构造字符串（不用上传文件），测试岗位 dict 写在测试脚本里，跑 `python test_keyword_matching.py` 即可看结果。

---

## 三、延期事项（不在本次 scope）

- 向量语义匹配（embedding + cosine similarity）
- 简历文件上传 HTTP 接口（callback_server.py 改造）
- 简历解析异步队列
- 面试通过率预测
- 用户反馈闭环（用户点"不匹配"后调整权重）
