"""日程创建服务（含回读验证）+ 邮件任务确认编排 + AI 提取编排。

稳定性规则：
1. 创建日程后必须回读验证（比对关键字段）
2. 不允许 AI 自动删除日程（只有显式 delete_schedule 接口）
3. AI 提取仅返回结构化数据，不直接创建日程——用户确认后再提交
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from models import application as application_model
from models import email as email_model
from models import schedule as schedule_model

logger = logging.getLogger(__name__)

# 用户自建日程允许的 schedule_type（在 assessment/written/interview 基础上增加 other）
SCHEDULE_TYPE_OTHER = "other"
VALID_USER_SCHEDULE_TYPES = {
    schedule_model.SCHEDULE_TYPE_ASSESSMENT,
    schedule_model.SCHEDULE_TYPE_WRITTEN,
    schedule_model.SCHEDULE_TYPE_INTERVIEW,
    SCHEDULE_TYPE_OTHER,
}

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


def _validate_event_time(event_time: str) -> str:
    """校验 event_time 是可解析的 ISO 字符串。失败抛 ValueError。

    兼容用户输入 "2025-01-15 14:30" 这种带空格的伪 ISO（自动转 T）。
    """
    if not event_time or not isinstance(event_time, str):
        raise ValueError("event_time 不能为空")
    normalized = event_time.strip().replace(" ", "T")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as e:
        raise ValueError(
            f"event_time 格式无效，请用 ISO 8601（如 2025-01-15T14:30:00）：{e}"
        )
    # 如果是 naive datetime，补上本地时区（+08:00），避免存 UTC 被错读
    if dt.tzinfo is None:
        from datetime import timezone, timedelta
        cst = timezone(timedelta(hours=8))
        dt = dt.replace(tzinfo=cst)
    return dt.isoformat()


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
    reminder_offsets_minutes: Optional[list[int]] = None,
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
        reminder_offsets_minutes=reminder_offsets_minutes,
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


async def create_user_schedule(
    user_id: str,
    schedule_type: str,
    event_time: str,
    company: Optional[str] = None,
    job_title: Optional[str] = None,
    duration_minutes: int = 60,
    meeting_link: Optional[str] = None,
    notes: Optional[str] = None,
    reminder_offsets_minutes: Optional[list[int]] = None,
) -> dict:
    """用户自建日程入口。

    与邮件流程解耦——用户在日程页直接填写表单提交。
    校验：schedule_type 必须在白名单内、event_time 可解析。
    创建后回读验证（同邮件流程）。
    """
    if schedule_type not in VALID_USER_SCHEDULE_TYPES:
        raise ValueError(
            f"不支持的日程类型：{schedule_type}。"
            f"可选：{', '.join(sorted(VALID_USER_SCHEDULE_TYPES))}"
        )

    # company/job_title 至少有一个非空（否则日程卡片标题会显示"未知公司"）
    if not (company and company.strip()) and not (job_title and job_title.strip()):
        raise ValueError("公司名和岗位名至少填写一个")

    normalized_time = _validate_event_time(event_time)

    # duration_minutes 合法化
    try:
        duration = int(duration_minutes)
        if duration <= 0:
            duration = 60
    except (ValueError, TypeError):
        duration = 60

    return await create_schedule_with_verify(
        user_id=user_id,
        schedule_type=schedule_type,
        event_time=normalized_time,
        company=(company or "").strip() or None,
        job_title=(job_title or "").strip() or None,
        duration_minutes=duration,
        meeting_link=(meeting_link or "").strip() or None,
        notes=(notes or "").strip() or None,
        reminder_offsets_minutes=reminder_offsets_minutes,
    )


async def ai_extract_schedule(
    user_id: str, subject: str, body: str
) -> dict:
    """AI 从邮件正文提取日程信息。仅返回结构化数据，不创建日程。

    用户在前端粘贴邮件正文，AI 提取后预填表单，用户确认后再调
    create_user_schedule 提交。这样既体现自动化，又保留用户控制权。
    """
    from services.llm_proxy import LLMProxyService
    from config import get_settings

    settings = get_settings()
    proxy = LLMProxyService(api_key=settings.DEEPSEEK_API_KEY)
    try:
        result = proxy.extract_schedule_from_text(subject, body)
    except TimeoutError as e:
        raise ValueError(f"AI 提取超时，请精简正文后重试：{e}")
    except RuntimeError as e:
        raise ValueError(str(e))
    except Exception as e:
        logger.error(f"ai_extract_schedule 失败 (user_id={user_id}): {e!r}", exc_info=True)
        raise ValueError(f"AI 提取失败：{e}")
    return result


async def confirm_email_task(task_id: str, user_id: str) -> dict:
    """确认邮件任务：匹配/创建 application + 创建日程 + 设置提醒 + 标记任务已确认。

    返回 {application_id, schedule_id, application_status}。

    稳定性规则：所有校验前置到函数开头，校验通过后才允许写入数据库。
    避免出现「application 已创建但 schedule 因 event_time 为空失败」的脏数据。
    """
    task = await email_model.get_task(task_id, user_id)
    if not task:
        raise ValueError("任务不存在")
    if task["status"] != email_model.TASK_STATUS_PENDING:
        raise ValueError(f"任务状态非待确认：{task['status']}")

    # ↓↓↓ 全部校验前置：在写入 application/schedule 之前完成所有字段检查
    # 1. task_type 必须可映射
    schedule_type = TASK_TYPE_MAP.get(task["task_type"])
    if not schedule_type:
        raise ValueError(f"未知任务类型：{task['task_type']}")

    # 2. company 和 job_title 至少有一个非空
    company = task.get("company") or ""
    job_title = task.get("job_title") or ""
    if not company.strip() and not job_title.strip():
        raise ValueError(
            "无法确认：公司和岗位均为空，请等待 AI 提取完成或手动补充后再确认"
        )

    # 3. event_time 必须存在（否则日程无法创建）
    event_time = task.get("event_time")
    if not event_time:
        raise ValueError(
            "无法创建日程：邮件未提取到事件时间，请等待 AI 提取完成或手动补充时间后再确认"
        )
    # ↑↑↑ 校验结束，下面才允许写入

    app_status = TASK_TO_STATUS.get(schedule_type, "applied")

    # 1. 匹配/创建 application（复用现有去重逻辑）
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
    schedule = await create_schedule_with_verify(
        user_id=user_id,
        schedule_type=schedule_type,
        event_time=event_time,
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
