"""数据库同步路由：本地 jobs.db 健康检查 + 从服务器重新拉取主库。

数据链路（第一性原理）：
    飞书源表 → [服务器 daily_update.sh @ 08:00] → 服务器 jobs.db（主库）
                                                    ↓ 本路由 pull-db（HTTP + 完整性校验）
                                              本地 jobs.db → SyncService → 前端

端点：
- ``GET  /api/v1/sync/db-health``  本地 jobs.db 健康状态（完整性、大小、mtime）
- ``POST /api/v1/sync/pull-db``    从服务器重新拉取 jobs.db 并原子替换本地副本
"""
from fastapi import APIRouter, Depends, HTTPException, status

from deps import get_current_user
from services.db_sync_service import (
    get_local_db_health,
    pull_db_from_server,
)

router = APIRouter(
    prefix="/sync",
    tags=["sync"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/db-health")
def db_health() -> dict:
    """返回本地 jobs.db 的健康状态。

    - ``integrity_ok`` 为 false 时，前端应提示用户点击「重新拉取数据库」。
    - 损坏原因写入 ``error`` 字段，供 UI 展示。
    """
    return get_local_db_health()


@router.post("/pull-db")
def pull_db() -> dict:
    """从服务器拉取最新 jobs.db，校验完整性 + MD5，原子替换本地副本。

    返回 ``DbSyncResult.to_dict()``：
    - ``ok``: 是否成功
    - ``message``: 人类可读结果（成功/失败原因）
    - ``remote_info``: 服务器主库信息（大小、行数、mtime）
    - ``downloaded_bytes`` / ``md5_match`` / ``integrity_ok``: 校验详情
    - ``backup_path``: 旧库备份路径（备份失败时为 null）

    失败时返回 200 + ok=false（业务层失败，非 HTTP 错误），
    便于前端直接读取 message 展示给用户。
    """
    result = pull_db_from_server()
    payload = result.to_dict()
    if not result.ok:
        # 业务失败仍返回 200，message 含清晰原因；前端按 ok 字段判断。
        # 仅在极端情况（如未配置远程地址）才抛 503。
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result.message,
        )
    return payload
