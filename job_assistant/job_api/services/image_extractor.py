"""图片简历文本提取（OCR）。

支持 .jpg / .jpeg / .png 图片格式，使用 rapidocr-onnxruntime 做中文 OCR。
提取纯文本后交给 LLM 解析简历结构。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 单例 OCR 引擎（首次调用时加载，避免重复初始化）
_ocr_engine = None
_ocr_lock_imported = False


def _get_ocr_engine():
    """懒加载 OCR 引擎（rapidocr-onnxruntime）。"""
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine
    try:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
        return _ocr_engine
    except ImportError:
        raise RuntimeError(
            "未安装 rapidocr-onnxruntime，无法解析图片简历。"
            "请运行: pip install rapidocr-onnxruntime"
        )


def extract_text_from_image(image_path: str | Path) -> str:
    """从图片中提取文本（OCR）。

    Args:
        image_path: 图片文件路径（.jpg / .jpeg / .png）

    Returns:
        提取的纯文本。提取失败返回空字符串。
    """
    engine = _get_ocr_engine()
    try:
        result, _ = engine(str(image_path))
        if not result:
            return ""
        # result: [[box, text, confidence], ...]
        # 按行合并文本（保持阅读顺序）
        lines = []
        for item in result:
            if len(item) >= 2 and item[1]:
                lines.append(item[1])
        return "\n".join(lines)
    except Exception as e:  # noqa: BLE001 OCR 失败不阻断流程
        logger.warning(f"图片 OCR 提取失败: {e!r}")
        return ""


def is_image_file(filename: str) -> bool:
    """判断文件是否为支持的图片格式。"""
    ext = Path(filename).suffix.lower()
    return ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp")
