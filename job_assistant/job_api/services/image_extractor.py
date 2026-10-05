"""图片简历文本提取（OCR）。

支持 .jpg / .jpeg / .png / .webp / .bmp 图片格式。
使用 DeepSeek-VL 视觉模型识别文字，与公告图片识别链路一致，
避免引入 RapidOCR 等额外本地依赖和模型下载。
提取纯文本后交给 LLM 解析简历结构。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _get_llm_client():
    """获取 LLMClient 实例（按需导入，避免循环依赖）。"""
    import sys
    parent = str(Path(__file__).resolve().parents[2])
    if parent not in sys.path:
        sys.path.insert(0, parent)
    from llm_client import LLMClient

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    return LLMClient(api_key=api_key or None)


def extract_text_from_image(image_path: str | Path) -> str:
    """从图片中提取文本（DeepSeek-VL 视觉模型）。

    Args:
        image_path: 图片文件路径（.jpg / .jpeg / .png / .webp / .bmp）

    Returns:
        提取的纯文本。提取失败返回空字符串。
    """
    path = Path(image_path)
    ext = path.suffix.lower().lstrip(".")
    try:
        content = path.read_bytes()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"读取图片失败 {image_path}: {e!r}")
        return ""

    if not content:
        return ""

    client = _get_llm_client()
    if not getattr(client, "api_key", ""):
        logger.warning("DEEPSEEK_API_KEY 未配置，跳过图片 OCR")
        return ""

    try:
        text = client.ocr_image(content, ext=ext or "png")
        return text or ""
    except Exception as e:  # noqa: BLE001 OCR 失败不阻断流程
        logger.warning(f"图片 OCR 提取失败: {e!r}")
        return ""


def is_image_file(filename: str) -> bool:
    """判断文件是否为支持的图片格式。"""
    ext = Path(filename).suffix.lower()
    return ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp")
