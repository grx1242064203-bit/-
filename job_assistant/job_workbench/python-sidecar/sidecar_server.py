"""
Offer搭子桌面工作台 — Python sidecar 评分引擎。

协议: stdin/stdout JSON-RPC(每行一个 JSON)。
- 请求:  {"id": 1, "method": "score_one", "params": {...}}
- 响应:  {"id": 1, "result": {...}}
         {"id": 1, "error": "..."}

Tauri Rust 端通过子进程方式启动本进程,逐行读写 JSON。
日志走 stderr,不污染 stdout。

依赖父目录(/workspace/job_assistant 根目录)的:
  scorer / resume_parser / keyword_normalizer / job_tree / competitiveness / job_db
本进程通过 sys.path.insert 把父目录加入搜索路径,从而 import 它们。
"""

import io
import json
import os
import sys
import traceback
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# 把 /workspace/job_assistant 根目录加入 sys.path,以便 import 现有评分模块。
#   python-sidecar/  → 上两层 = job_workbench/ → 再上一层 = job_assistant/
# 用绝对路径,避免依赖 CWD(Tauri 启动子进程时 CWD 可能是任意目录)。
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_JOB_ASSISTANT_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _JOB_ASSISTANT_ROOT not in sys.path:
    sys.path.insert(0, _JOB_ASSISTANT_ROOT)

# 现在父目录在 sys.path 里,可以 import 评分模块。
# 注意: 这些模块在 import 阶段会读 config.settings.DATA_DIR 下的
#       kw_dict.json / job_category_tree.json,DATA_DIR 默认指向 /opt/job_assistant/data。
#       评分本身不需要 LLM(llm_client 仅在 score_job 的可选参数中用到,我们传 None)。
import scorer  # noqa: E402  (sys.path 已调整)


# ---------------------------------------------------------------------------
# profile 构造:从 params.profile(dict)构造一个 SimpleNamespace 模拟 UserProfile。
# scorer.score_job 只通过 getattr 访问 profile 的属性,SimpleNamespace 完全够用。
# ---------------------------------------------------------------------------
def _build_profile(profile_dict):
    """把 dict 形式的 profile 转成 SimpleNamespace,递归处理嵌套结构。

    scorer 需要的属性(参见 scorer._extract_user_keywords / competitiveness):
      structured_keywords, fit_directions, core_skills, direction_keywords,
      target_cities, target_companies, degree, major, target_certificates
    structured_keywords 里的元素可以是 dict(scorer._tag_get 已兼容 dict)。
    """
    if profile_dict is None:
        return SimpleNamespace()
    if isinstance(profile_dict, SimpleNamespace):
        return profile_dict

    if not isinstance(profile_dict, dict):
        # 已经是对象就直接用
        return profile_dict

    # 关键: structured_keywords 必须保留为 list[dict],不能把里面的 dict 转成 SimpleNamespace,
    # 否则 scorer._tag_get(tag, key) 走 isinstance(tag, dict) 分支会失败。
    # direction_keywords 是 Dict[str, List[str]],scorer 用 profile.direction_keywords.items(),
    # 也保留为 dict,不能包成 SimpleNamespace(会丢 .items())。
    # 其余标量/列表字段原样透传给 SimpleNamespace,scorer 用 getattr 访问。
    return SimpleNamespace(**dict(profile_dict))


# ---------------------------------------------------------------------------
# 各 RPC 方法的实现
# ---------------------------------------------------------------------------
def _method_ping(params):
    return {"pong": True}


def _method_score_one(params):
    job = params.get("job")
    profile_dict = params.get("profile")
    if job is None:
        raise ValueError("score_one 缺少 job 参数")
    if profile_dict is None:
        raise ValueError("score_one 缺少 profile 参数")

    profile = _build_profile(profile_dict)
    result = scorer.score_job(job, profile, llm_client=None)
    return result


def _method_score_batch(params):
    jobs = params.get("jobs")
    profile_dict = params.get("profile")
    if jobs is None:
        raise ValueError("score_batch 缺少 jobs 参数")
    if profile_dict is None:
        raise ValueError("score_batch 缺少 profile 参数")
    if not isinstance(jobs, list):
        raise ValueError("score_batch 的 jobs 必须是列表")

    profile = _build_profile(profile_dict)
    out = []
    for job in jobs:
        job_id = None
        try:
            if isinstance(job, dict):
                job_id = job.get("id") or job.get("job_id")
            result = scorer.score_job(job, profile, llm_client=None)
            out.append({
                "job_id": job_id,
                "score": result.get("相关性评分"),
                "recommend": result.get("综合推荐度"),
                "reasons": result.get("匹配理由", []),
            })
        except Exception as e:
            sys.stderr.write(
                f"[sidecar] score_batch 单条失败 job_id={job_id}: {e}\n"
            )
            out.append({
                "job_id": job_id,
                "score": None,
                "recommend": None,
                "reasons": [],
                "error": str(e),
            })
    return out


def _method_quit(params):
    # 通过返回特殊标记,主循环检测后退出进程
    return {"__quit__": True}


_METHODS = {
    "ping": _method_ping,
    "score_one": _method_score_one,
    "score_batch": _method_score_batch,
    "quit": _method_quit,
}


# ---------------------------------------------------------------------------
# 主循环:逐行读取 stdin,每行一个 JSON 请求,处理后写一行 JSON 响应到 stdout。
# 异常不崩,返回 error 字段。日志走 stderr。
# ---------------------------------------------------------------------------
def _emit(obj):
    """写一行 JSON 到 stdout,立即 flush(子进程管道需要 flush 才能让父端读到)。"""
    line = json.dumps(obj, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def serve(in_stream=None, out_stream=None):
    """运行 JSON-RPC 主循环。

    in_stream / out_stream 主要用于测试时注入 StringIO。
    生产路径走默认的 sys.stdin / sys.stdout。
    """
    instream = in_stream if in_stream is not None else sys.stdin
    # out_stream 仅用于测试;生产必须用 sys.stdout,且 _emit 已用 sys.stdout。
    if out_stream is not None:
        global _emit  # noqa: PLW0603
        def _emit_test(obj):
            out_stream.write(json.dumps(obj, ensure_ascii=False) + "\n")
            out_stream.flush() if hasattr(out_stream, "flush") else None
        _emit = _emit_test  # noqa: PLW0604

    sys.stderr.write("[sidecar] 评分引擎已启动,等待 JSON-RPC 请求...\n")
    sys.stderr.flush()

    for raw_line in instream:
        if not raw_line:
            continue
        line = raw_line.strip() if isinstance(raw_line, str) else raw_line
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"[sidecar] JSON 解析失败: {e} line={line!r}\n")
            sys.stderr.flush()
            _emit({"id": None, "error": f"JSON 解析失败: {e}"})
            continue

        req_id = req.get("id") if isinstance(req, dict) else None
        method = req.get("method") if isinstance(req, dict) else None
        params = req.get("params", {}) if isinstance(req, dict) else {}

        if not isinstance(req, dict) or not method:
            _emit({"id": req_id, "error": "请求格式非法: 缺少 method"})
            continue

        handler = _METHODS.get(method)
        if handler is None:
            _emit({"id": req_id, "error": f"未知方法: {method}"})
            continue

        try:
            result = handler(params)
            if isinstance(result, dict) and result.get("__quit__"):
                _emit({"id": req_id, "result": {"quit": True}})
                sys.stderr.write("[sidecar] 收到 quit,退出进程。\n")
                sys.stderr.flush()
                return
            _emit({"id": req_id, "result": result})
        except Exception as e:
            tb = traceback.format_exc()
            sys.stderr.write(f"[sidecar] 方法 {method} 异常: {e}\n{tb}\n")
            sys.stderr.flush()
            _emit({"id": req_id, "error": str(e)})

    sys.stderr.write("[sidecar] stdin EOF,退出进程。\n")
    sys.stderr.flush()


def main():
    # 确保 stdout 用 UTF-8(Windows 等环境下默认编码可能不是 UTF-8)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if hasattr(sys.stdin, "reconfigure"):
        try:
            sys.stdin.reconfigure(encoding="utf-8")
        except Exception:
            pass
    serve()


if __name__ == "__main__":
    main()
