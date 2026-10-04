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

from fastapi import APIRouter, Depends, HTTPException, status
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
_proxy = LLMProxyService(api_key=_settings.DEEPSEEK_API_KEY)


class ParseResumeRequest(BaseModel):
    resume_text: str = Field(..., min_length=1, description="简历原文")


class ParseResumeResponse(BaseModel):
    keywords: list = []
    fit_directions: list = []


class SupplementRequest(BaseModel):
    user_edited: dict = Field(..., description="用户编辑后的画像")
    resume_text: str = ""


class SupplementResponse(BaseModel):
    fit_directions: list = []
    hard_skills: list = []


def _check_quota(user_id: str):
    """检查配额，超额抛 429。"""
    quota = get_user_quota(user_id)
    if quota["remaining"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"已达每日 LLM 调用配额上限（{quota['limit']} 次/天），"
                f"明日 0 点重置"
            ),
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
    user_id = user["user_id"]
    _check_quota(user_id)

    try:
        result = _proxy.parse_resume(req.resume_text)
    except TimeoutError as e:
        _handle_llm_error(e, "parse_resume")
        return  # 不会被走到（_handle_llm_error 抛出）
    except Exception as e:
        _handle_llm_error(e, "parse_resume")
        return

    # 调用成功后增加用量计数；即使并发竞争导致 False 也返回结果，避免吞掉已成功的调用
    increment_usage(user_id)
    return {
        "keywords": result.get("keywords", []),
        "fit_directions": result.get("fit_directions", []),
    }


@router.post("/supplement", response_model=SupplementResponse)
def supplement(
    req: SupplementRequest,
    user: dict = Depends(get_current_user),
):
    """补充分析 → 基于用户编辑后的画像推荐适配方向 + 硬技能。"""
    user_id = user["user_id"]
    _check_quota(user_id)

    try:
        result = _proxy.supplement(req.user_edited, req.resume_text)
    except TimeoutError as e:
        _handle_llm_error(e, "supplement")
        return
    except Exception as e:
        _handle_llm_error(e, "supplement")
        return

    increment_usage(user_id)
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
    个性化面试回答。结果按 (user_id, company_name) 缓存。
    """
    user_id = user["user_id"]
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

    increment_usage(user_id)

    # 4) 写入缓存（按 user_id + company_name）
    saved = dd_model.upsert_due_diligence_sync(
        user_id=user_id,
        company_name=company_name,
        intro=result.get("intro", ""),
        official_website=result.get("official_website", ""),
        news_links=result.get("news_links", []),
        why_company_questions=result.get("why_company_questions", []),
    )
    return {**saved, "cached": False}


# ===== PDF 简历解析（multipart 上传）=====

from fastapi import UploadFile, File


@router.post("/parse-resume-file", response_model=ParseResumeResponse)
async def parse_resume_file(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """上传 PDF / .txt / .md 简历文件 → 提取文本 → LLM 解析。

    优先用文本方式（.txt/.md 直接读），PDF 走 PyMuPDF 提取文本层。
    扫描件 PDF（无文本层）会返回 keywords=[], fit_directions=[]，前端应提示。
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)
    user_id = user["user_id"]
    _check_quota(user_id)

    try:
        file_bytes = await file.read()
        filename = (file.filename or "resume").lower()

        # 根据扩展名选择提取方式
        if filename.endswith(".pdf"):
            from services.pdf_extractor import extract_pdf_text
            text = extract_pdf_text(file_bytes)
            if not text:
                # PDF 扫描件或加密
                _log.warning(f"PDF 无法提取文本: {filename}")
                return {
                    "keywords": [],
                    "fit_directions": [],
                    "warning": "无法从 PDF 提取文本（可能是扫描件或加密文件）。"
                               "请尝试可复制文本的 PDF，或转为 .txt/.md 后上传。",
                }
        elif filename.endswith((".txt", ".md", ".markdown")):
            text = file_bytes.decode("utf-8", errors="ignore").strip()
        else:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {filename}。支持 .pdf / .txt / .md",
            )

        if len(text) < 50:
            raise HTTPException(
                status_code=400,
                detail="简历文本太短（< 50 字符），请确认文件内容完整。",
            )

        result = _proxy.parse_resume(text)
    except HTTPException:
        raise
    except TimeoutError as e:
        _handle_llm_error(e, "parse_resume_file")
        return
    except Exception as e:
        _handle_llm_error(e, "parse_resume_file")
        return

    increment_usage(user_id)
    return {
        "keywords": result.get("keywords", []),
        "fit_directions": result.get("fit_directions", []),
    }
