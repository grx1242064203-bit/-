"""每用户每日 LLM 调用配额管理。

存储：SQLite（与 auth.db 同库，新建 llm_usage 表）。
每日 0 点重置：按日期判断（usage_date 字段，YYYY-MM-DD）。

配额上限通过环境变量 LLM_DAILY_LIMIT 配置(由 config.Settings 注入,见 routers/llm.py):
- 默认 5(开发期兜底,生产必须通过环境变量覆盖)
- 设为 0 表示禁用(不允许任何调用)
- 设为负数(如 -1)表示不限制

设计要点：
- 模块级单例连接 + threading.Lock 保证线程安全（FastAPI 同进程多线程场景）。
- 多进程部署应替换为连接池或 Postgres，此处保持最小实现。
- DB 路径优先环境变量 AUTH_DB_PATH；否则 DATA_DIR/auth.db。
"""
import logging
import os
import sqlite3
import threading
from datetime import date
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

# 兜底默认值(开发期);生产部署应通过环境变量 LLM_DAILY_LIMIT 覆盖。
# 设为 0 = 禁用;负数 = 不限制。
DEFAULT_DAILY_LIMIT = -1


def _resolve_limit(default: int = DEFAULT_DAILY_LIMIT) -> int:
    """从配置(环境变量 LLM_DAILY_LIMIT 或 .env)读取上限,缺失时回退到 default。

    优先用 pydantic Settings(会读取 .env + 系统环境变量),避免直接 os.getenv
    读不到 .env 中配置的问题。
    """
    try:
        from config import get_settings
        val = get_settings().LLM_DAILY_LIMIT
        if val is not None:
            return val
    except Exception:  # noqa: BLE001 配置加载失败时回退 os.getenv
        pass
    raw = os.getenv("LLM_DAILY_LIMIT")
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logger.warning(f"LLM_DAILY_LIMIT 非法值 '{raw}',回退默认 {default}")
        return default

_db_lock = threading.Lock()
_conn: "sqlite3.Connection | None" = None


def _db_path() -> str:
    """返回 quota/auth 用的 SQLite 文件路径。T3 的 auth.db 同库共用。"""
    env_path = os.getenv("AUTH_DB_PATH")
    if env_path:
        return env_path
    data_dir = os.getenv("DATA_DIR", "../data")
    return str(Path(data_dir) / "auth.db")


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path = _db_path()
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        except OSError:
            pass
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _init_schema(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    """幂等建表。T3 的 users 表由其自己创建。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_usage (
            user_id     TEXT NOT NULL,
            usage_date  TEXT NOT NULL,
            used_count  INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, usage_date)
        )
        """
    )
    conn.commit()


def get_user_quota(user_id: str, limit: int | None = None) -> Dict:
    """返回 {limit, used, remaining}。按当日日期判断重置（跨天自动归零）。

    limit 传入优先;否则从环境变量 LLM_DAILY_LIMIT 读取。
    limit <= 0 且 < 0 时视为不限制(remaining 返回大数);
    limit == 0 时禁用(remaining 永远 0)。
    """
    if limit is None:
        limit = _resolve_limit()
    today = date.today().isoformat()
    with _db_lock:
        conn = _get_conn()
        row = conn.execute(
            "SELECT used_count FROM llm_usage WHERE user_id=? AND usage_date=?",
            (user_id, today),
        ).fetchone()
        used = int(row["used_count"]) if row else 0
        if limit < 0:
            # 不限制:返回 used 和一个足够大的 remaining
            return {"limit": limit, "used": used, "remaining": 10**9}
        remaining = max(0, limit - used)
        return {"limit": limit, "used": used, "remaining": remaining}


def increment_usage(user_id: str, limit: int | None = None) -> bool:
    """增加 1 次用量计数；返回 False 表示已超额（不写入）。

    limit 传入优先;否则从环境变量 LLM_DAILY_LIMIT 读取。
    limit < 0 时不限制,总是返回 True;
    limit == 0 时禁用,总是返回 False;
    limit > 0 时正常计数。
    """
    if limit is None:
        limit = _resolve_limit()
    if limit < 0:
        # 不限制,仍然记录用量但永不到顶
        today = date.today().isoformat()
        with _db_lock:
            conn = _get_conn()
            row = conn.execute(
                "SELECT used_count FROM llm_usage WHERE user_id=? AND usage_date=?",
                (user_id, today),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE llm_usage SET used_count=? WHERE user_id=? AND usage_date=?",
                    (int(row["used_count"]) + 1, user_id, today),
                )
            else:
                conn.execute(
                    "INSERT INTO llm_usage (user_id, usage_date, used_count) "
                    "VALUES (?, ?, ?)",
                    (user_id, today, 1),
                )
            conn.commit()
        return True
    today = date.today().isoformat()
    with _db_lock:
        conn = _get_conn()
        row = conn.execute(
            "SELECT used_count FROM llm_usage WHERE user_id=? AND usage_date=?",
            (user_id, today),
        ).fetchone()
        used = int(row["used_count"]) if row else 0
        if used >= limit:
            return False
        if row:
            conn.execute(
                "UPDATE llm_usage SET used_count=? WHERE user_id=? AND usage_date=?",
                (used + 1, user_id, today),
            )
        else:
            conn.execute(
                "INSERT INTO llm_usage (user_id, usage_date, used_count) "
                "VALUES (?, ?, ?)",
                (user_id, today, 1),
            )
        conn.commit()
        return True


def _reset_for_test() -> None:
    """测试辅助：清空 llm_usage 表（不删除表结构）。仅供测试调用。"""
    with _db_lock:
        conn = _get_conn()
        conn.execute("DELETE FROM llm_usage")
        conn.commit()
