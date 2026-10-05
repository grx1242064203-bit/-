"""简历文件文本提取服务。

支持格式：
- .txt / .md / .markdown：直接读取（UTF-8 / GBK 自动探测）
- .pdf：PyMuPDF 提取文本层（非 OCR，仅提取可选中文字）
- .jpg / .jpeg / .png / .webp / .bmp：LLMClient.ocr_image() 用视觉模型识别文字

设计要点：
- 图片不走本地 OCR（RapidOCR 等），直接调 DeepSeek-VL 视觉模型，
  与公告图片识别链路一致，避免引入额外依赖和模型下载。
- PDF 优先提取文本层；若文本层为空（扫描件），返回空字符串并提示。
- 所有异常向上抛出，由路由层统一处理并返回具体错误信息。
"""
import logging
import os
from typing import Tuple

from fastapi import UploadFile

logger = logging.getLogger(__name__)

# 支持的文件扩展名
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
PDF_EXT = {".pdf"}
TEXT_EXT = {".txt", ".md", ".markdown", ".text"}


def _read_text_file(content: bytes) -> str:
    """读取文本文件，自动探测 UTF-8 / GBK 编码。"""
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _extract_pdf(content: bytes) -> str:
    """用 PyMuPDF 提取 PDF 文本层（非 OCR）。"""
    import fitz  # pymupdf

    doc = fitz.open(stream=content, filetype="pdf")
    try:
        texts = []
        for page in doc:
            text = page.get_text()
            if text:
                texts.append(text)
        return "\n".join(texts)
    finally:
        doc.close()


def _extract_image(content: bytes, ext: str) -> str:
    """用 DeepSeek-VL 视觉模型识别图片文字（复用 LLMClient.ocr_image）。"""
    import sys
    from pathlib import Path

    # 把项目根目录加入 sys.path 以 import llm_client
    parent = str(Path(__file__).resolve().parents[2])
    if parent not in sys.path:
        sys.path.insert(0, parent)

    from llm_client import LLMClient

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    client = LLMClient(api_key=api_key or None)
    if not getattr(client, "api_key", ""):
        raise ValueError("DEEPSEEK_API_KEY 未配置，无法识别图片简历")

    ext_clean = ext.lstrip(".")
    text = client.ocr_image(content, ext=ext_clean)
    return text or ""


def get_file_ext(filename: str) -> str:
    """获取小写文件扩展名（含点）。"""
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


async def extract_resume_text(file: UploadFile) -> Tuple[str, str]:
    """从上传的简历文件提取纯文本。

    Returns:
        (text, file_type) — file_type 为 'text' / 'pdf' / 'image'

    Raises:
        ValueError: 不支持的文件类型或提取失败（含具体原因）
    """
    ext = get_file_ext(file.filename or "")
    content = await file.read()

    if not content:
        raise ValueError("文件内容为空")

    if ext in TEXT_EXT:
        text = _read_text_file(content)
        if not text.strip():
            raise ValueError("文件内容为空，请确认简历非空")
        return text, "text"

    if ext in PDF_EXT:
        try:
            text = _extract_pdf(content)
        except Exception as e:
            raise ValueError(f"PDF 解析失败: {e}") from e
        if not text.strip():
            raise ValueError("PDF 未提取到文本（可能是扫描件，请转图片后上传）")
        return text, "pdf"

    if ext in IMAGE_EXT:
        try:
            text = _extract_image(content, ext)
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"图片识别失败: {e}") from e
        if not text.strip():
            raise ValueError("图片中未识别到文字，请确保图片清晰且包含文字内容")
        return text, "image"

    raise ValueError(
        f"不支持的文件类型 '{ext or '未知'}'，"
        f"支持 .txt / .md / .pdf / .jpg / .png 等格式"
    )
