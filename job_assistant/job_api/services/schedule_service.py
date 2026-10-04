"""日程创建服务（含回读验证）+ 邮件任务确认编排。

稳定性规则：
1. 创建日程后必须回读验证（比对关键字段）
2. 不允许 AI 自动删除日程（只有显式 delete_schedule 接口）
"""
from typing import Optional

from models import application as application_model
from models import email as email_model
from models import schedule as schedule_model


# task_type → application status 映射
TASK_TO_STATUS = {
    schedule_model.SCHEDULE_TYPE_ASSESSMENT: "assessment",
    schedule_model.SCHEDULE_TYPE_WRITTEN: "applied",  # 笔试通常在投递后
    schedule_model.SCHEDULE_TYPE_INTERVIEW: "interview",
}

# task_type → schedule_type 映射（同名，直接用）
TASK_TYPE_MAP = {
    email_model.TASK_TYPE_ASSESSMENT: schedule_model.SCHEDULE_TYPE_ASSESSMENT,
    email_model.TASK_TYPE_WRITTEN: schedule_model.SCHEDULE_TYPE_WRITTEN,
    email_model.TASK_TYPE_INTERVIEW: schedule_model.SCHEDULE_TYPE_INTERVIEW,
}


async def create_schedule_with_verify(
    user_id: str,
    schedule_type: str,
    event_time: str,
    application_id: Optional[str] = None,
    company: Optional[str] = None,
    job_title: Optional[str] = None,
    duration_minutes: int = 60,
    email_link: Optional[str] = None,
    meeting_link: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """创建日程并回读验证。验证失败抛出 ValueError。"""
    result = await schedule_model.create_schedule(
        user_id=user_id,
        schedule_type=schedule_type,
        event_time=event_time,
        application_id=application_id,
        company=company,
        job_title=job_title,
        duration_minutes=duration_minutes,
        email_link=email_link,
        meeting_link=meeting_link,
        notes=notes,
    )

    # 回读验证
    verify = await schedule_model.get_schedule(result["id"], user_id)
    if not verify:
        raise ValueError("日程创建后回读失败：记录不存在")

    # 比对关键字段
    if verify["schedule_type"] != schedule_type:
        raise ValueError(
            f"回读验证失败：schedule_type 不匹配 "
            f"(期望 {schedule_type}, 实际 {verify['schedule_type']})"
        )
    if verify["event_time"] != event_time:
        raise ValueError(
            f"回读验证失败：event_time 不匹配 "
            f"(期望 {event_time}, 实际 {verify['event_time']})"
        )

    await schedule_model.mark_verified(result["id"])
    return {**result, "verified": True}


async def confirm_email_task(task_id: str, user_id: str) -> dict:
    """确认邮件任务：匹配/创建 application + 创建日程 + 设置提醒 + 标记任务已确认。

    返回 {application_id, schedule_id, application_status}。
    """
    task = await email_model.get_task(task_id, user_id)
    if not task:
        raise ValueError("任务不存在")
    if task["status"] != email_model.TASK_STATUS_PENDING:
        raise ValueError(f"任务状态非待确认：{task['status']}")

    schedule_type = TASK_TYPE_MAP.get(task["task_type"])
    if not schedule_type:
        raise ValueError(f"未知任务类型：{task['task_type']}")

    app_status = TASK_TO_STATUS.get(schedule_type, "applied")

    # 1. 匹配/创建 application（复用现有去重逻辑）
    company = task.get("company") or ""
    job_title = task.get("job_title") or ""
    if not company and not job_title:
        raise ValueError("无法确认：公司和岗位均为空")

    application = await application_model.create_application(
        user_id=user_id,
        company_name=company,
        job_title=job_title,
        status=app_status,
        source="email",
        link_type=None,
        link_id=None,
        email_id=task["email_id"],
    )

    # 2. 创建日程（带回读验证）
    if not task.get("event_time"):
        raise ValueError("无法创建日程：邮件未提取到事件时间，请手动设置")

    schedule = await create_schedule_with_verify(
        user_id=user_id,
        schedule_type=schedule_type,
        event_time=task["event_time"],
        application_id=application["id"],
        company=company,
        job_title=job_title,
        email_link=task.get("email_link"),
        meeting_link=task.get("event_link"),
        notes=task.get("notes"),
    )

    # 3. 标记任务已确认
    await email_model.confirm_task(
        task_id=task_id,
        user_id=user_id,
        application_id=application["id"],
        schedule_id=schedule["id"],
    )

    return {
        "application_id": application["id"],
        "application_status": application["status"],
        "schedule_id": schedule["id"],
        "verified": schedule["verified"],
    }
