"""
T11 sidecar 评分引擎单元测试。

覆盖:
- ping/pong 协议往返
- score_one 返回 0-100 分(不依赖真实 LLM,llm_client 传 None)
- score_batch 批量评分,每条都返回 {job_id, score, recommend, reasons}
- 异常路径: 缺参数 / 未知方法 / 坏 JSON

运行:
    cd job_assistant/job_workbench/python-sidecar
    DATA_DIR=../../data python3 -m pytest tests/test_sidecar.py -q
    # 或直接:
    DATA_DIR=../../data python3 tests/test_sidecar.py
"""

import io
import json
import os
import sys
import unittest

# 把 sidecar 目录加入 sys.path,以便 import sidecar_server
_HERE = os.path.dirname(os.path.abspath(__file__))
_SIDECAR_DIR = os.path.abspath(os.path.join(_HERE, ".."))
if _SIDECAR_DIR not in sys.path:
    sys.path.insert(0, _SIDECAR_DIR)

# 把 job_assistant 根目录加入 sys.path,以便 sidecar_server 内部 import scorer 等
_JOB_ROOT = os.path.abspath(os.path.join(_SIDECAR_DIR, "..", ".."))
if _JOB_ROOT not in sys.path:
    sys.path.insert(0, _JOB_ROOT)

# 确保 DATA_DIR 指向真实数据目录(kw_dict.json / job_category_tree.json 必须可读)
if not os.environ.get("DATA_DIR"):
    os.environ["DATA_DIR"] = os.path.join(_JOB_ROOT, "data")

import sidecar_server  # noqa: E402  (sys.path 已调整)


# ---------------------------------------------------------------------------
# Mock 数据
# ---------------------------------------------------------------------------
def _mock_profile_dict():
    """返回一个 dict 形式的 mock profile(模拟客户端 JSON 传入)。"""
    return {
        "structured_keywords": [
            {"kw": "Python", "standard": "Python", "category": "hard_skill",
             "weight": 3.0, "source": "resume_llm", "resume_section": "skill"},
            {"kw": "Go", "standard": "Go", "category": "hard_skill",
             "weight": 2.0, "source": "resume_llm", "resume_section": "skill"},
            {"kw": "后端开发", "standard": "后端开发", "category": "role",
             "weight": 2.0, "source": "resume_llm", "resume_section": "other"},
            {"kw": "北京邮电大学", "standard": "北京邮电大学", "category": "education",
             "weight": 2.0, "source": "resume_llm", "resume_section": "education"},
            {"kw": "本科", "standard": "本科", "category": "education",
             "weight": 1.0, "source": "resume_llm", "resume_section": "education"},
        ],
        "fit_directions": [
            {"direction": "后端开发", "cat_key": "dev", "sub_key": "backend",
             "category_name": "开发", "weight": 1.0, "evidence": "简历项目方向"},
        ],
        "core_skills": ["Python", "Go"],
        "direction_keywords": {"role": ["后端开发"]},
        "target_cities": ["北京"],
        "target_companies": ["字节跳动"],
        "degree": "本科",
        "major": "计算机科学与技术",
        "target_certificates": [],
        "school": "北京邮电大学",
    }


def _mock_job(job_id="j1"):
    """返回一个 mock job dict,岗位方向=后端开发(命中候选人 fit_directions)。"""
    return {
        "id": job_id,
        "company": "字节跳动",
        "position_title": "后端开发工程师",
        "job_subcategory": "后端开发",
        "job_category": "开发",
        "city": "北京",
        "min_education": "本科",
        "company_tier": "顶",
        "keywords": '["Python", "Go", "Kubernetes"]',
        "hard_skills": '["Python", "Go"]',
    }


def _run_rpc_over_lines(lines):
    """把多行 JSON-RPC 请求喂给 sidecar serve(),返回解析后的响应列表。"""
    in_stream = io.StringIO("\n".join(lines) + "\n")
    out_stream = io.StringIO()
    sidecar_server.serve(in_stream=in_stream, out_stream=out_stream)
    out_stream.seek(0)
    responses = []
    for line in out_stream.getvalue().splitlines():
        line = line.strip()
        if line:
            responses.append(json.loads(line))
    return responses


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------
class TestPingPong(unittest.TestCase):
    """ping/pong 协议往返。"""

    def test_ping_returns_pong(self):
        resp = _run_rpc_over_lines([
            json.dumps({"id": 1, "method": "ping", "params": {}}),
        ])
        self.assertEqual(len(resp), 1)
        self.assertEqual(resp[0], {"id": 1, "result": {"pong": True}})

    def test_quit_returns_quit_and_exits(self):
        # quit 之后进程应退出;再发一条不应被处理
        resp = _run_rpc_over_lines([
            json.dumps({"id": 1, "method": "quit", "params": {}}),
            json.dumps({"id": 2, "method": "ping", "params": {}}),
        ])
        # quit 触发后 serve() 立即 return,第二条 ping 不会被处理
        self.assertEqual(len(resp), 1)
        self.assertEqual(resp[0], {"id": 1, "result": {"quit": True}})


class TestScoreOne(unittest.TestCase):
    """score_one 单条评分。"""

    def test_score_returns_0_to_100(self):
        resp = _run_rpc_over_lines([
            json.dumps({"id": 1, "method": "score_one",
                        "params": {"job": _mock_job(),
                                   "profile": _mock_profile_dict()}}),
        ])
        self.assertEqual(len(resp), 1)
        self.assertEqual(resp[0]["id"], 1)
        self.assertNotIn("error", resp[0])
        result = resp[0]["result"]
        # 必备字段
        self.assertIn("相关性评分", result)
        self.assertIn("综合推荐度", result)
        self.assertIn("维度分", result)
        score = result["相关性评分"]
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        # 推荐度取值校验
        self.assertIn(result["综合推荐度"],
                      {"强烈推荐", "推荐", "可申请", "不建议"})

    def test_score_one_direct_call(self):
        """直接调 _method_score_one,不走 stdin/stdout(便于排错)。"""
        result = sidecar_server._method_score_one(
            {"job": _mock_job(), "profile": _mock_profile_dict()}
        )
        self.assertGreaterEqual(result["相关性评分"], 0)
        self.assertLessEqual(result["相关性评分"], 100)

    def test_score_one_missing_job_raises(self):
        with self.assertRaises(ValueError):
            sidecar_server._method_score_one({"profile": _mock_profile_dict()})


class TestScoreBatch(unittest.TestCase):
    """score_batch 批量评分。"""

    def test_batch_returns_one_entry_per_job(self):
        jobs = [_mock_job("j1"), _mock_job("j2"), _mock_job("j3")]
        resp = _run_rpc_over_lines([
            json.dumps({"id": 1, "method": "score_batch",
                        "params": {"jobs": jobs,
                                   "profile": _mock_profile_dict()}}),
        ])
        self.assertEqual(len(resp), 1)
        self.assertNotIn("error", resp[0])
        result = resp[0]["result"]
        self.assertEqual(len(result), 3)
        # 每条都要有 job_id / score / recommend / reasons
        for i, entry in enumerate(result):
            self.assertEqual(entry["job_id"], f"j{i+1}")
            self.assertIsNotNone(entry["score"])
            self.assertGreaterEqual(entry["score"], 0)
            self.assertLessEqual(entry["score"], 100)
            self.assertIn(entry["recommend"],
                          {"强烈推荐", "推荐", "可申请", "不建议"})
            self.assertIsInstance(entry["reasons"], list)

    def test_batch_direct_call(self):
        jobs = [_mock_job("j1"), _mock_job("j2")]
        result = sidecar_server._method_score_batch(
            {"jobs": jobs, "profile": _mock_profile_dict()}
        )
        self.assertEqual(len(result), 2)
        for entry in result:
            self.assertGreaterEqual(entry["score"], 0)
            self.assertLessEqual(entry["score"], 100)


class TestErrorHandling(unittest.TestCase):
    """异常路径:不崩,返回 error 字段。"""

    def test_unknown_method_returns_error(self):
        resp = _run_rpc_over_lines([
            json.dumps({"id": 1, "method": "no_such_method", "params": {}}),
        ])
        self.assertEqual(resp[0]["id"], 1)
        self.assertIn("error", resp[0])
        self.assertIn("未知方法", resp[0]["error"])

    def test_bad_json_returns_error(self):
        resp = _run_rpc_over_lines([
            "this is not json",
        ])
        self.assertEqual(len(resp), 1)
        self.assertIn("error", resp[0])

    def test_score_one_missing_profile_returns_error(self):
        # 缺 profile → score_one 抛 ValueError → 主循环包成 error
        resp = _run_rpc_over_lines([
            json.dumps({"id": 1, "method": "score_one",
                        "params": {"job": _mock_job()}}),
        ])
        self.assertEqual(len(resp), 1)
        self.assertEqual(resp[0]["id"], 1)
        self.assertIn("error", resp[0])

    def test_request_without_method_returns_error(self):
        resp = _run_rpc_over_lines([
            json.dumps({"id": 1, "params": {}}),
        ])
        self.assertEqual(resp[0]["id"], 1)
        self.assertIn("error", resp[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
