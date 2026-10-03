"""认证流程端到端测试。

- mock email_service（不真正发邮件）
- 临时 SQLite（DATA_DIR 指向 tmp_path）
- 覆盖：注册 → 验证 → 登录 → refresh
- 边界：重复已验证注册返回 409；未验证用户登录返回 403；错误密码返回 401；
        重复未验证注册走重发码分支（返回 200，needs_verify=True）
"""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def temp_env(tmp_path, monkeypatch):
    """注入临时数据目录 + 测试用密钥；清掉 get_settings 单例缓存。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JWT_SECRET", "test-secret-not-for-prod")
    monkeypatch.setenv("RESEND_API_KEY", "")
    from config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client(temp_env):
    """构造 TestClient；重置 auth_service 建表标志 + 测试期禁用 rate limit。"""
    import routers.auth as auth_router
    import services.auth_service as auth_svc
    auth_svc.reset_init_flag()
    auth_router.limiter.enabled = False
    from main import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def mock_send_email():
    """所有测试都 mock email_service.send_verification_code，不真正发邮件。"""
    with patch(
        "services.email_service.send_verification_code",
        new_callable=AsyncMock,
    ) as mocked:
        yield mocked


def _read_code(email: str) -> str:
    """从 DB 读取该 email 当前未使用的验证码（绕过 email mock）。"""
    from config import get_settings

    db_path = Path(get_settings().DATA_DIR) / "auth.db"

    async def _read():
        async with aiosqlite.connect(str(db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT code FROM verification_codes "
                "WHERE email = ? ORDER BY expires_at DESC LIMIT 1",
                (email,),
            )
            row = await cursor.fetchone()
            return row["code"] if row else ""

    return asyncio.run(_read())


def _set_verified_directly(email: str) -> None:
    """测试辅助：直接将 email 标记为已验证（绕过验证码流程）。"""
    from models.user import set_verified
    asyncio.run(set_verified(email))


def test_register_verify_login_refresh(client, mock_send_email):
    # 1) 注册 → 未验证用户 + 验证码写入 DB + email 被调用
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "secret123"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["needs_verify"] is True
    user_id = body["user_id"]
    assert user_id
    mock_send_email.assert_awaited_once()

    code = _read_code("alice@example.com")
    assert code and len(code) == 6 and code.isdigit()

    # 2) 验证邮箱 → 拿 token
    resp = client.post(
        "/api/v1/auth/verify-email",
        json={"email": "alice@example.com", "code": code},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    expires_at = resp.json()["expires_at"]
    assert token
    assert isinstance(expires_at, int) and expires_at > 0

    # 3) 登录 → 拿 token
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "secret123"},
    )
    assert resp.status_code == 200, resp.text
    login_token = resp.json()["token"]
    assert login_token

    # 4) refresh → 拿新 token
    resp = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {login_token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["token"]


def test_duplicate_verified_register_returns_409(client):
    # 第一次注册 bob
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "secret123"},
    )
    assert resp.status_code == 200
    # 直接标记为已验证（绕过验证码）
    _set_verified_directly("bob@example.com")
    # 再次注册 → 409
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "another-pwd-456"},
    )
    assert resp.status_code == 409, resp.text


def test_duplicate_unverified_register_resends_code(client, mock_send_email):
    # 第一次注册 carol（未验证）
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "secret123"},
    )
    assert resp.status_code == 200
    first_user_id = resp.json()["user_id"]
    mock_send_email.reset_mock()

    # 再次注册（仍未验证） → 200，重发验证码，user_id 不变
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "another-pwd-456"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["needs_verify"] is True
    assert body["user_id"] == first_user_id
    mock_send_email.assert_awaited_once()


def test_unverified_login_returns_403(client):
    # 注册但不验证
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "dave@example.com", "password": "secret123"},
    )
    assert resp.status_code == 200

    # 立即登录 → 403
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "dave@example.com", "password": "secret123"},
    )
    assert resp.status_code == 403, resp.text


def test_wrong_password_returns_401(client):
    # 注册 + 直接标记已验证
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "eve@example.com", "password": "secret123"},
    )
    assert resp.status_code == 200
    _set_verified_directly("eve@example.com")

    # 错误密码 → 401
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "eve@example.com", "password": "wrong-password"},
    )
    assert resp.status_code == 401, resp.text


def test_refresh_with_invalid_token_returns_401(client):
    resp = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert resp.status_code == 401, resp.text
