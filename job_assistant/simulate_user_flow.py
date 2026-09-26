#!/usr/bin/env python3
"""
端到端用户流程模拟测试 — 完整模拟用户从安装到每日任务的全流程。

Mock 策略:
- FeishuClient: 替换为 MockFeishuClient,记录所有调用并返回模拟数据
- WxPusherClient: 替换为 MockWxPusherClient,记录推送内容
- JobCollector: 替换为 MockJobCollector,返回模拟岗位数据

测试范围:
1. 用户 Onboarding(创建多维表格/字段/转所有权)
2. 每日任务(采集→评分→去重→入库→日报→推送)
3. 去重(重复岗位不重复写入)
4. 回调验签(verification_token 校验)
5. 失败告警(有失败时推送给管理员)
6. 并发安全(UserStore lost-update / HashStore 文件锁)

使用方式:
    cd /workspace/job_assistant
    python simulate_user_flow.py
"""
import os
import sys
import json
import time
import shutil
import logging
import threading
from unittest.mock import patch, MagicMock
from datetime import datetime

# 使用独立的测试数据目录,不污染生产数据
TEST_DATA_DIR = "/tmp/ja_e2e_test_data"
os.environ["DATA_DIR"] = TEST_DATA_DIR

# 清理旧测试数据
if os.path.exists(TEST_DATA_DIR):
    shutil.rmtree(TEST_DATA_DIR)
os.makedirs(TEST_DATA_DIR, exist_ok=True)

from config import settings
from models import UserStore, User, UserProfile, HashStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ============================================================
# 模拟数据
# ============================================================
MOCK_JOBS = [
    {
        "title": "字节跳动 产品经理 校招",
        "company": "字节跳动",
        "department": "产品部",
        "location": "北京",
        "salary": "25-35K",
        "jd_text": (
            "岗位职责:负责产品规划与需求分析。要求:本科及以上学历,计算机相关专业,"
            "熟悉Python和SQL,具备良好的数据分析能力。应届毕业生优先。"
        ),
        "jd_summary": "字节跳动产品经理校招,要求Python SQL",
        "jd_url": "https://jobs.bytedance.com/product/001",
        "posted": "2026-09-20",
        "crawl_date": "2026-09-26 09:00:00",
    },
    {
        "title": "腾讯 后端开发工程师 实习",
        "company": "腾讯",
        "department": "技术部",
        "location": "北京",
        "salary": "300-500/天",
        "jd_text": (
            "负责后端服务开发。要求:计算机相关专业,熟悉Python/Go,"
            "了解数据库SQL。在校生可投。"
        ),
        "jd_summary": "腾讯后端开发实习,Python Go SQL",
        "jd_url": "https://careers.tencent.com/backend/002",
        "posted": "2026-09-22",
        "crawl_date": "2026-09-26 09:00:01",
    },
    {
        "title": "某公司 销售经理",
        "company": "某某销售公司",
        "department": "销售部",
        "location": "上海",
        "salary": "15-25K",
        "jd_text": "负责销售业务拓展,要求有销售经验。",
        "jd_summary": "销售经理",
        "jd_url": "https://example.com/sales/003",
        "posted": "2026-09-18",
        "crawl_date": "2026-09-26 09:00:02",
    },
]

# 测试用户画像
TEST_PROFILE = {
    "school": "X大",
    "degree": "本科",
    "major": "计算机",
    "experience_years": 0,
    "core_skills": ["Python", "SQL"],
    "direction_keywords": {"产品经理": ["pm", "产品"]},
    "target_companies": ["字节"],
    "target_industries": [],
    "target_cities": ["北京"],
    "target_certificates": [],
}


# ============================================================
# Mock 客户端
# ============================================================
class MockFeishuClient:
    """模拟飞书 API 客户端,记录所有调用"""

    call_log = []  # 类级别记录所有调用

    def __init__(self, *args, **kwargs):
        self.created_bitable = None
        self.tables_created = []
        self.fields_created = []
        self.records_written = []
        self.docs_created = []
        self.shared = []
        self.transferred = []

    def create_bitable(self, name):
        MockFeishuClient.call_log.append(("create_bitable", name))
        self.created_bitable = f"mock_base_{int(time.time())}"
        return self.created_bitable

    def resolve_app_token(self, token):
        return token  # 测试用非 wiki token

    def verify_bitable_access(self, token):
        MockFeishuClient.call_log.append(("verify_bitable_access", token))
        return True

    def create_table(self, app_token, name):
        MockFeishuClient.call_log.append(("create_table", name))
        tid = f"tbl_{name}"
        self.tables_created.append(tid)
        return tid

    def create_field(self, app_token, table_id, field_name, field_type, **kwargs):
        MockFeishuClient.call_log.append(("create_field", field_name))
        self.fields_created.append(field_name)
        return f"fld_{field_name}"

    def batch_create_records(self, app_token, table_id, records):
        MockFeishuClient.call_log.append(("batch_create_records", len(records), table_id))
        for r in records:
            self.records_written.append({"table_id": table_id, "fields": r})
        return [f"rec_{i}" for i in range(len(records))]

    def search_records(self, app_token, table_id, filter_expr, fields=None):
        # 第一次调用(去重 hash 查询)返回空
        MockFeishuClient.call_log.append(("search_records", filter_expr))
        return []

    def get_record(self, app_token, table_id, record_id):
        return {}

    def delete_record(self, app_token, table_id, record_id):
        MockFeishuClient.call_log.append(("delete_record", record_id))

    def normalize_fields(self, fields):
        return fields

    def create_doc(self, title):
        MockFeishuClient.call_log.append(("create_doc", title))
        doc_id = f"doc_{int(time.time())}"
        url = f"https://www.feishu.cn/docx/{doc_id}"
        self.docs_created.append({"doc_id": doc_id, "title": title, "url": url})
        return doc_id, url

    def append_doc_blocks(self, document_id, blocks):
        MockFeishuClient.call_log.append(("append_doc_blocks", len(blocks)))

    def share_with_user(self, token, doc_type, open_id, perm="full_access"):
        MockFeishuClient.call_log.append(("share_with_user", open_id))
        self.shared.append(open_id)

    def transfer_owner(self, token, doc_type, open_id):
        MockFeishuClient.call_log.append(("transfer_owner", open_id))
        self.transferred.append(open_id)


class MockWxPusherClient:
    """模拟 WxPusher,记录推送内容"""

    push_log = []

    def __init__(self, *args, **kwargs):
        pass

    def send(self, uid, content, content_type=3, url=None):
        MockWxPusherClient.push_log.append({"uid": uid, "content": content, "url": url})
        logger.info(f"[MOCK WxPusher] 推送给 {uid}: {content[:60]}...")
        return True

    def send_daily_summary(self, uid, date_str, jobs, doc_url, closed_count=0, major=""):
        content = f"## 日报 {date_str} | 新增{len(jobs)}条"
        return self.send(uid, content, url=doc_url)


class MockJobCollector:
    """模拟岗位采集器,返回 MOCK_JOBS"""

    def __init__(self, *args, **kwargs):
        self.call_count = 0

    def collect(self, profile, target_companies, target_cities, limit=20):
        self.call_count += 1
        logger.info(f"[MOCK Collector] 采集到 {len(MOCK_JOBS)} 个岗位 (limit={limit})")
        return MOCK_JOBS[:limit]


# ============================================================
# 测试工具
# ============================================================
class TestResult:
    def __init__(self):
        self.results = []  # (name, passed, detail)

    def record(self, name, passed, detail=""):
        status = "PASS" if passed else "FAIL"
        self.results.append((name, passed, detail))
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

    def summary(self):
        passed = sum(1 for _, p, _ in self.results if p)
        total = len(self.results)
        print(f"\n{'='*60}")
        print(f"测试汇总: {passed}/{total} 通过")
        print(f"{'='*60}")
        for name, p, detail in self.results:
            print(f"  [{'PASS' if p else 'FAIL'}] {name}")
        return passed == total


# ============================================================
# 测试用例
# ============================================================
def test_onboarding(result: TestResult):
    """测试 1: 用户 Onboarding 流程"""
    print("\n📋 测试 1: 用户 Onboarding 流程")
    MockFeishuClient.call_log = []

    with patch("onboarding.FeishuClient", MockFeishuClient):
        from onboarding import onboard_user
        user = onboard_user(
            user_id="test_onboard_001",
            tenant_key="test_tenant",
            open_id="test_open_001",
            profile=TEST_PROFILE,
            plan="autumn",
            expire_date="2026-12-31",
        )

    # 验证用户已保存
    store = UserStore()
    saved = store.get("test_onboard_001")
    result.record("用户已保存到 users.json", saved is not None)
    result.record("base_token 已设置", bool(saved.feishu_base_token))
    result.record("table_id 已设置", bool(saved.feishu_table_id))
    result.record("closed_table_id 已设置", bool(saved.feishu_closed_table_id))
    result.record("open_id 正确", saved.feishu_open_id == "test_open_001")

    # 验证飞书调用
    calls = [c[0] for c in MockFeishuClient.call_log]
    result.record("调用了 create_bitable", "create_bitable" in calls)
    result.record("调用了 verify_bitable_access", "verify_bitable_access" in calls)
    result.record("调用了 create_table(2次)", calls.count("create_table") == 2)
    result.record("调用了 transfer_owner", "transfer_owner" in calls)
    # transfer_owner 成功时不调用 share_with_user;失败降级时才调用
    result.record("所有权转移或分享已执行",
                  "transfer_owner" in calls or "share_with_user" in calls)

    return saved


def test_daily_run(result: TestResult, user: User):
    """测试 2: 每日任务完整流程"""
    print("\n📋 测试 2: 每日任务完整流程(采集→评分→入库→日报→推送)")
    MockFeishuClient.call_log = []
    MockFeishuClient.records_written = []
    MockWxPusherClient.push_log = []

    # 设置用户的 wxpusher_uid,触发推送流程
    user.wxpusher_uid = "test_wx_uid_001"
    store = UserStore()
    store.upsert(user)

    with patch("daily_runner.FeishuClient", MockFeishuClient), \
         patch("daily_runner.WxPusherClient", MockWxPusherClient), \
         patch("daily_runner.JobCollector", MockJobCollector):
        from daily_runner import DailyRunner
        runner = DailyRunner(user)
        result_data = runner.run()

    print(f"  执行结果: {json.dumps(result_data, ensure_ascii=False, default=str)[:300]}")

    result.record("无错误", len(result_data.get("errors", [])) == 0,
                  f"errors={result_data.get('errors')}")
    result.record("新增岗位数=3", result_data["new_jobs"] == 3,
                  f"actual={result_data['new_jobs']}")
    result.record("生成了日报文档", bool(result_data["doc_url"]))
    result.record("推送成功", result_data["push_ok"] is True)

    # 验证飞书写入
    writes = [r for r in MockFeishuClient.call_log if r[0] == "batch_create_records"]
    total_written = sum(r[1] for r in writes)
    result.record("写入飞书记录数=3", total_written == 3, f"actual={total_written}")

    # 验证日报标题不含"金融"
    doc_titles = [c[1] for c in MockFeishuClient.call_log if c[0] == "create_doc"]
    has_finance = any("金融" in t for t in doc_titles)
    result.record("日报标题不含'金融'(Fix-4 验证)", not has_finance,
                  f"titles={doc_titles}")

    # 验证推送内容
    pushes = MockWxPusherClient.push_log
    result.record("微信推送被调用", len(pushes) >= 1)

    return result_data


def test_deduplication(result: TestResult, user: User):
    """测试 3: 去重 — 第二次运行不重复写入"""
    print("\n📋 测试 3: 去重验证(第二次运行不应重复写入)")
    MockFeishuClient.call_log = []
    MockWxPusherClient.push_log = []

    with patch("daily_runner.FeishuClient", MockFeishuClient), \
         patch("daily_runner.WxPusherClient", MockWxPusherClient), \
         patch("daily_runner.JobCollector", MockJobCollector):
        from daily_runner import DailyRunner
        runner = DailyRunner(user)
        result_data = runner.run()

    print(f"  第二次执行结果: new_jobs={result_data['new_jobs']}")
    result.record("第二次运行新增=0(去重生效)", result_data["new_jobs"] == 0,
                  f"actual={result_data['new_jobs']}")

    writes = [r for r in MockFeishuClient.call_log if r[0] == "batch_create_records"]
    total_written = sum(r[1] for r in writes)
    result.record("飞书无重复写入", total_written == 0, f"actual={total_written}")


def test_callback_verification(result: TestResult):
    """测试 4: 回调验签(Fix-3 验证)"""
    print("\n📋 测试 4: 回调 verification_token 验签")
    from callback_server import _verify_feishu_token

    # 未配置 token 时跳过校验
    original = settings.FEISHU_VERIFICATION_TOKEN
    settings.FEISHU_VERIFICATION_TOKEN = ""
    ok = _verify_feishu_token({"token": "anything"})
    result.record("未配置 token 时放行", ok is True)

    # 配置 token 后校验
    settings.FEISHU_VERIFICATION_TOKEN = "secret_123"
    ok_match = _verify_feishu_token({"token": "secret_123"})
    result.record("token 匹配时通过", ok_match is True)

    ok_mismatch = _verify_feishu_token({"token": "wrong_token"})
    result.record("token 不匹配时拒绝", ok_mismatch is False)

    # v2 结构: header.token
    ok_v2 = _verify_feishu_token({"header": {"token": "secret_123"}})
    result.record("v2 结构 header.token 校验通过", ok_v2 is True)

    settings.FEISHU_VERIFICATION_TOKEN = original


def test_failure_alert(result: TestResult):
    """测试 5: 失败告警(Fix-5 验证)"""
    print("\n📋 测试 5: 每日任务失败告警")
    MockWxPusherClient.push_log = []
    settings.ADMIN_WXPUSHER_UID = "admin_uid_001"

    # 模拟一个失败的结果
    from main import _alert_admin
    summary = {"total_users": 2, "success": 1, "failed": 1,
               "total_new_jobs": 0, "total_closed": 0}
    results = [
        {"user_id": "user_ok", "errors": []},
        {"user_id": "user_fail", "errors": ["飞书 API 超时"]},
    ]

    with patch("main.WxPusherClient", MockWxPusherClient):
        _alert_admin(summary, results)

    pushes = MockWxPusherClient.push_log
    result.record("失败时触发告警推送", len(pushes) == 1)
    if pushes:
        content = pushes[0]["content"]
        result.record("告警内容包含失败用户", "user_fail" in content)
        result.record("告警推送给管理员", pushes[0]["uid"] == "admin_uid_001")

    # 无失败时不推送
    MockWxPusherClient.push_log = []
    summary_ok = {"total_users": 1, "success": 1, "failed": 0,
                  "total_new_jobs": 5, "total_closed": 0}
    with patch("main.WxPusherClient", MockWxPusherClient):
        _alert_admin(summary_ok, [{"user_id": "u1", "errors": []}])
    result.record("无失败时不推送告警", len(MockWxPusherClient.push_log) == 0)

    settings.ADMIN_WXPUSHER_UID = ""


def test_concurrency_safety(result: TestResult):
    """测试 6: 并发安全(Fix-1 & Fix-2 验证)"""
    print("\n📋 测试 6: 并发安全验证")

    # --- UserStore lost-update ---
    store = UserStore()
    u_a = User(id="conc_userA", profile=UserProfile(major="A"))
    u_b = User(id="conc_userB", profile=UserProfile(major="B"))
    store.upsert(u_a)
    store.upsert(u_b)

    s1 = UserStore()
    s2 = UserStore()
    a = s1.get("conc_userA")
    a.profile.school = "学校A"
    s1.upsert(a)
    b = s2.get("conc_userB")
    b.profile.school = "学校B"
    s2.upsert(b)

    final = UserStore()
    result.record("UserStore 双用户修改不丢失",
                  final.get("conc_userA").profile.school == "学校A"
                  and final.get("conc_userB").profile.school == "学校B")

    # --- HashStore 并发写 ---
    errors = []
    def write_hash(i):
        try:
            HashStore("conc_test").add(f"h{i}")
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=write_hash, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()

    hs = HashStore("conc_test")
    result.record("HashStore 10 线程并发写无损坏",
                  len(hs._hashes) == 10 and len(errors) == 0,
                  f"count={len(hs._hashes)}, errors={len(errors)}")


def test_scoring_quality(result: TestResult, user: User):
    """测试 7: 评分质量 — 验证评分可解释且区分度合理"""
    print("\n📋 测试 7: 评分质量验证")
    from scorer import score_job

    scored = [score_job(j, user.profile) for j in MOCK_JOBS]
    titles = {s["岗位标题"]: s for s in scored}

    # 产品经理岗位应评分最高
    pm_score = titles["字节跳动 产品经理 校招"]["相关性评分"]
    sales_score = titles["某公司 销售经理"]["相关性评分"]
    result.record("匹配岗位评分 > 不匹配岗位", pm_score > sales_score,
                  f"PM={pm_score} Sales={sales_score}")

    # 产品经理应为"优先申请"或"可申请"
    pm_recommend = titles["字节跳动 产品经理 校招"]["综合推荐度"]
    result.record("匹配岗位推荐度为优先申请/可申请",
                  pm_recommend in ["优先申请", "可申请"],
                  f"recommend={pm_recommend}")

    # 验证去重 hash 包含 jd_url
    pm_hash = titles["字节跳动 产品经理 校招"]["去重hash"]
    result.record("去重 hash 非空", bool(pm_hash))


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 60)
    print("招聘情报助手 — 端到端用户流程模拟测试")
    print(f"测试数据目录: {TEST_DATA_DIR}")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    result = TestResult()

    try:
        # 测试 1: Onboarding
        user = test_onboarding(result)

        # 测试 2: 每日任务
        test_daily_run(result, user)

        # 测试 3: 去重
        test_deduplication(result, user)

        # 测试 4: 回调验签
        test_callback_verification(result)

        # 测试 5: 失败告警
        test_failure_alert(result)

        # 测试 6: 并发安全
        test_concurrency_safety(result)

        # 测试 7: 评分质量
        test_scoring_quality(result, user)

    except Exception as e:
        logger.exception("测试执行异常")
        result.record("测试流程未崩溃", False, str(e))

    # 清理
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)

    all_pass = result.summary()
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
