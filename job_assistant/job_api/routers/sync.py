"""岗位同步路由:供桌面端增量拉取岗位数据。

- ``GET /api/v1/sync/jobs``  增量分页拉取岗位
- ``GET /api/v1/sync/stats`` 岗位总数与最新更新时间
"""
from fastapi import APIRouter, Depends, Query

from deps import verify_token
from services.sync_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SyncService,
)

router = APIRouter(
    prefix="/sync",
    tags=["sync"],
    dependencies=[Depends(verify_token)],
)


@router.get("/jobs")
def list_jobs(
    since: str = Query(
        "", description="增量时间戳,返回 updated_at > since 的岗位;空串表示从头拉取"
    ),
    limit: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="每页数量,默认 500,最大 1000",
    ),
    cursor: str | None = Query(
        None, description="分页游标,上一页返回的 next_cursor"
    ),
) -> dict:
    """增量分页拉取岗位列表。"""
    return SyncService().get_jobs_since(since=since, limit=limit, cursor=cursor)


@router.get("/stats")
def stats() -> dict:
    """返回岗位总数与最新更新时间。"""
    return SyncService().get_stats()
