"""日程与提醒路由。

GET  /api/v1/schedules              列出日程（带提醒）
POST /api/v1/schedules              用户自建日程（手动填表）
POST /api/v1/schedules/ai-extract   AI 从邮件正文提取日程信息（预填表单）
DELETE /api/v1/schedules/{id}       删除日程（显式，无自动删除）
GET  /api/v1/schedules/reminders/due  获取到期提醒（供前端轮询）
POST /api/v1/schedules/reminders/{id}/fire  标记提醒已触发
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from deps import get_current_user
from models import schedule as schedule_model
from services import schedule_service

router = APIRouter(prefix="/schedules", tags=["schedules"])


class CreateUserScheduleRequest(BaseModel):
    """用户自建日程请求体。"""

    schedule_type: str = Field(
        ..., description="assessment/written/interview/other"
    )
    event_time: str = Field(
        ..., description="ISO 8601 datetime，如 2025-01-15T14:30:00+08:00"
    )
    company: str | None = Field("", description="公司名")
    job_title: str | None = Field("", description="岗位名")
    duration_minutes: int = Field(60, ge=1, le=1440, description="时长（分钟）")
    meeting_link: str | None = Field("", description="会议/笔试/测评链接")
    notes: str | None = Field("", description="备注")
    reminder_offsets_minutes: list[int] | None = Field(
        None,
        description="提前提醒分钟数列表，如 [120, 30] 表示提前 2h、30min。"
        "留空则用默认 [120, 30]。",
    )


class AIExtractRequest(BaseModel):
    """AI 提取日程请求体。"""

    subject: str = Field("", description="邮件主题（可选）")
    body: str = Field(..., min_length=1, description="邮件正文 / 任意文本")


@router.get("")
async def list_schedules(user: dict = Depends(get_current_user)):
    schedules = await schedule_model.list_schedules_with_reminders(user["id"])
    return {"schedules": schedules}


@router.post("")
async def create_user_schedule(
    req: CreateUserScheduleRequest,
    user: dict = Depends(get_current_user),
):
    """用户自建日程。校验 + 创建 + 回读验证 + 自动生成提醒。"""
    try:
        result = await schedule_service.create_user_schedule(
            user_id=user["id"],
            schedule_type=req.schedule_type,
            event_time=req.event_time,
            company=req.company,
            job_title=req.job_title,
            duration_minutes=req.duration_minutes,
            meeting_link=req.meeting_link,
            notes=req.notes,
            reminder_offsets_minutes=req.reminder_offsets_minutes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 回读带提醒的完整日程对象返回前端
    full = await schedule_model.list_schedules_with_reminders(user["id"])
    created = next((s for s in full if s["id"] == result["id"]), None)
    return {"schedule": created, "verified": result.get("verified", False)}


@router.post("/ai-extract")
async def ai_extract_schedule(
    req: AIExtractRequest,
    user: dict = Depends(get_current_user),
):
    """AI 从邮件正文提取日程信息。仅返回结构化字段，不创建日程。

    用法：用户粘贴邮件正文 → AI 提取 → 前端预填表单 → 用户确认后
    再调 POST /schedules 提交。
    """
    try:
        result = await schedule_service.ai_extract_schedule(
            user_id=user["id"], subject=req.subject, body=req.body
        )
    except ValueError as e:
        # AI 服务不可用 / 超时 / 提取失败统一返回 400（用户可重试）
        raise HTTPException(status_code=400, detail=str(e))
    return {"extracted": result}


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
