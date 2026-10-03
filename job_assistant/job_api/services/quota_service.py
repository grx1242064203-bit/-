"""每用户每日 LLM 调用配额管理。

存储：SQLite（与 auth.db 同库，新建 llm_usage 表）。
每日 0 点重置：按日期判断（usage_date 字段，YYYY-MM-DD）。
默认每日 5 次（简历解析 1 次 + 补充分析 4 次）。

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

DEFAULT_DAILY_LIMIT = 5

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


def get_user_quota(user_id: str, limit: int = DEFAULT_DAILY_LIMIT) -> Dict:
    """返回 {limit, used, remaining}。按当日日期判断重置（跨天自动归零）。"""
    today = date.today().isoformat()
    with _db_lock:
        conn = _get_conn()
        row = conn.execute(
            "SELECT used_count FROM llm_usage WHERE user_id=? AND usage_date=?",
            (user_id, today),
        ).fetchone()
        used = int(row["used_count"]) if row else 0
        remaining = max(0, limit - used)
        return {"limit": limit, "used": used, "remaining": remaining}


def increment_usage(user_id: str, limit: int = DEFAULT_DAILY_LIMIT) -> bool:
    """增加 1 次用量计数；返回 False 表示已超额（不写入）。"""
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
