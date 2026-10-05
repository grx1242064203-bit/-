"""邮件任务 LLM 提取服务。

异步流程：
1. imap_service.sync_account 抓邮件 → email_classifier.classify_only 初筛
2. 命中 → email_model.create_task(extract_status="pending", 字段为空)
3. 后台调 extract_task_fields(task_id, ...) → LLM 提取 → update_task_extract(llm_done)
4. LLM 失败/超时 → 回退规则提取 → update_task_extract(rule_fallback)

设计要点：
- 复用 LLMProxyService.extract_schedule_from_text（已在日程页 AI 提取验证过）
- LLM 失败不阻塞同步流程（异步触发，失败回退规则）
- 字段映射：LLM 返回 task_type→email_tasks.task_type，但 task_type 已被初筛赋值，
  仅当 LLM 给出更具体的类型且与初筛一致时保留 LLM 的；不一致时仍以初筛为准
  （初筛用关键词，对类型判断更准；LLM 对字段提取更准）
"""
import logging
import traceback
from typing import Optional

from config import get_settings
from models import email as email_model
from services import email_classifier

logger = logging.getLogger(__name__)


def _fallback_to_rules(
    subject: str, body: str, sender: str, message_id: str, imap_server: str
) -> dict:
    """LLM 失败后回退到规则提取。返回与 LLM 同结构的 dict（不含 confidence）。"""
    rule_data = email_classifier.classify_and_extract(
        subject=subject,
        body=body,
        sender=sender,
        message_id=message_id,
        imap_server=imap_server,
    )
    return rule_data or {}


async def extract_task_fields(
    task_id: str,
    user_id: str,
    subject: str,
    body: str,
    sender: str,
    message_id: str,
    imap_server: str,
) -> dict:
    """LLM 提取邮件任务字段并回填。返回提取结果 dict。

    失败时回退到规则提取，并标记 extract_status=rule_fallback。
    任何异常都不抛出（异步任务，失败仅记日志）。
    """
    from services.llm_proxy import LLMProxyService

    settings = get_settings()
    proxy = LLMProxyService(api_key=settings.DEEPSEEK_API_KEY)

    extracted: dict = {}
    extract_status = email_model.EXTRACT_STATUS_LLM_DONE

    try:
        extracted = proxy.extract_schedule_from_text(subject, body)
        # LLM 返回的 task_type 仅用于校验，不覆盖初筛（初筛更准）
        # 字段映射：meeting_link → event_link
        # notes 拼接邮件主题（便于用户在确认卡片看到上下文）
        notes = extracted.get("notes", "")
        if subject and subject not in (notes or ""):
            notes = f"{subject} | {notes}".strip(" |")
        extracted["notes"] = notes
        extracted["event_link"] = extracted.get("meeting_link")
    except TimeoutError as e:
        logger.warning(
            f"LLM 提取超时 (task_id={task_id}): {e}. 回退到规则提取"
        )
        extract_status = email_model.EXTRACT_STATUS_RULE_FALLBACK
        extracted = _fallback_to_rules(subject, body, sender, message_id, imap_server)
    except RuntimeError as e:
        logger.warning(
            f"LLM 提取失败 (task_id={task_id}): {e}. 回退到规则提取"
        )
        extract_status = email_model.EXTRACT_STATUS_RULE_FALLBACK
        extracted = _fallback_to_rules(subject, body, sender, message_id, imap_server)
    except Exception as e:
        logger.error(
            f"LLM 提取异常 (task_id={task_id}): {e!r}\n{traceback.format_exc()}"
        )
        extract_status = email_model.EXTRACT_STATUS_LLM_FAILED
        extracted = _fallback_to_rules(subject, body, sender, message_id, imap_server)
        # 规则也失败（extracted 为空）→ 仅标记 llm_failed，字段保留 None
        if not extracted:
            await email_model.update_task_extract_status(
                task_id, user_id, email_model.EXTRACT_STATUS_LLM_FAILED
            )
            return {"extract_status": email_model.EXTRACT_STATUS_LLM_FAILED}

    # 回填到 DB（COALESCE 不会覆盖已有非空值，但这里 task 是新创建的，字段都是 None）
    await email_model.update_task_extract(
        task_id=task_id,
        user_id=user_id,
        company=extracted.get("company"),
        job_title=extracted.get("job_title"),
        event_time=extracted.get("event_time"),
        event_link=extracted.get("event_link") or extracted.get("meeting_link"),
        notes=extracted.get("notes"),
        extract_status=extract_status,
    )

    # 增加配额计数（仅 LLM 成功时）
    if extract_status == email_model.EXTRACT_STATUS_LLM_DONE:
        try:
            from services.quota_service import increment_usage
            increment_usage(user_id)
        except Exception as e:
            logger.warning(
                f"increment_usage 写入失败(extract_task_fields, "
                f"user_id={user_id}): {e!r}"
            )

    return {**extracted, "extract_status": extract_status}
