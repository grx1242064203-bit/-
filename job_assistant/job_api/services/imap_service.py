"""IMAP 邮件抓取服务。

使用 Python stdlib imaplib + email，无额外依赖。
抓取指定账户的未读邮件，解析后存入 emails 表，再调分类器生成 email_tasks。
"""
import email
import imaplib
import logging
import socket
import ssl
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Optional

from models import email as email_model
from models import email_account as account_model
from services import email_classifier

log = logging.getLogger(__name__)


def _build_ssl_context() -> ssl.SSLContext:
    """构建兼容国内邮箱(163/QQ)的 SSLContext。

    国内邮箱 IMAP 服务器对 TLS 1.3 握手兼容性较差,常见错误:
    - SSLError: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol
    - 原因: Python 3.14 默认 ssl.PROTOCOL_TLS_CLIENT 协商到 TLS 1.3,
      但 163 服务器在 TLS 1.3 握手时意外关闭连接(可能是中间件/风控)

    修复: 强制最高版本 TLS 1.2,禁用 TLS 1.3,保留 TLS 1.2 兼容性。
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # 设置最低版本 TLS 1.0(兼容旧服务器),最高版本 TLS 1.2(禁用 TLS 1.3)
    ctx.minimum_version = ssl.TLSVersion.TLSv1
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    # 验证证书(默认行为)
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    # 加载系统 CA 证书
    ctx.load_default_certs()
    return ctx


def _create_imap_ssl_connection(
    imap_server: str, imap_port: int, timeout: int = 15
) -> imaplib.IMAP4_SSL:
    """创建 IMAP4_SSL 连接,使用自定义 SSLContext(禁用 TLS 1.3)。

    兼容 Python 3.9+ 的 timeout 参数。
    """
    ctx = _build_ssl_context()
    # imaplib.IMAP4_SSL 支持传入 ssl_context 参数
    return imaplib.IMAP4_SSL(
        host=imap_server,
        port=imap_port,
        ssl_context=ctx,
        timeout=timeout,
    )


def _send_imap_id_command(conn: imaplib.IMAP4_SSL) -> None:
    """发送 IMAP ID 命令声明客户端身份(兼容 163/126 邮箱风控)。

    163/126 邮箱要求第三方客户端在 login 之后立即发送 ID 命令,否则会:
    - 拒绝后续 select 命令
    - 主动断开连接(表现为 SSLError: UNEXPECTED_EOF_WHILE_READING)
    - 返回 "Unsafe Login. Please contact kefu@188.com"

    IMAP ID 扩展(RFC 2971) 格式:
      C: A1 ID ("name" "OfferPartner" "version" "1.0" "vendor" "OfferPartner")
      S: * ID ("name" "ImailServer" "version" "1.0")
      S: A1 OK ID completed

    参数都是任意字符串,服务器只关心客户端是否发送了 ID 命令,
    不验证身份真实性。163 邮箱看 ID 命令是否存在,不查具体值。

    其他邮箱(QQ/Gmail/Outlook)也支持 ID 命令,无副作用。
    """
    try:
        # imaplib 没有原生 ID 命令支持,需要手动构造
        # 使用 _simple_command 名称为 "ID",参数为带括号的字符串列表
        args = (
            '("name" "OfferPartner" '
            '"version" "1.0" '
            '"vendor" "OfferPartner" '
            '"support-email" "support@offer-partner.com")'
        )
        # conn._simple_command 返回 (typ, response_data),typ 应为 "OK"
        typ, _ = conn._simple_command("ID", args)
        if typ != "OK":
            log.warning("IMAP ID 命令返回非 OK: %s", typ)
        else:
            log.info("IMAP ID 命令发送成功")
        # 读取并丢弃服务器的 ID 响应,避免影响后续命令
        try:
            conn._get_tagged_response()
        except Exception:
            pass
    except Exception as e:
        # ID 命令失败不阻塞主流程(部分服务器可能不支持 ID 扩展)
        log.warning("IMAP ID 命令发送失败(不阻塞): %s: %s", type(e).__name__, e)


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

    流程:
    1. SSL 连接(禁用 TLS 1.3)
    2. login 登录
    3. 发送 ID 命令(兼容 163 邮箱风控)
    4. select INBOX 验证权限
    5. logout
    """
    try:
        log.info(
            "IMAP 连接测试: server=%s port=%s user=%s", imap_server, imap_port, username
        )
        conn = _create_imap_ssl_connection(imap_server, imap_port, timeout=15)
        conn.login(username, password)
        # 关键: 登录后立即发送 ID 命令,否则 163 服务器会断开连接
        _send_imap_id_command(conn)
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
        # 复用禁用 TLS 1.3 的 SSLContext(兼容国内邮箱)
        conn = _create_imap_ssl_connection(
            account["imap_server"], account["imap_port"], timeout=30
        )
        conn.login(account["username"], account["password"])
        # 关键: 登录后立即发送 ID 命令,否则 163 服务器会断开连接
        _send_imap_id_command(conn)
        conn.select("INBOX", readonly=True)
    except Exception as e:
        return {"fetched": 0, "tasks_created": 0, "skipped": 0, "error": f"IMAP 连接失败: {type(e).__name__}: {e}"}

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
