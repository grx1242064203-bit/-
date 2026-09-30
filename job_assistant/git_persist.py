"""
Git 持久化模块 — 每轮处理后自动 commit + push 数据库和代码。
防止沙箱重置导致数据丢失。
"""
import subprocess
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

REPO_DIR = os.path.dirname(os.path.abspath(__file__))


def _ensure_git_config():
    """确保 git user 已配置(沙箱重置后会丢失)。"""
    for key, val in [("user.email", "agent@trae.ai"), ("user.name", "Trae Agent")]:
        r = subprocess.run(
            ["git", "config", key, val],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=10,
        )
    subprocess.run(["git", "config", "pull.rebase", "false"],
                   cwd=REPO_DIR, capture_output=True, timeout=10)


def git_commit_and_push(message: str = None) -> bool:
    """
    自动 add + commit + push。
    只提交 jobs.db 和代码文件,跳过缓存。
    返回是否成功。
    """
    try:
        _ensure_git_config()
        if message is None:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            message = f"auto: data snapshot @ {now}"

        # 1. add (尊重 .gitignore,缓存不会被提交)
        r = subprocess.run(
            ["git", "add", "-A"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            logger.warning(f"[git] add 失败: {r.stderr}")
            return False

        # 2. 检查是否有变更
        r = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            logger.info("[git] 无变更,跳过 commit")
            return True

        # 3. commit
        r = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            logger.warning(f"[git] commit 失败: {r.stderr}")
            return False
        logger.info(f"[git] commit 成功: {message}")

        # 4. push (仅当配置了 remote 时)
        r = subprocess.run(
            ["git", "remote"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=10,
        )
        if not r.stdout.strip():
            logger.info("[git] 无 remote,跳过 push(本地 commit 已完成)")
            return True

        # 检测当前分支名(兼容 master/main)
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=10,
        )
        branch = r.stdout.strip() or "main"

        r = subprocess.run(
            ["git", "push", "origin", branch],
            cwd=REPO_DIR, capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            logger.warning(f"[git] push 失败: {r.stderr}")
            return False
        logger.info("[git] push 成功,数据已持久化到远端")
        return True

    except subprocess.TimeoutExpired:
        logger.warning("[git] 操作超时")
        return False
    except Exception as e:
        logger.warning(f"[git] 异常: {e}")
        return False
