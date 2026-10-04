"""从服务器拉取最新 jobs.db 并替换本地副本。

数据链路（第一性原理）：
    飞书源表 → [服务器 daily_update.sh @ 08:00] → 服务器 jobs.db（主库）
                                                    ↓ 本服务（HTTP 下载 + 完整性校验）
                                              本地 jobs.db → SyncService → 前端

本服务职责：
1. 调用服务器 /api/db/info 获取主库健康状态（完整性、大小、行数、mtime）
2. 调用服务器 /api/db/download 下载 jobs.db 到临时文件
3. 对临时文件运行 PRAGMA integrity_check，并校验 MD5 与服务器一致
4. 备份旧 jobs.db，原子替换为新文件
5. 返回清晰的成功/失败状态，供 API 与前端展示
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from config import get_settings


class DbSyncResult:
    def __init__(
        self,
        ok: bool,
        message: str,
        remote_info: Optional[dict] = None,
        downloaded_bytes: int = 0,
        md5_match: bool = False,
        integrity_ok: bool = False,
        backup_path: Optional[str] = None,
    ) -> None:
        self.ok = ok
        self.message = message
        self.remote_info = remote_info or {}
        self.downloaded_bytes = downloaded_bytes
        self.md5_match = md5_match
        self.integrity_ok = integrity_ok
        self.backup_path = backup_path

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "message": self.message,
            "remote_info": self.remote_info,
            "downloaded_bytes": self.downloaded_bytes,
            "md5_match": self.md5_match,
            "integrity_ok": self.integrity_ok,
            "backup_path": self.backup_path,
        }


def _md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _integrity_check(path: Path) -> tuple[bool, str]:
    """对 SQLite 文件运行 PRAGMA integrity_check，返回 (是否ok, 结果文本)。"""
    try:
        conn = sqlite3.connect(str(path))
        row = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        result = row[0] if row else "no result"
        return result == "ok", result
    except sqlite3.DatabaseError as e:
        return False, f"DatabaseError: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def fetch_remote_info() -> dict:
    """获取服务器主库的健康信息。"""
    s = get_settings()
    url = s.REMOTE_DB_BASE_URL.rstrip("/") + s.REMOTE_DB_INFO_PATH
    req = Request(url, headers={"User-Agent": "job-assistant-sync/1.0"})
    with urlopen(req, timeout=30) as resp:
        import json
        return json.loads(resp.read().decode("utf-8"))


def pull_db_from_server() -> DbSyncResult:
    """从服务器下载 jobs.db，校验完整性与 MD5，原子替换本地副本。

    返回 DbSyncResult，包含成功/失败原因与远程信息。
    """
    s = get_settings()
    db_path = Path(s.JOBS_DB_PATH)
    data_dir = Path(s.DATA_DIR)

    # 1. 获取远程信息（确认主库健康）
    try:
        remote_info = fetch_remote_info()
    except Exception as e:
        return DbSyncResult(
            ok=False,
            message=f"无法连接服务器获取数据库信息: {e}",
        )

    if not remote_info.get("ok"):
        return DbSyncResult(
            ok=False,
            message=f"服务器主库不健康: {remote_info.get('integrity', 'unknown')}",
            remote_info=remote_info,
        )

    remote_md5_expected = None
    remote_size = remote_info.get("size", 0)

    # 2. 下载到临时文件
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        suffix=".db", dir=str(data_dir)
    )
    tmp_path = Path(tmp_path_str)
    os.close(tmp_fd)

    download_url = s.REMOTE_DB_BASE_URL.rstrip("/") + s.REMOTE_DB_DOWNLOAD_PATH
    try:
        req = Request(download_url, headers={"User-Agent": "job-assistant-sync/1.0"})
        with urlopen(req, timeout=300) as resp:
            remote_md5_expected = resp.headers.get("X-DB-MD5")
            with open(tmp_path, "wb") as out:
                shutil.copyfileobj(resp, out, length=1024 * 1024)
    except (URLError, OSError) as e:
        tmp_path.unlink(missing_ok=True)
        return DbSyncResult(
            ok=False,
            message=f"下载失败: {e}",
            remote_info=remote_info,
        )

    downloaded_bytes = tmp_path.stat().st_size

    # 3. 校验大小
    if remote_size and downloaded_bytes != remote_size:
        tmp_path.unlink(missing_ok=True)
        return DbSyncResult(
            ok=False,
            message=(
                f"下载大小不匹配: 期望 {remote_size} 字节, 实际 {downloaded_bytes} 字节"
            ),
            remote_info=remote_info,
            downloaded_bytes=downloaded_bytes,
        )

    # 4. 校验 MD5
    local_md5 = _md5_file(tmp_path)
    md5_match = (
        remote_md5_expected is None or local_md5 == remote_md5_expected
    )
    if not md5_match:
        tmp_path.unlink(missing_ok=True)
        return DbSyncResult(
            ok=False,
            message=(
                f"MD5 不匹配: 服务器 {remote_md5_expected}, 本地 {local_md5}"
            ),
            remote_info=remote_info,
            downloaded_bytes=downloaded_bytes,
            md5_match=False,
        )

    # 5. 完整性校验
    integrity_ok, integrity_msg = _integrity_check(tmp_path)
    if not integrity_ok:
        tmp_path.unlink(missing_ok=True)
        return DbSyncResult(
            ok=False,
            message=f"下载文件完整性校验失败: {integrity_msg}",
            remote_info=remote_info,
            downloaded_bytes=downloaded_bytes,
            md5_match=True,
            integrity_ok=False,
        )

    # 6. 备份旧库 + 原子替换
    backup_path = None
    if db_path.exists():
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup_path = str(db_path.with_name(f"jobs.db.bak_{ts}"))
        try:
            shutil.copy2(str(db_path), backup_path)
        except OSError:
            backup_path = None  # 备份失败不阻断替换

    # 原子替换：先移动到目标同目录（同一文件系统内 rename 是原子的）
    final_tmp = db_path.with_suffix(".db.new")
    shutil.move(str(tmp_path), str(final_tmp))
    os.replace(str(final_tmp), str(db_path))

    return DbSyncResult(
        ok=True,
        message="数据库同步成功",
        remote_info=remote_info,
        downloaded_bytes=downloaded_bytes,
        md5_match=True,
        integrity_ok=True,
        backup_path=backup_path,
    )


def get_local_db_health() -> dict:
    """返回本地 jobs.db 的健康状态，供前端 /api/v1/sync/db-health 查询。"""
    s = get_settings()
    db_path = Path(s.JOBS_DB_PATH)
    result = {
        "exists": db_path.exists(),
        "size": 0,
        "mtime": None,
        "integrity": "missing",
        "integrity_ok": False,
        "error": None,
    }
    if not db_path.exists():
        return result

    result["size"] = db_path.stat().st_size
    result["mtime"] = db_path.stat().st_mtime

    ok, msg = _integrity_check(db_path)
    result["integrity"] = msg
    result["integrity_ok"] = ok
    if not ok:
        result["error"] = f"数据库损坏: {msg}，请点击同步重新拉取"
    return result
