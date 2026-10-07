"""LLM 代理路由：简历解析 + 补充分析。

接口签名（spec）：
- POST /api/v1/llm/parse-resume  {resume_text} → {keywords, fit_directions}
- POST /api/v1/llm/supplement   {user_edited, resume_text} → {fit_directions, hard_skills}

所有端点：
- 需要 Bearer Token 认证（依赖注入 get_current_user，T3 占位）。
- 调用前检查每日配额，超额返回 429。
- 调用成功后增加用量计数。
- DeepSeek 异常 / 超时 / 缺 API Key → 503。

不直接暴露 DeepSeek API Key，由 LLMProxyService 在服务层注入。
"""
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from config import get_settings
from deps import get_current_user
from models import company_due_diligence as dd_model
from services.llm_proxy import LLMProxyService
from services.quota_service import (
    get_user_quota,
    increment_usage,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm"])

# 单例代理服务（API Key 在调用时从 settings 注入；不暴露给路由层以外的模块）
_settings = get_settings()
# 优先用 settings(.env); 兜底用环境变量(部分部署只设环境变量不写 .env)
_api_key = _settings.DEEPSEEK_API_KEY or os.getenv("DEEPSEEK_API_KEY", "")
_proxy = LLMProxyService(api_key=_api_key)


class ParseResumeRequest(BaseModel):
    resume_text: str = Field(..., min_length=1, description="简历原文")


class ParseResumeResponse(BaseModel):
    keywords: list = []
    fit_directions: list = []


class ParseResumeFileResponse(BaseModel):
    keywords: list = []
    fit_directions: list = []
    raw_text: str = ""
    file_type: str = ""


class SupplementRequest(BaseModel):
    user_edited: dict = Field(..., description="用户编辑后的画像")
    resume_text: str = ""


class SupplementResponse(BaseModel):
    fit_directions: list = []
    hard_skills: list = []


def _check_quota(user_id: str):
    """检查配额，超额抛 429。

    limit < 0 视为不限制,直接放行;
    limit == 0 视为禁用,永远 429;
    limit > 0 正常比较 remaining。
    """
    quota = get_user_quota(user_id)
    # 不限制(limit < 0):直接放行
    if quota["limit"] < 0:
        return quota
    # 禁用(limit == 0)或已用尽(remaining == 0):抛 429
    if quota["remaining"] <= 0:
        if quota["limit"] == 0:
            detail = "LLM 调用已被禁用,请联系管理员"
        else:
            detail = (
                f"已达每日 LLM 调用配额上限（{quota['limit']} 次/天），"
                f"明日 0 点重置"
            )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": "86400"},
        )
    return quota


def _handle_llm_error(e: Exception, label: str):
    """统一 LLM 异常映射：超时 / 缺 Key / 其他 → 503。"""
    logger.error(f"LLM {label} 失败: {e}", exc_info=True)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"LLM 服务暂时不可用，请稍后重试",
    )


@router.post("/parse-resume", response_model=ParseResumeResponse)
def parse_resume(
    req: ParseResumeRequest,
    user: dict = Depends(get_current_user),
):
    """解析简历文本 → 结构化关键词 + 适配岗位方向。"""
    user_id = str(user["user_id"])
    _check_quota(user_id)

    try:
        result = _proxy.parse_resume(req.resume_text)
    except TimeoutError as e:
        _handle_llm_error(e, "parse_resume")
        return  # 不会被走到（_handle_llm_error 抛出）
    except Exception as e:
        _handle_llm_error(e, "parse_resume")
        return

    # 调用成功后增加用量计数；即使并发竞争导致 False 也返回结果，避免吞掉已成功的调用。
    # 包入 try/except:DB 写入失败不阻塞已成功的 LLM 结果返回。
    try:
        increment_usage(user_id)
    except Exception as e:
        logger.warning(f"increment_usage 写入失败(parse_resume, user_id={user_id}): {e!r}")
    return {
        "keywords": result.get("keywords", []),
        "fit_directions": result.get("fit_directions", []),
    }


@router.post("/parse-resume-file", response_model=ParseResumeFileResponse)
async def parse_resume_file(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """上传简历文件 → 提取文本 → LLM 解析 → 返回画像 + 原文。

    支持格式：.pdf / .txt / .md / .jpg / .jpeg / .png / .webp / .bmp
    - PDF: PyMuPDF 提取文本层
    - 纯文本(.txt/.md): 直接读取
    - 图片: DeepSeek-VL 视觉模型识别文字

    返回: keywords / fit_directions / raw_text / file_type
    """
    user_id = user["user_id"]
    _check_quota(user_id)

    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    supported = {".pdf", ".txt", ".md", ".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    if ext not in supported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式: {ext}。支持: {', '.join(sorted(supported))}",
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件为空",
        )

    # 根据格式提取文本
    resume_text = ""
    file_type = ""
    if ext == ".pdf":
        file_type = "pdf"
        from services.pdf_extractor import extract_pdf_text
        resume_text = extract_pdf_text(raw_bytes)
        if not resume_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDF 未提取到文本（可能是扫描件或加密）。请转成 .txt 或上传图片。",
            )
    elif ext in (".txt", ".md"):
        file_type = "text"
        try:
            resume_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            resume_text = raw_bytes.decode("gbk", errors="ignore")
    else:
        # 图片 → DeepSeek-VL OCR
        file_type = "image"
        from services.image_extractor import extract_text_from_image
        # 写入临时文件供 OCR 引擎读取
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name
        try:
            resume_text = extract_text_from_image(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        if not resume_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="图片 OCR 未识别到文本，请上传清晰的简历截图。",
            )

    # 提取成功 → 走 LLM 解析
    try:
        result = _proxy.parse_resume(resume_text)
    except TimeoutError as e:
        _handle_llm_error(e, "parse_resume")
        return
    except Exception as e:
        _handle_llm_error(e, "parse_resume")
        return

    # 包入 try/except:DB 写入失败不阻塞已成功的 LLM 结果返回。
    try:
        increment_usage(user_id)
    except Exception as e:
        logger.warning(f"increment_usage 写入失败(parse_resume_file, user_id={user_id}): {e!r}")
    return {
        "keywords": result.get("keywords", []),
        "fit_directions": result.get("fit_directions", []),
        "raw_text": resume_text,
        "file_type": file_type,
    }


@router.post("/supplement", response_model=SupplementResponse)
def supplement(
    req: SupplementRequest,
    user: dict = Depends(get_current_user),
):
    """补充分析 → 基于用户编辑后的画像推荐适配方向 + 硬技能。"""
    user_id = str(user["user_id"])
    _check_quota(user_id)

    try:
        result = _proxy.supplement(req.user_edited, req.resume_text)
    except TimeoutError as e:
        _handle_llm_error(e, "supplement")
        return
    except Exception as e:
        _handle_llm_error(e, "supplement")
        return

    # 包入 try/except:DB 写入失败不阻塞已成功的 LLM 结果返回。
    try:
        increment_usage(user_id)
    except Exception as e:
        logger.warning(f"increment_usage 写入失败(supplement, user_id={user_id}): {e!r}")
    # supplement_profile 返回 {fit_directions, structured_keywords, new_directions, new_skills}
    # API 仅暴露 {fit_directions, hard_skills}（hard_skills = LLM 新补的硬技能 tag）
    return {
        "fit_directions": result.get("fit_directions", []),
        "hard_skills": result.get("new_skills", []),
    }


# ===== 公司尽调：联网搜索 + LLM 生成 =====

class CompanyDueDiligenceRequest(BaseModel):
    company_name: str = Field(..., min_length=1, description="公司名称")


class CompanyDueDiligenceResponse(BaseModel):
    company_name: str
    intro: str = ""
    official_website: str = ""
    news_links: list = []
    why_company_questions: list = []
    generated_at: str = ""
    cached: bool = False


@router.post("/company-due-diligence", response_model=CompanyDueDiligenceResponse)
def company_due_diligence(
    req: CompanyDueDiligenceRequest,
    user: dict = Depends(get_current_user),
):
    """公司尽调卡：生成公司简介/官网/新闻/个性化面试问答。

    自动读取用户的 active 简历画像，把简历文本喂给 LLM，生成结合用户经历的
    专业面试回答。结果按 (user_id, company_name) 缓存。
    """
    user_id = str(user["user_id"])  # 统一 str 类型,与 resume_profiles 对齐
    company_name = req.company_name.strip()

    # 1) 命中缓存直接返回
    cached = dd_model.get_due_diligence_sync(user_id, company_name)
    if cached:
        return {**cached, "cached": True}

    # 2) 读取用户简历（用于个性化面试回答）
    resume_text = ""
    try:
        from models.resume_profile import get_active_profile
        profile = get_active_profile(user_id)
        if profile:
            resume_text = profile.get("resume_text", "")
    except Exception as e:  # noqa: BLE001 简历读取失败不阻塞尽调生成
        logger.warning(f"读取用户简历失败 (user_id={user_id}): {e!r}")

    # 3) 未命中：检查配额 + 生成
    _check_quota(user_id)
    try:
        result = _proxy.company_due_diligence(company_name, resume_text=resume_text)
    except TimeoutError as e:
        _handle_llm_error(e, "company_due_diligence")
        return
    except Exception as e:
        _handle_llm_error(e, "company_due_diligence")
        return

    # 4) 写入用量计数 + 缓存。
    # 包入 try/except:LLM 已成功,这两步 DB 写入失败不能阻塞返回结果(避免 500)。
    try:
        increment_usage(user_id)
    except Exception as e:
        logger.warning(f"increment_usage 写入失败(company_due_diligence, user_id={user_id}): {e!r}")

    saved: dict = {**result, "company_name": company_name}
    try:
        saved = dd_model.upsert_due_diligence_sync(
            user_id=user_id,
            company_name=company_name,
            intro=result.get("intro", ""),
            official_website=result.get("official_website", ""),
            news_links=result.get("news_links", []),
            why_company_questions=result.get("why_company_questions", []),
        )
    except Exception as e:
        # 缓存写入失败:只记日志,返回 LLM 生成结果(不写 cached 标记)
        logger.warning(
            f"upsert_due_diligence_sync 写入失败(user_id={user_id}, "
            f"company={company_name}): {e!r}",
            exc_info=True,
        )
        return {**result, "company_name": company_name, "cached": False}
    return {**saved, "cached": False}
