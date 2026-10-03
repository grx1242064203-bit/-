"""邮件服务（Resend HTTP API）。

- send_verification_code(email, code)：通过 Resend 发送 6 位验证码邮件
- Resend 不可用（无 API Key 或调用失败）时打印验证码到 stderr（开发模式降级）
"""
import sys

import httpx

from config import get_settings

RESEND_API_URL = "https://api.resend.com/emails"
# 发件人地址：生产环境需在 Resend 控制台验证自有域名；
# 未验证域名用 onboarding@resend.dev（Resend 默认提供的沙箱发件人）。
FROM_EMAIL = "onboarding@resend.dev"


async def send_verification_code(email: str, code: str) -> None:
    """发送 6 位验证码邮件。Resend 不可用时降级到 stderr 打印（开发模式）。"""
    settings = get_settings()
    if not settings.RESEND_API_KEY:
        print(
            f"[email_service] RESEND_API_KEY 未配置 → 开发模式降级："
            f"验证码 {code}（收件人 {email}，6 小时内有效）",
            file=sys.stderr,
        )
        return

    payload = {
        "from": FROM_EMAIL,
        "to": [email],
        "subject": "【求职搭子】邮箱验证码",
        "text": (
            f"你的求职搭子验证码是：{code}\n"
            "该验证码 6 小时内有效。\n"
            "如果不是你本人操作，请忽略此邮件。"
        ),
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 开发模式降级，吞掉所有异常
        print(
            f"[email_service] Resend 调用失败 ({exc!r}) → 开发模式降级："
            f"验证码 {code}（收件人 {email}）",
            file=sys.stderr,
        )
