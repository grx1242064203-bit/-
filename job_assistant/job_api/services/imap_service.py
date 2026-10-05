"""IMAP 邮件抓取服务。

使用 Python stdlib imaplib + email，无额外依赖。
抓取指定账户的未读邮件，解析后存入 emails 表，再调分类器生成 email_tasks。
"""
import email
import imaplib
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Optional

from models import email as email_model
from models import email_account as account_model
from services import email_classifier


def _decode_str(value: Optional[str]) -> str:
    """解码邮件头字段（可能是 MIME 编码）。"""
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            except (LookupError, TypeError):
                decoded.append(part.decode("utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return "".join(decoded)


def _get_body(msg: email.message.Message) -> tuple[str, str]:
    """提取邮件纯文本和 HTML 正文。"""
    text_parts = []
    html_parts = []

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" in disp:
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                content = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ctype == "text/plain":
                text_parts.append(content)
            elif ctype == "text/html":
                html_parts.append(content)
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                content = payload.decode(charset, errors="replace")
                if msg.get_content_type() == "text/html":
                    html_parts.append(content)
                else:
                    text_parts.append(content)
        except Exception:
            pass

    return "\n".join(text_parts), "\n".join(html_parts)


async def test_connection(
    imap_server: str, imap_port: int, username: str, password: str
) -> dict:
    """测试 IMAP 连接。返回 {ok: bool, error: str}。

    协议流程说明:
    - IMAP4_SSL(server, port) 建立 SSL 连接
    - login(user, pass) 认证
    - select("INBOX", readonly=True) 选邮箱(只读)
    - logout() 关闭连接

    注意: readonly=True 选邮箱后不需要调 close()
    - close() 是 select() 的逆操作,但只用于可写模式
    - 在 readonly 模式下调 close() 部分服务器(如 163)会抛异常
    - 正确流程是 select(readonly=True) → 直接 logout()
    """
    import logging

    log = logging.getLogger(__name__)
    try:
        log.info(
            "IMAP 连接测试: server=%s port=%s user=%s", imap_server, imap_port, username
        )
        conn = imaplib.IMAP4_SSL(imap_server, imap_port, timeout=15)
        conn.login(username, password)
        # 选 INBOX 验证登录成功 + 有权限读邮件
        typ, data = conn.select("INBOX", readonly=True)
        if typ != "OK":
            err = f"select INBOX 失败: {data!r}"
            log.warning(err)
            return {"ok": False, "error": err}
        # readonly 模式不调 close(),直接 logout
        conn.logout()
        log.info("IMAP 连接成功: %s@%s", username, imap_server)
        return {"ok": True, "error": ""}
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        log.warning("IMAP 连接失败: %s server=%s user=%s", err, imap_server, username)
        return {"ok": False, "error": err}


async def sync_account(account_id: str, user_id: str, limit: int = 50) -> dict:
    """同步指定邮箱账户的未读邮件。
    返回 {fetched: int, tasks_created: int, skipped: int, error: str}。
    """
    account = await account_model.get_account(account_id, user_id)
    if not account:
        return {"fetched": 0, "tasks_created": 0, "skipped": 0, "error": "邮箱账户不存在"}

    try:
        conn = imaplib.IMAP4_SSL(
            account["imap_server"], account["imap_port"], timeout=30
        )
        conn.login(account["username"], account["password"])
        conn.select("INBOX", readonly=True)
    except Exception as e:
        return {"fetched": 0, "tasks_created": 0, "skipped": 0, "error": f"IMAP 连接失败: {e}"}

    fetched = 0
    tasks_created = 0
    skipped = 0

    try:
        # 搜索最近的邮件（按序号倒序，取最新 limit 封）
        status, data = conn.search(None, "ALL")
        if status != "OK":
            return {"fetched": 0, "tasks_created": 0, "skipped": 0, "error": "搜索邮件失败"}

        msg_ids = data[0].split()
        # 取最新的 limit 封
        msg_ids = msg_ids[-limit:] if msg_ids else []

        for msg_id in msg_ids:
            status, msg_data = conn.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data[0]:
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            message_id = msg.get("Message-ID", f"local-{msg_id.decode()}")
            subject = _decode_str(msg.get("Subject", ""))
            sender = _decode_str(msg.get("From", ""))
            from_addr = msg.get("From", "")

            # 解析时间
            received_at = None
            date_str = msg.get("Date")
            if date_str:
                try:
                    dt = parsedate_to_datetime(date_str)
                    received_at = dt.isoformat()
                except Exception:
                    received_at = None

            body_text, body_html = _get_body(msg)
            raw_headers = str(msg.items())

            # 存入 emails 表（message_id 去重）
            email_record = await email_model.insert_email(
                user_id=user_id,
                account_id=account_id,
                message_id=message_id,
                subject=subject,
                sender=sender,
                from_addr=from_addr,
                received_at=received_at or "",
                body_text=body_text,
                body_html=body_html,
                raw_headers=raw_headers,
            )

            if email_record is None:
                # 已存在，跳过
                skipped += 1
                continue

            fetched += 1

            # 分类并创建任务
            task_data = email_classifier.classify_and_extract(
                subject=subject,
                body=body_text or body_html,
                sender=sender,
                message_id=message_id,
                imap_server=account["imap_server"],
            )

            if task_data:
                await email_model.create_task(
                    user_id=user_id,
                    email_id=email_record["id"],
                    **task_data,
                )
                tasks_created += 1
            else:
                skipped += 1

        await account_model.update_last_sync(account_id)
        return {
            "fetched": fetched,
            "tasks_created": tasks_created,
            "skipped": skipped,
            "error": "",
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass
