-- Offer搭子桌面端本地数据库 Schema（SQLite）
-- 对齐 spec: docs/staging/specs/2026-10-03-desktop-workbench.md#四本地数据库-schemasqlite
-- 所有表均 IF NOT EXISTS，幂等可重入；migrations/001_init.sql 由 db::init_db_with_conn 一次性 execute_batch 落库。

PRAGMA journal_mode = WAL;          -- 写不阻塞读，桌面端高频读场景首选
PRAGMA foreign_keys = ON;           -- 开启外键约束（applications.job_id 等）
PRAGMA synchronous = NORMAL;       -- WAL 模式下 NORMAL 足够安全且更快

-- ============================================================================
-- 1. 用户配置（本机）：单行记录，user_id 来自云端注册
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_config (
    user_id                   TEXT    PRIMARY KEY,
    email                     TEXT    NOT NULL,
    token_encrypted           TEXT,                          -- Bearer token 本机加密存储（base64 + 应用层 XOR 占位，后续切 keychain）
    subscription_plan         TEXT,                          -- free / pro / max
    subscription_expires_at   TEXT,                          -- ISO8601 字符串
    llm_quota_today           INTEGER NOT NULL DEFAULT 0,    -- 订阅档位当日配额
    llm_used_today            INTEGER NOT NULL DEFAULT 0,    -- 已用次数
    last_sync_at              TEXT                           -- 最近一次 /sync/jobs 成功时间
);

-- ============================================================================
-- 2. 岗位数据（从云端同步，本地毫秒级筛选 / 评分）
-- ============================================================================
CREATE TABLE IF NOT EXISTS jobs (
    job_id             TEXT    PRIMARY KEY,
    company            TEXT    NOT NULL,
    title              TEXT    NOT NULL,
    category           TEXT,                            -- 岗位大类（技术/产品/运营/管培…）
    city               TEXT,
    requirements       TEXT,                            -- 学历 / 专业等门槛（结构化字段）
    jd_text            TEXT,                            -- 原始 JD 全文
    apply_url          TEXT,
    deadline           TEXT,                            -- ISO8601 截止日期
    source             TEXT,                            -- feishu / manual / ...
    graduation_match   INTEGER NOT NULL DEFAULT 1,      -- 0 = 非应届；1 = 应届可投
    is_mt              INTEGER NOT NULL DEFAULT 0,      -- 管培生标记 0/1
    llm_score          REAL,                            -- 本地算法评分（沿用字段名，0-100）
    llm_reason         TEXT,                            -- 评分理由 / 拆分维度 JSON
    updated_at         TEXT,                            -- 同步游标字段，ISO8601
    deleted            INTEGER NOT NULL DEFAULT 0      -- 软删标记 0/1
);

CREATE INDEX IF NOT EXISTS idx_jobs_updated_at        ON jobs (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_city             ON jobs (city);
CREATE INDEX IF NOT EXISTS idx_jobs_is_mt            ON jobs (is_mt);
CREATE INDEX IF NOT EXISTS idx_jobs_graduation_match ON jobs (graduation_match);
CREATE INDEX IF NOT EXISTS idx_jobs_category         ON jobs (category);
CREATE INDEX IF NOT EXISTS idx_jobs_company           ON jobs (company);
CREATE INDEX IF NOT EXISTS idx_jobs_llm_score        ON jobs (llm_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_deleted           ON jobs (deleted);

-- ============================================================================
-- 3. 简历：本地文件 + 解析结果；同一用户保留多版本，is_active 标记当前生效
-- ============================================================================
CREATE TABLE IF NOT EXISTS resumes (
    resume_id             TEXT    PRIMARY KEY,
    file_path             TEXT    NOT NULL,                -- 本地绝对路径
    raw_text              TEXT,                            -- 提取的纯文本（送 LLM 解析）
    parsed_profile_json   TEXT,                            -- LLM 解析结果 JSON（keywords + fit_directions）
    created_at            TEXT    NOT NULL,
    is_active             INTEGER NOT NULL DEFAULT 0       -- 0/1
);

CREATE INDEX IF NOT EXISTS idx_resumes_is_active ON resumes (is_active);

-- ============================================================================
-- 4. 投递记录：状态机 draft → applied → test → interview → offer | rejected
-- ============================================================================
CREATE TABLE IF NOT EXISTS applications (
    app_id      TEXT    PRIMARY KEY,
    job_id      TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'draft',          -- draft|applied|test|interview|offer|rejected
    applied_at  TEXT,
    updated_at  TEXT,
    notes       TEXT,
    source      TEXT,                                      -- manual / autofill / ...
    FOREIGN KEY (job_id) REFERENCES jobs (job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_applications_job_id  ON applications (job_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications (status);
CREATE INDEX IF NOT EXISTS idx_applications_applied_at ON applications (applied_at);

-- ============================================================================
-- 5. 邮箱配置：本机独有 IMAP 凭证（M2 启用，schema 已预留）
-- ============================================================================
CREATE TABLE IF NOT EXISTS email_accounts (
    account_id          TEXT    PRIMARY KEY,
    email_addr          TEXT    NOT NULL,
    imap_host           TEXT    NOT NULL,
    imap_port           INTEGER NOT NULL,
    password_encrypted  TEXT,                                -- 本机加密（base64 + 应用层 XOR 占位，后续切 keychain）
    last_sync_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_email_accounts_email_addr ON email_accounts (email_addr);

-- ============================================================================
-- 6. 邮件解析结果：LLM 抽取 type/company/time/location 后关联到投递记录
-- ============================================================================
CREATE TABLE IF NOT EXISTS emails (
    email_id         TEXT    PRIMARY KEY,
    account_id       TEXT    NOT NULL,
    subject          TEXT,
    "from"           TEXT,                                  -- "from" 是 SQLite 保留字，需双引号转义；spec 字段名保留
    body             TEXT,
    parsed_type      TEXT,                                  -- interview / offer / reject / test / other
    parsed_company   TEXT,
    parsed_time      TEXT,
    parsed_location  TEXT,
    linked_app_id    TEXT,                                  -- 关联到 applications.app_id
    received_at      TEXT,
    status           TEXT,                                  -- unread / read / archived
    FOREIGN KEY (account_id) REFERENCES email_accounts (account_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_emails_account_id    ON emails (account_id);
CREATE INDEX IF NOT EXISTS idx_emails_received_at   ON emails (received_at);
CREATE INDEX IF NOT EXISTS idx_emails_linked_app_id ON emails (linked_app_id);

-- ============================================================================
-- 7. 日程：邮件解析 / 手动录入 / 同步外部日历
-- ============================================================================
CREATE TABLE IF NOT EXISTS schedules (
    event_id           TEXT    PRIMARY KEY,
    source             TEXT,                                -- email / manual / calendar
    title              TEXT,
    event_time         TEXT,
    location           TEXT,
    company            TEXT,
    job_id             TEXT,
    related_email_id   TEXT,
    status             TEXT,                                -- pending / done / cancelled
    notes              TEXT,
    FOREIGN KEY (job_id)           REFERENCES jobs (job_id) ON DELETE SET NULL,
    FOREIGN KEY (related_email_id)  REFERENCES emails (email_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_schedules_event_time ON schedules (event_time);
CREATE INDEX IF NOT EXISTS idx_schedules_job_id      ON schedules (job_id);
