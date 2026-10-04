"""岗位同步路由:供桌面端增量拉取岗位数据。

- ``GET /api/v1/sync/jobs``      增量分页拉取岗位
- ``GET /api/v1/sync/stats``     岗位总数与最新更新时间
- ``GET /api/v1/sync/companies`` 分页拉取公司总览
- ``GET /api/v1/sync/company-stats`` 公司维度统计
- ``GET /api/v1/sync/categories`` 岗位分类统计
"""
from fastapi import APIRouter, Depends, Query

from deps import get_current_user
from services.sync_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SyncService,
)

router = APIRouter(
    prefix="/sync",
    tags=["sync"],
    dependencies=[Depends(get_current_user)],
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


@router.get("/companies")
def list_companies(
    limit: int = Query(200, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    industry: str = Query("", description="行业筛选"),
    company_type: str = Query("", description="公司类型筛选"),
    keyword: str = Query("", description="公司名关键词"),
) -> dict:
    """分页拉取公司总览（对齐飞书公司表字段）。"""
    return SyncService().get_companies(
        limit=limit,
        offset=offset,
        industry=industry,
        company_type=company_type,
        keyword=keyword,
    )


@router.get("/company-stats")
def company_stats() -> dict:
    """公司维度统计：总数 + 行业分布 + 类型分布。"""
    return SyncService().get_company_stats()


@router.get("/categories")
def categories() -> dict:
    """岗位分类统计（用于侧边栏导航）。"""
    return SyncService().get_job_categories()
