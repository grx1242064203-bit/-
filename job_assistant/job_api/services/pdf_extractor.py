"""PDF 简历文本提取器 — 用 PyMuPDF 提取纯文本，复用现有 LLM 解析链路。

第一性原则：PDF 提取 = 纯文本 → 后续解析逻辑与 .txt 完全一致。
对抗性审查：
- PDF 为空/扫描件（无文本层）→ 返回空串，前端提示"请上传可复制文本的 PDF 或用 .txt"
- 加密 PDF → 返回空串并提示
- 大文件（>10MB）→ 限流
"""

from __future__ import annotations

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_PDF_BYTES = 10 * 1024 * 1024  # 10MB 上限


def extract_pdf_text(file_bytes: bytes) -> str:
    """从 PDF 二进制提取纯文本。

    Args:
        file_bytes: PDF 文件原始字节

    Returns:
        提取到的纯文本。空 PDF / 扫描件 / 加密 → 返回空串 ""。
    """
    if not file_bytes or len(file_bytes) > _MAX_PDF_BYTES:
        if len(file_bytes) > _MAX_PDF_BYTES:
            logger.warning(f"PDF 超过 {_MAX_PDF_BYTES} 字节上限: {len(file_bytes)}")
        return ""

    try:
        import pymupdf  # PyMuPDF，pip install pymupdf

        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        if doc.is_encrypted:
            logger.warning("PDF 加密无法提取文本")
            doc.close()
            return ""

        texts: list[str] = []
        for page in doc:
            # get_text("text") 纯文本模式，忽略格式，便于后续 LLM 解析
            page_text = page.get_text("text").strip()
            if page_text:
                texts.append(page_text)

        doc.close()
        result = "\n".join(texts).strip()
        logger.info(f"PDF 提取完成: {len(result)} chars, {len(texts)} pages")
        return result

    except ImportError:
        logger.error("pymupdf 未安装，请 pip install pymupdf")
        return ""
    except Exception as e:
        logger.error(f"PDF 提取失败: {e}")
        return ""
