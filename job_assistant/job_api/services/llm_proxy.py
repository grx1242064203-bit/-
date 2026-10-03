"""LLM 代理服务：复用父目录 LLMClient + resume_parser，对云端 API 暴露受限接口。

设计要点：
1. 不直接暴露 DeepSeek API Key — 由服务层注入，路由层无感知。
2. 复用父目录 (/workspace/job_assistant) 的 resume_parser.parse_resume_text
   与 supplement_profile，避免重复实现 Prompt 与归一化逻辑。
3. sys.path 处理：job_api 位于 job_assistant 子目录，import 父目录模块需把
   job_assistant 根目录加入 sys.path 头部。延迟到方法调用时执行，避免在
   模块导入期污染 sys.path 影响 job_api 自身的 config 解析。
4. 异常上抛：调用失败 / 超时 / 缺 API Key 时抛异常，由路由层映射为 503。
"""
import concurrent.futures
import logging
import sys
import threading
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# /workspace/job_assistant —— llm_proxy.py 的上三级目录
# (__file__ = .../job_api/services/llm_proxy.py, parents[2] = job_assistant/)
_PARENT_DIR = str(Path(__file__).resolve().parents[2])
_path_lock = threading.Lock()
_path_added = False


def _ensure_parent_path() -> None:
    """把 job_assistant 根目录加入 sys.path 头部（仅一次）。"""
    global _path_added
    with _path_lock:
        if _path_added:
            return
        if _PARENT_DIR not in sys.path:
            sys.path.insert(0, _PARENT_DIR)
        _path_added = True


class LLMProxyService:
    """DeepSeek LLM 代理 — 简历解析 + 补充分析。

    封装父目录 LLMClient，对外只暴露结构化结果，不泄漏 API Key。
    """

    def __init__(self, api_key: str = "", timeout: int = 30):
        self.api_key = api_key
        self.timeout = timeout

    def _make_client(self):
        """构造父目录 LLMClient 实例。缺 API Key 时抛 RuntimeError。"""
        _ensure_parent_path()
        from llm_client import LLMClient  # 延迟 import，避免模块导入期副作用

        client = LLMClient(api_key=self.api_key or None)
        if not getattr(client, "api_key", ""):
            raise RuntimeError("DEEPSEEK_API_KEY 未配置，LLM 服务不可用")
        return client

    def parse_resume(self, resume_text: str) -> Dict[str, Any]:
        """解析简历 → {"keywords": [...], "fit_directions": [...]}。

        复用 resume_parser.parse_resume_text。30s 超时；失败抛异常。
        """
        _ensure_parent_path()
        from resume_parser import parse_resume_text  # 延迟 import

        client = self._make_client()
        return self._run_with_timeout(
            parse_resume_text, resume_text, client,
            label="parse_resume",
        )

    def supplement(self, user_edited: dict, resume_text: str = "") -> Dict[str, Any]:
        """补充分析 → 复用 resume_parser.supplement_profile。30s 超时；失败抛异常。

        返回结构（透传 supplement_profile）：
        {fit_directions, structured_keywords, new_directions, new_skills}
        路由层负责挑选 {fit_directions, hard_skills} 字段返回客户端。
        """
        _ensure_parent_path()
        from resume_parser import supplement_profile  # 延迟 import

        client = self._make_client()
        return self._run_with_timeout(
            supplement_profile, user_edited, resume_text, client,
            label="supplement",
        )

    def _run_with_timeout(self, fn, *args, label: str = "llm_call"):
        """在线程池中执行 fn，超过 self.timeout 抛 TimeoutError。

        parse_resume_text 内部已捕获 LLM 异常并返回空结果，因此超时是
        调用层主动保护；其他显式异常（如 API Key 缺失）原样上抛。
        """
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(fn, *args)
            try:
                return future.result(timeout=self.timeout)
            except concurrent.futures.TimeoutError:
                logger.error(f"LLM {label} 超时 ({self.timeout}s)")
                raise TimeoutError(f"LLM {label} 超时 ({self.timeout}s)")
        finally:
            executor.shutdown(wait=False)
