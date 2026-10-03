"""LLM 代理接口测试。

覆盖（spec 验收）：
- mock LLMProxyService（不真正调 DeepSeek）
- 测试配额超限返回 429
- 测试无 token 返回 401
- 测试 LLM 异常返回 503

认证：T3 已落地真 JWT（deps.get_current_user 调 jwt_service.verify_token +
models.user.get_user_by_id）。测试用 jwt_service.create_access_token 签发
真 JWT，并 mock deps.get_user_by_id 返回假用户，避免触碰真实 SQLite users 表。

依赖未安装时（CI/无 pip install 场景）整套测试优雅跳过，与 T2/T5 约定一致。
"""
import os
import tempfile

# 必须在任何 job_api 模块 import 前设置隔离 DB（quota_service 模块级单例
# 在首次 _get_conn() 时读取此环境变量；TestClient 触发首次请求时才初始化）
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix="_test_llm_quota.db")
os.environ["AUTH_DB_PATH"] = _DB_PATH

import pytest  # noqa: E402

# fastapi / pydantic / jose / aiosqlite / passlib / slowapi 任一缺失则整套跳过
# （不阻塞 py_compile；依赖安装后即恢复执行）
pytest.importorskip("fastapi")
pytest.importorskip("pydantic")
pytest.importorskip("pydantic_settings")
pytest.importorskip("jose")
pytest.importorskip("aiosqlite")
pytest.importorskip("passlib")
pytest.importorskip("bcrypt")
pytest.importorskip("slowapi")
pytest.importorskip("httpx")

from unittest.mock import AsyncMock, patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from services import quota_service  # noqa: E402
from services.jwt_service import create_access_token  # noqa: E402

# T3 真 JWT：签发一个真实 token，sub=test-user-id（mock 的 get_user_by_id 会
# 返回该 id 的用户）
_TEST_USER_ID = "test-user-id-0000"
_FAKE_USER = {
    "id": _TEST_USER_ID,
    "email": "test@job-assistant.local",
    "password_hash": "(redacted)",
    "is_verified": True,
    "device_fingerprint": None,
    "created_at": "2026-10-03T00:00:00+00:00",
    "last_login_at": None,
}


def _make_token() -> str:
    """签发真实 JWT（用 settings.JWT_SECRET，T3 的 verify_token 会通过）。"""
    return create_access_token(_TEST_USER_ID)


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_make_token()}"}


@pytest.fixture(scope="module")
def client():
    """模块级 TestClient（启动 lifespan，结束自动清理）。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_quota_each():
    """每个测试前清空 llm_usage 表，避免测试间配额状态泄漏。"""
    quota_service._reset_for_test()
    yield
    quota_service._reset_for_test()


@pytest.fixture(autouse=True)
def _mock_get_user_by_id():
    """mock deps.get_user_by_id → 返回 _FAKE_USER，避免触碰真实 users 表。

    必须 patch deps 模块的本地名（deps.py 用 ``from models.user import
    get_user_by_id`` 把名字绑定到 deps 模块上，patch 原模块不生效）。
    """
    with patch("deps.get_user_by_id", new=AsyncMock(return_value=_FAKE_USER)):
        yield


# ====== 401：缺/无效 token ======

def test_parse_resume_no_token_returns_401(client):
    """无 Bearer Token → 401。"""
    resp = client.post("/api/v1/llm/parse-resume", json={"resume_text": "test"})
    assert resp.status_code == 401


def test_supplement_no_token_returns_401(client):
    """无 Bearer Token → 401。"""
    resp = client.post(
        "/api/v1/llm/supplement",
        json={"user_edited": {"directions": ["后端开发"]}, "resume_text": ""},
    )
    assert resp.status_code == 401


def test_parse_resume_invalid_token_returns_401(client):
    """无效 Bearer Token → 401（T3 deps.get_current_user 验签失败）。"""
    resp = client.post(
        "/api/v1/llm/parse-resume",
        json={"resume_text": "test"},
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert resp.status_code == 401


# ====== 200：mock proxy 正常返回 ======

def test_parse_resume_with_mock_proxy(client):
    """mock LLMProxyService.parse_resume → 200 + 期望结构。"""
    fake_result = {
        "keywords": [
            {"kw": "Python", "standard": "python",
             "category": "hard_skill", "weight": 4.0},
        ],
        "fit_directions": [
            {"direction": "后端开发", "weight": 0.8,
             "cat_key": "dev", "sub_key": "backend"},
        ],
    }
    with patch("routers.llm._proxy") as mock_proxy:
        mock_proxy.parse_resume.return_value = fake_result
        resp = client.post(
            "/api/v1/llm/parse-resume",
            json={"resume_text": "Python 开发"},
            headers=_auth_headers(),
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["keywords"] == fake_result["keywords"]
    assert body["fit_directions"] == fake_result["fit_directions"]
    # 调用成功后用量 +1（user_id 取自 JWT sub）
    quota = quota_service.get_user_quota(_TEST_USER_ID)
    assert quota["used"] == 1


def test_supplement_with_mock_proxy(client):
    """mock LLMProxyService.supplement → 200 + hard_skills 取自 new_skills。"""
    fake_result = {
        "fit_directions": [
            {"direction": "AI Agent开发", "weight": 0.7},
        ],
        "new_skills": [
            {"kw": "LangChain", "weight": 3.0,
             "category": "hard_skill", "source": "ai_supplemented"},
        ],
        "structured_keywords": [],
        "new_directions": [],
    }
    with patch("routers.llm._proxy") as mock_proxy:
        mock_proxy.supplement.return_value = fake_result
        resp = client.post(
            "/api/v1/llm/supplement",
            json={"user_edited": {"directions": ["AI Agent开发"]},
                  "resume_text": "Python"},
            headers=_auth_headers(),
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["fit_directions"] == fake_result["fit_directions"]
    assert body["hard_skills"] == fake_result["new_skills"]


# ====== 429：配额超限 ======

def test_quota_exceeded_returns_429(client):
    """用量达上限后再请求 → 429，且不调用 LLM。"""
    # 把配额用满（默认 5 次）
    for _ in range(quota_service.DEFAULT_DAILY_LIMIT):
        quota_service.increment_usage(_TEST_USER_ID)
    quota = quota_service.get_user_quota(_TEST_USER_ID)
    assert quota["remaining"] == 0

    with patch("routers.llm._proxy") as mock_proxy:
        mock_proxy.parse_resume.return_value = {"keywords": [], "fit_directions": []}
        resp = client.post(
            "/api/v1/llm/parse-resume",
            json={"resume_text": "test"},
            headers=_auth_headers(),
        )
    assert resp.status_code == 429
    body = resp.json()
    assert "配额" in body["detail"] or "limit" in body["detail"].lower()
    # 配额超限不应调用 LLM
    mock_proxy.parse_resume.assert_not_called()


def test_quota_exceeded_supplement_returns_429(client):
    """supplement 同样受配额约束。"""
    for _ in range(quota_service.DEFAULT_DAILY_LIMIT):
        quota_service.increment_usage(_TEST_USER_ID)

    with patch("routers.llm._proxy") as mock_proxy:
        mock_proxy.supplement.return_value = {
            "fit_directions": [], "new_skills": [],
        }
        resp = client.post(
            "/api/v1/llm/supplement",
            json={"user_edited": {"directions": ["后端开发"]}, "resume_text": ""},
            headers=_auth_headers(),
        )
    assert resp.status_code == 429
    mock_proxy.supplement.assert_not_called()


# ====== 503：LLM 异常 ======

def test_parse_resume_llm_failure_returns_503(client):
    """LLM 异常（缺 API Key / 超时 / DeepSeek 不可用）→ 503，且不增加用量。"""
    with patch("routers.llm._proxy") as mock_proxy:
        mock_proxy.parse_resume.side_effect = RuntimeError(
            "DEEPSEEK_API_KEY 未配置"
        )
        resp = client.post(
            "/api/v1/llm/parse-resume",
            json={"resume_text": "test"},
            headers=_auth_headers(),
        )
    assert resp.status_code == 503
    quota = quota_service.get_user_quota(_TEST_USER_ID)
    assert quota["used"] == 0


def test_supplement_llm_failure_returns_503(client):
    """supplement LLM 异常 → 503。"""
    with patch("routers.llm._proxy") as mock_proxy:
        mock_proxy.supplement.side_effect = TimeoutError("LLM supplement 超时")
        resp = client.post(
            "/api/v1/llm/supplement",
            json={"user_edited": {"directions": ["后端"]}, "resume_text": ""},
            headers=_auth_headers(),
        )
    assert resp.status_code == 503


# ====== 422：请求体校验失败 ======

def test_parse_resume_empty_resume_text_returns_422(client):
    """resume_text 为空 → 422（Pydantic Field min_length=1）。"""
    with patch("routers.llm._proxy"):
        resp = client.post(
            "/api/v1/llm/parse-resume",
            json={"resume_text": ""},
            headers=_auth_headers(),
        )
    assert resp.status_code == 422


# ====== 配额递增逻辑（直接验证 quota_service） ======

def test_quota_increment_logic():
    """直接验证 quota_service 的递增 + 上限行为（不通过 HTTP）。"""
    quota_service._reset_for_test()
    user_id = "test-user-direct"

    q = quota_service.get_user_quota(user_id)
    assert q == {"limit": 5, "used": 0, "remaining": 5}

    for i in range(1, 6):
        ok = quota_service.increment_usage(user_id)
        assert ok is True
        q = quota_service.get_user_quota(user_id)
        assert q["used"] == i
        assert q["remaining"] == 5 - i

    # 第 6 次：超额，返回 False，不写入
    ok = quota_service.increment_usage(user_id)
    assert ok is False
    q = quota_service.get_user_quota(user_id)
    assert q["used"] == 5
    assert q["remaining"] == 0
