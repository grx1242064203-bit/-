"""IMAP 邮件抓取服务。

使用 Python stdlib imaplib + email，无额外依赖。
抓取指定账户的未读邮件，解析后存入 emails 表，再调分类器生成 email_tasks。

异步 LLM 提取流程（用户选定方案）：
1. 抓邮件 → 存 emails 表（去重）
2. email_classifier.classify_only 关键词初筛（零成本，快）
3. 命中 → email_model.create_task(extract_status="pending", 字段为空)
4. asyncio.create_task 触发后台 LLM 提取（不阻塞同步流程）
5. LLM 完成 → update_task_extract(llm_done)；失败 → 回退规则(rule_fallback)

这样同步快（5s），用户看到任务时字段可能还在加载，
用户可手动刷新或点 ✨ AI 重新提取按钮强制重做。
"""
import asyncio
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


def _trigger_async_llm_extract(
    task_id: str,
    user_id: str,
    subject: str,
    body: str,
    sender: str,
    message_id: str,
    imap_server: str,
) -> None:
    """后台异步触发 LLM 提取，不阻塞同步流程。

    使用 asyncio.create_task 而非 await，sync_account 立即返回。
    LLM 失败会自动回退到规则提取。
    """
    async def _runner():
        try:
            from services.email_llm_extractor import extract_task_fields
            await extract_task_fields(
                task_id=task_id,
                user_id=user_id,
                subject=subject,
                body=body,
                sender=sender,
                message_id=message_id,
                imap_server=imap_server,
            )
        except Exception as e:
            log.error(
                f"异步 LLM 提取失败 (task_id={task_id}): {e!r}",
                exc_info=True,
            )

    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_runner())
    except RuntimeError:
        # 无事件循环（如同步测试调用）→ 同步执行
        log.warning("无事件循环，跳过异步 LLM 提取")


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
    - 拒绝后续 select 命令(EXAMINE Unsafe Login)
    - 主动断开连接(SSLError: UNEXPECTED_EOF_WHILE_READING)

    关键: 163 会校验客户端身份字符串,必须是已知邮件客户端才会放行。
    因此伪装成 Foxmail(腾讯出品的国内邮箱客户端,163 白名单)。

    IMAP ID 扩展(RFC 2971) 格式:
      C: A1 ID ("name" "Foxmail" "version" "7.2" "vendor" "Tencent")
      S: * ID ("name" "ImailServer" "version" "1.0")
      S: A1 OK ID completed

    其他邮箱(QQ/Gmail/Outlook)也支持 ID 命令,无副作用。
    """
    try:
        # 伪装成 Foxmail 客户端,163 白名单会放行
        args = (
            '("name" "Foxmail" '
            '"version" "7.2.18.154" '
            '"vendor" "Tencent" '
            '"support-email" "support@foxmail.com")'
        )
        # conn._simple_command 返回 (typ, response_data),typ 应为 "OK"
        typ, _ = conn._simple_command("ID", args)
        if typ != "OK":
            log.warning("IMAP ID 命令返回非 OK: %s", typ)
        else:
            log.info("IMAP ID 命令发送成功(伪装 Foxmail)")
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


async def sync_account(account_id: str, user_id: str, limit: int = 200) -> dict:
    """同步指定邮箱账户的邮件（包括已读）。
    返回 {fetched: int, tasks_created: int, skipped: int, fetch_errors: int, error: str}。

    limit=200: 覆盖大多数用户最近 1-2 个月的邮件,避免漏招。
    搜索 ALL 而非 UNSEEN:用户可能读过招聘邮件后才来同步,不能漏。
    """
    account = await account_model.get_account(account_id, user_id)
    if not account:
        return {"fetched": 0, "tasks_created": 0, "skipped": 0, "fetch_errors": 0, "error": "邮箱账户不存在"}

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
        return {"fetched": 0, "tasks_created": 0, "skipped": 0, "fetch_errors": 0, "error": f"IMAP 连接失败: {type(e).__name__}: {e}"}

    fetched = 0
    tasks_created = 0
    skipped = 0
    fetch_errors = 0

    try:
        # 搜索所有邮件（包括已读）——用户可能先读过邮件才来同步
        status, data = conn.search(None, "ALL")
        if status != "OK":
            return {"fetched": 0, "tasks_created": 0, "skipped": 0, "fetch_errors": 0, "error": "搜索邮件失败"}

        msg_ids = data[0].split()
        total_count = len(msg_ids)
        # 取最新的 limit 封（倒序取,确保最新的优先）
        msg_ids = msg_ids[-limit:] if msg_ids else []
        log.info(
            "IMAP 同步: 账户=%s 总邮件数=%d 取最新 %d 封",
            account["email"], total_count, len(msg_ids)
        )

        for msg_id in msg_ids:
            try:
                status, msg_data = conn.fetch(msg_id, "(RFC822)")
                if status != "OK" or not msg_data[0]:
                    fetch_errors += 1
                    log.warning("fetch 邮件失败 msg_id=%s status=%s", msg_id, status)
                    continue
            except Exception as e:
                fetch_errors += 1
                log.warning("fetch 邮件异常 msg_id=%s: %s: %s", msg_id, type(e).__name__, e)
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
            try:
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
            except Exception as e:
                fetch_errors += 1
                log.warning("insert_email 失败 msg_id=%s subject=%s: %s", msg_id, subject[:50], e)
                continue

            if email_record is None:
                # 已存在，跳过（但仍计入 skipped）
                skipped += 1
                continue

            fetched += 1

            # 1) 关键词初筛（零成本，快）——过滤广告/宣讲会
            task_type = email_classifier.classify_only(
                subject=subject, body=body_text or body_html
            )
            if task_type is None:
                skipped += 1
                continue

            # 2) 立即创建 pending 任务（字段为空，extract_status=pending）
            # 同步流程不等 LLM，立即返回；用户在前端会看到「AI 提取中...」徽章
            email_link = email_classifier.build_email_link(
                message_id, account["imap_server"]
            )
            new_task = await email_model.create_task(
                user_id=user_id,
                email_id=email_record["id"],
                task_type=task_type,
                email_link=email_link,
                notes=f"主题: {subject}",  # 临时 notes，LLM 会覆盖
                extract_status=email_model.EXTRACT_STATUS_PENDING,
            )
            tasks_created += 1

            # 3) 异步触发 LLM 提取（不阻塞同步流程）
            # LLM 完成后回填字段；失败自动回退规则提取
            _trigger_async_llm_extract(
                task_id=new_task["id"],
                user_id=user_id,
                subject=subject,
                body=body_text or body_html or "",
                sender=sender,
                message_id=message_id,
                imap_server=account["imap_server"],
            )

        await account_model.update_last_sync(account_id)
        log.info(
            "IMAP 同步完成: 账户=%s fetched=%d tasks_created=%d skipped=%d fetch_errors=%d",
            account["email"], fetched, tasks_created, skipped, fetch_errors
        )
        return {
            "fetched": fetched,
            "tasks_created": tasks_created,
            "skipped": skipped,
            "fetch_errors": fetch_errors,
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
