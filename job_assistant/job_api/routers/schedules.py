"""日程与提醒路由。

GET  /api/v1/schedules              列出日程（带提醒）
DELETE /api/v1/schedules/{id}       删除日程（显式，无自动删除）
GET  /api/v1/schedules/reminders/due  获取到期提醒（供前端轮询）
"""
from fastapi import APIRouter, Depends, HTTPException

from deps import get_current_user
from models import schedule as schedule_model

router = APIRouter(prefix="/schedules", tags=["schedules"])


@router.get("")
async def list_schedules(user: dict = Depends(get_current_user)):
    schedules = await schedule_model.list_schedules_with_reminders(user["id"])
    return {"schedules": schedules}


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: str, user: dict = Depends(get_current_user)
):
    ok = await schedule_model.delete_schedule(schedule_id, user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="日程不存在")
    return {"ok": True}


@router.get("/reminders/due")
async def get_due_reminders(user: dict = Depends(get_current_user)):
    """获取当前用户到期未触发的提醒。前端可用此接口轮询。"""
    reminders = await schedule_model.get_due_reminders()
    # 过滤当前用户
    user_reminders = [r for r in reminders if r["user_id"] == user["id"]]
    return {"reminders": user_reminders}


@router.post("/reminders/{reminder_id}/fire")
async def mark_reminder_fired(
    reminder_id: str, user: dict = Depends(get_current_user)
):
    """标记提醒已触发（前端弹窗后调用）。"""
    await schedule_model.mark_reminder_fired(reminder_id)
    return {"ok": True}
