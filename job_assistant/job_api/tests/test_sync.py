"""岗位同步接口测试。

Service 层测试仅依赖标准库 sqlite3,不依赖 fastapi,可独立运行。
HTTP 层测试在 fastapi 可用时执行,否则跳过。
"""
import sqlite3
from pathlib import Path

import pytest

from services.sync_service import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    JOB_FIELDS,
    SyncService,
)


def _make_db(tmp_path: Path) -> Path:
    """在临时目录建一个 mock jobs 物理表(spec 字段),插入 10 条。"""
    db = tmp_path / "jobs.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE jobs (
            job_id INTEGER PRIMARY KEY,
            company TEXT,
            title TEXT,
            category TEXT,
            city TEXT,
            requirements TEXT,
            jd_text TEXT,
            apply_url TEXT,
            deadline TEXT,
            source TEXT,
            graduation_match INTEGER,
            is_mt INTEGER,
            updated_at TEXT
        )
        """
    )
    rows = []
    for i in range(1, 11):
        rows.append(
            (
                i,
                f"公司{i}",
                f"岗位{i}",
                "技术",
                "北京",
                "本科",
                f"JD{i}",
                f"http://apply/{i}",
                "2026-12-31",
                "feishu",
                1 if i % 2 == 0 else 0,
                1 if i % 3 == 0 else 0,
                f"2026-01-{i:02d} 00:00:00",
            )
        )
    conn.executemany(
        "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db


# ---------------- Service 层测试 ----------------


def test_get_jobs_since_incremental(tmp_path):
    """since 增量查询:返回 updated_at > since 的全部岗位。"""
    db = _make_db(tmp_path)
    svc = SyncService(db_path=db)
    res = svc.get_jobs_since(since="2026-01-05 00:00:00", limit=500)
    assert res["next_cursor"] is None
    assert len(res["jobs"]) == 5
    assert [j["job_id"] for j in res["jobs"]] == [6, 7, 8, 9, 10]


def test_get_jobs_since_empty_since_returns_all(tmp_path):
    """since 为空表示从头拉取。"""
    db = _make_db(tmp_path)
    svc = SyncService(db_path=db)
    res = svc.get_jobs_since(since="", limit=500)
    assert len(res["jobs"]) == 10
    assert res["jobs"][0]["job_id"] == 1
    assert res["jobs"][-1]["job_id"] == 10


def test_get_jobs_since_pagination(tmp_path):
    """cursor 分页:每页 3 条,跨多页覆盖全部 10 条,末页 next_cursor 为 None。"""
    db = _make_db(tmp_path)
    svc = SyncService(db_path=db)

    page1 = svc.get_jobs_since(since="", limit=3)
    assert len(page1["jobs"]) == 3
    assert [j["job_id"] for j in page1["jobs"]] == [1, 2, 3]
    assert page1["next_cursor"] is not None

    page2 = svc.get_jobs_since(since="", limit=3, cursor=page1["next_cursor"])
    assert len(page2["jobs"]) == 3
    assert [j["job_id"] for j in page2["jobs"]] == [4, 5, 6]
    assert page2["next_cursor"] is not None

    page3 = svc.get_jobs_since(since="", limit=3, cursor=page2["next_cursor"])
    assert len(page3["jobs"]) == 3
    assert [j["job_id"] for j in page3["jobs"]] == [7, 8, 9]
    assert page3["next_cursor"] is not None

    page4 = svc.get_jobs_since(since="", limit=3, cursor=page3["next_cursor"])
    assert len(page4["jobs"]) == 1
    assert page4["jobs"][0]["job_id"] == 10
    assert page4["next_cursor"] is None


def test_get_jobs_since_cursor_same_timestamp(tmp_path):
    """同一 updated_at 多条时,游标按 job_id 严格推进,不漏不重。"""
    db = tmp_path / "jobs.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE jobs (
            job_id INTEGER PRIMARY KEY,
            company TEXT, title TEXT, category TEXT, city TEXT,
            requirements TEXT, jd_text TEXT, apply_url TEXT,
            deadline TEXT, source TEXT,
            graduation_match INTEGER, is_mt INTEGER, updated_at TEXT
        )
        """
    )
    # 5 条同一时间戳,job_id 1..5
    conn.executemany(
        "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (i, f"c{i}", f"t{i}", "cat", "city", "req", "jd", "url", "dl", "src", 0, 0, "2026-01-01 00:00:00")
            for i in range(1, 6)
        ],
    )
    conn.commit()
    conn.close()

    svc = SyncService(db_path=db)
    p1 = svc.get_jobs_since(since="", limit=2)
    assert [j["job_id"] for j in p1["jobs"]] == [1, 2]
    p2 = svc.get_jobs_since(since="", limit=2, cursor=p1["next_cursor"])
    assert [j["job_id"] for j in p2["jobs"]] == [3, 4]
    p3 = svc.get_jobs_since(since="", limit=2, cursor=p2["next_cursor"])
    assert [j["job_id"] for j in p3["jobs"]] == [5]
    assert p3["next_cursor"] is None


def test_get_jobs_since_with_since_and_cursor(tmp_path):
    """since + cursor 组合:cursor 隐含 since,正常分页。"""
    db = _make_db(tmp_path)
    svc = SyncService(db_path=db)
    # since='2026-01-03 00:00:00' => 04..10 共 7 条
    p1 = svc.get_jobs_since(since="2026-01-03 00:00:00", limit=4)
    assert [j["job_id"] for j in p1["jobs"]] == [4, 5, 6, 7]
    p2 = svc.get_jobs_since(since="2026-01-03 00:00:00", limit=4, cursor=p1["next_cursor"])
    assert [j["job_id"] for j in p2["jobs"]] == [8, 9, 10]
    assert p2["next_cursor"] is None


def test_get_jobs_since_invalid_cursor_falls_back(tmp_path):
    """损坏的 cursor 应回退到无游标行为(按 since 查全量)。"""
    db = _make_db(tmp_path)
    svc = SyncService(db_path=db)
    res = svc.get_jobs_since(since="2026-01-05 00:00:00", limit=500, cursor="not-a-valid-cursor")
    assert len(res["jobs"]) == 5


def test_get_jobs_since_limit_clamped_to_max(tmp_path):
    """limit 超过 MAX_PAGE_SIZE 应被夹到上限;数据量不足时返回全部。"""
    db = _make_db(tmp_path)
    svc = SyncService(db_path=db)
    res = svc.get_jobs_since(since="", limit=10_000)
    assert len(res["jobs"]) == 10
    assert res["next_cursor"] is None


def test_get_jobs_since_limit_too_small_uses_default(tmp_path):
    """limit < 1 应回退到默认值。"""
    db = _make_db(tmp_path)
    svc = SyncService(db_path=db)
    res = svc.get_jobs_since(since="", limit=0)
    assert len(res["jobs"]) == 10


def test_job_fields_align_spec(tmp_path):
    """返回的 job dict 字段集合与 spec 完全一致。"""
    db = _make_db(tmp_path)
    svc = SyncService(db_path=db)
    res = svc.get_jobs_since(since="", limit=1)
    assert set(res["jobs"][0].keys()) == set(JOB_FIELDS)


def test_get_stats(tmp_path):
    """stats 返回总数与最新 updated_at。"""
    db = _make_db(tmp_path)
    svc = SyncService(db_path=db)
    stats = svc.get_stats()
    assert stats["total"] == 10
    assert stats["updated_at"] == "2026-01-10 00:00:00"


def test_constants():
    """页大小常量符合 spec。"""
    assert DEFAULT_PAGE_SIZE == 500
    assert MAX_PAGE_SIZE == 1000


# ---------------- HTTP 接口层测试(fastapi 可用时执行) ----------------


def _settings():
    from config import get_settings
    return get_settings()


def _override_auth():
    """测试用：override get_current_user 依赖，跳过认证。"""
    return {"id": "test-user", "user_id": "test-user", "email": "test@test.com", "is_verified": 1}


def test_api_sync_jobs_endpoint(tmp_path, monkeypatch):
    """GET /api/v1/sync/jobs 增量分页接口。"""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    db = _make_db(tmp_path)
    monkeypatch.setattr(_settings(), "JOBS_DB_PATH", db)

    from main import app
    from deps import get_current_user
    app.dependency_overrides[get_current_user] = _override_auth
    client = TestClient(app)

    resp = client.get(
        "/api/v1/sync/jobs",
        params={"since": "", "limit": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"jobs", "next_cursor"}
    assert len(body["jobs"]) == 5
    assert body["jobs"][0]["job_id"] == 1
    assert body["next_cursor"] is not None

    # 翻第二页
    resp2 = client.get(
        "/api/v1/sync/jobs",
        params={"since": "", "limit": 5, "cursor": body["next_cursor"]},
    )
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert len(body2["jobs"]) == 5
    assert body2["jobs"][0]["job_id"] == 6
    assert body2["next_cursor"] is None


def test_api_sync_stats_endpoint(tmp_path, monkeypatch):
    """GET /api/v1/sync/stats 接口。"""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    db = _make_db(tmp_path)
    monkeypatch.setattr(_settings(), "JOBS_DB_PATH", db)

    from main import app
    from deps import get_current_user
    app.dependency_overrides[get_current_user] = _override_auth
    client = TestClient(app)

    resp = client.get("/api/v1/sync/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 10
    assert body["updated_at"] == "2026-01-10 00:00:00"


def test_api_sync_jobs_limit_validation(tmp_path, monkeypatch):
    """limit 超过上限应被 422 拒绝(Query 约束)。"""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    db = _make_db(tmp_path)
    monkeypatch.setattr(_settings(), "JOBS_DB_PATH", db)

    from main import app
    from deps import get_current_user
    app.dependency_overrides[get_current_user] = _override_auth
    client = TestClient(app)

    resp = client.get(
        "/api/v1/sync/jobs",
        params={"since": "", "limit": MAX_PAGE_SIZE + 1},
    )
    assert resp.status_code == 422
