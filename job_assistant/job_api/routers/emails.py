"""邮箱账户与邮件同步路由。

POST   /api/v1/email/accounts          新增邮箱账户
GET    /api/v1/email/accounts          列出邮箱账户
DELETE /api/v1/email/accounts/{id}     删除邮箱账户
POST   /api/v1/email/accounts/{id}/test    测试连接
POST   /api/v1/email/accounts/{id}/sync    同步邮件
GET    /api/v1/email/tasks             列出分类任务（?status=pending）
POST   /api/v1/email/tasks/{id}/confirm   确认任务（创建日程+提醒）
POST   /api/v1/email/tasks/{id}/ignore    忽略任务
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from deps import get_current_user
from models import email as email_model
from models import email_account as account_model
from services import imap_service, schedule_service

router = APIRouter(prefix="/email", tags=["email"])


class CreateAccountRequest(BaseModel):
    email: str
    imap_server: str
    imap_port: int = 993
    username: str
    password: str


@router.post("/accounts")
async def create_account(
    req: CreateAccountRequest, user: dict = Depends(get_current_user)
):
    # 测试连接
    test = await imap_service.test_connection(
        req.imap_server, req.imap_port, req.username, req.password
    )
    if not test["ok"]:
        # 错误信息透传给前端,前端用 extractErrorMessage 显示
        raise HTTPException(status_code=400, detail=f"IMAP 连接失败: {test['error']}")

    account = await account_model.create_account(
        user_id=user["id"],
        email=req.email,
        imap_server=req.imap_server,
        imap_port=req.imap_port,
        username=req.username,
        password=req.password,
    )
    return account


@router.get("/accounts")
async def list_accounts(user: dict = Depends(get_current_user)):
    accounts = await account_model.list_accounts(user["id"])
    return {"accounts": accounts}


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: str, user: dict = Depends(get_current_user)
):
    ok = await account_model.delete_account(account_id, user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="账户不存在")
    return {"ok": True}


@router.post("/accounts/{account_id}/test")
async def test_account(
    account_id: str, user: dict = Depends(get_current_user)
):
    account = await account_model.get_account(account_id, user["id"])
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    result = await imap_service.test_connection(
        account["imap_server"], account["imap_port"],
        account["username"], account["password"],
    )
    return result


@router.post("/accounts/{account_id}/sync")
async def sync_account(
    account_id: str, user: dict = Depends(get_current_user)
):
    result = await imap_service.sync_account(account_id, user["id"])
    if result["error"]:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.get("/emails/{email_id}")
async def get_email_detail(
    email_id: str, user: dict = Depends(get_current_user)
):
    """返回邮件原文：主题/发件人/收件时间/正文（text + html）。

    供前端"查看邮件"弹窗使用。任务卡片上的 email_id 即此 id。
    """
    email = await email_model.get_email(email_id, user["id"])
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")
    return {"email": email}


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = None, user: dict = Depends(get_current_user)
):
    tasks = await email_model.list_tasks(user["id"], status=status)
    # 拉取每个任务关联的邮件主题/发件人/收件时间，供前端卡片预览
    enriched = []
    for t in tasks:
        email_id = t.get("email_id")
        if email_id:
            email_row = await email_model.get_email(email_id, user["id"])
            if email_row:
                t["email_subject"] = email_row.get("subject") or ""
                t["email_sender"] = email_row.get("sender") or ""
                t["email_received_at"] = email_row.get("received_at") or ""
            else:
                t["email_subject"] = ""
                t["email_sender"] = ""
                t["email_received_at"] = ""
        else:
            t["email_subject"] = ""
            t["email_sender"] = ""
            t["email_received_at"] = ""
        enriched.append(t)
    return {"tasks": enriched}


@router.post("/tasks/{task_id}/confirm")
async def confirm_task(
    task_id: str, user: dict = Depends(get_current_user)
):
    try:
        result = await schedule_service.confirm_email_task(task_id, user["id"])
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tasks/{task_id}/ignore")
async def ignore_task(
    task_id: str, user: dict = Depends(get_current_user)
):
    ok = await email_model.ignore_task(task_id, user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True}


@router.post("/tasks/{task_id}/reextract")
async def reextract_task(
    task_id: str, user: dict = Depends(get_current_user)
):
    """用户手动触发 ✨ AI 重新提取任务字段。

    场景：异步 LLM 提取还在 pending 状态、或提取结果不准、或 LLM 失败后想重试。
    流程：
    1. 校验任务存在且为 pending 状态
    2. 标记 extract_status=pending（前端显示加载中）
    3. 异步触发 LLM 提取（不等返回）
    4. 立即返回 ok，前端轮询/刷新查看结果
    """
    task = await email_model.get_task(task_id, user["id"])
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] != email_model.TASK_STATUS_PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"任务已处理（{task['status']}），无法重新提取",
        )
    # 拉取邮件原文供 LLM 提取
    email_row = await email_model.get_email(task["email_id"], user["id"])
    if not email_row:
        raise HTTPException(status_code=404, detail="关联邮件不存在")

    # 标记 pending，触发异步提取
    await email_model.update_task_extract_status(
        task_id, user["id"], email_model.EXTRACT_STATUS_PENDING
    )
    # 复用 imap_service 里的异步触发器
    from services.imap_service import _trigger_async_llm_extract
    _trigger_async_llm_extract(
        task_id=task_id,
        user_id=user["id"],
        subject=email_row.get("subject") or "",
        body=email_row.get("body_text") or email_row.get("body_html") or "",
        sender=email_row.get("sender") or "",
        message_id=email_row.get("message_id") or "",
        imap_server="",  # email_link 已存在，不需重建
    )
    return {"ok": True}
