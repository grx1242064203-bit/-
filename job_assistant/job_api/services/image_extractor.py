"""简历文件文本提取服务。

支持格式：
- .txt / .md / .markdown：直接读取（UTF-8 / GBK 自动探测）
- .pdf：PyMuPDF 提取文本层
- .jpg / .jpeg / .png / .webp / .bmp：RapidOCR 中文 OCR

设计要点：
- RapidOCR 引擎懒加载（首次调用才初始化，避免启动慢）
- OCR 结果按行合并，保留段落结构
- 所有异常向上抛出，由路由层统一处理并返回具体错误信息
"""
import io
import logging
from typing import Tuple

from fastapi import UploadFile

logger = logging.getLogger(__name__)

# 支持的文件扩展名
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
PDF_EXT = {".pdf"}
TEXT_EXT = {".txt", ".md", ".markdown", ".text"}

# RapidOCR 引擎单例（懒加载）
_ocr_engine = None


def _get_ocr_engine():
    """懒加载 RapidOCR 引擎，首次调用初始化。"""
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
        logger.info("RapidOCR 引擎初始化完成")
    return _ocr_engine


def _read_text_file(content: bytes) -> str:
    """读取文本文件，自动探测 UTF-8 / GBK 编码。"""
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    # 兜底：忽略错误字符
    return content.decode("utf-8", errors="ignore")


def _extract_pdf(content: bytes) -> str:
    """用 PyMuPDF 提取 PDF 文本层。"""
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


def _extract_image(content: bytes) -> str:
    """用 RapidOCR 识别图片中的文字，按行合并。"""
    engine = _get_ocr_engine()
    result, _ = engine(content)
    if not result:
        return ""
    # result 格式: [[box, text, score], ...]
    # 按 y 坐标排序后逐行合并
    lines = []
    for item in result:
        if len(item) >= 2:
            lines.append(item[1])
    return "\n".join(lines)


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
        ValueError: 不支持的文件类型或提取失败
    """
    ext = get_file_ext(file.filename or "")
    content = await file.read()

    if not content:
        raise ValueError("文件内容为空")

    if ext in TEXT_EXT:
        text = _read_text_file(content)
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
            text = _extract_image(content)
        except Exception as e:
            raise ValueError(f"图片 OCR 识别失败: {e}") from e
        if not text.strip():
            raise ValueError("图片中未识别到文字，请确保图片清晰且包含文字内容")
        return text, "image"

    raise ValueError(
        f"不支持的文件类型 '{ext or '未知'}'，"
        f"支持 .txt / .md / .pdf / .jpg / .png 等格式"
    )
