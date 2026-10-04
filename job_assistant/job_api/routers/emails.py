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


@router.get("/tasks")
async def list_tasks(
    status: str | None = None, user: dict = Depends(get_current_user)
):
    tasks = await email_model.list_tasks(user["id"], status=status)
    return {"tasks": tasks}


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
