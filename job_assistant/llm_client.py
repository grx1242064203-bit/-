"""
LLM 客户端 — 基于 DeepSeek 的简历解析与岗位信息增强。

设计原则(第一性原理):
1. 简历解析的核心是"结构化提取" — 把非结构化文本转为可评分的字段
2. Prompt 角色扮演资深 HR,提取维度对标真实招聘筛选标准
3. 输出严格 JSON,便于直接映射到 UserProfile
4. 失败降级:LLM 不可用时返回空结构,不阻塞主流程

DeepSeek API 兼容 OpenAI 格式,api_key 从环境变量 DEEPSEEK_API_KEY 读取。
"""
import json
import logging
import os
import re
import io
from typing import Dict, List, Optional, Any

import requests

logger = logging.getLogger(__name__)

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_VL_MODEL = "deepseek-v4-flash-vision-exp"  # 视觉模型,用于图片公告 OCR

# VL 多策略重试:当默认策略失败时,逐步放宽像素/高度限制 + 缩小切片高度
# 策略设计(从保守到激进):
#   1. 默认:切片 2500px,压缩 4M 像素/4000px 高 — 成本低,适合常规图
#   2. 放宽:切片 1500px,压缩 8M 像素/6000px 高 — 长图切更碎,保留更多细节
#   3. 激进:切片 1000px,压缩 12M 像素/8000px 高 — 超长图充分切片,质量最高
VL_STRATEGIES = [
    {"slice_height": 2500, "slice_max_width": 800,
     "compress_max_width": 1280, "max_pixels": 4_000_000, "max_height": 4000, "quality": 80},
    {"slice_height": 1500, "slice_max_width": 1000,
     "compress_max_width": 1500, "max_pixels": 8_000_000, "max_height": 6000, "quality": 85},
    {"slice_height": 1000, "slice_max_width": 1200,
     "compress_max_width": 1800, "max_pixels": 12_000_000, "max_height": 8000, "quality": 90},
]


# ========== 简历解析 Prompt ==========
# 角色扮演 + 明确输出格式 + 提取维度对标 HR 真实筛选标准
RESUME_PARSE_PROMPT = """你是一位有 10 年经验的资深 HR 专家,擅长从简历中精准提取候选人画像。
请从以下简历文本中提取结构化信息,严格输出 JSON,不要输出任何 JSON 以外的文字。

提取维度与要求:
1. school: 毕业院校(全称,如"清华大学")。多个取最高学历的院校。
2. degree: 学历(本科/硕士/博士/大专/高中)。
3. major: 专业全称(如"计算机科学与技术")。
4. graduation_year: 毕业年份(4位数字,如 2026)。在读则填预计毕业年份。
5. graduation_date: 毕业年月(格式 YYYY-MM,如 "2026-06")。在读则填预计毕业年月。校招投递需严格匹配届数,此字段非常重要。
6. experience_years: 工作年限(数字,应届/在校填 0,实习经历不算正式工作年限)。校招用户此值应为 0。
7. core_skills: 核心技能列表(硬技能优先,如 Python/SQL/Excel/数据分析/项目管理等,提取 5-15 个)。
8. target_roles: 目标岗位方向列表(从简历求职意向/经历推断,如 ["产品经理","数据分析"])。每个方向需精炼为 2-6 字的岗位名称。
9. direction_keywords: 每个目标方向对应的搜索关键词数组。这是最关键的字段!
   格式: [{{"direction": "方向名", "keywords": ["关键词1","关键词2",...]}}]
   要求: 每个方向生成 5-8 个搜索关键词,必须包含:
     - 方向名本身(如 "FOF投资经理")
     - 同义/近义岗位名(如 "基金投资经理"、"资产配置研究员")
     - 细分领域术语(如 "基金筛选"、"组合管理"、"母基金")
     - 英文常用缩写(如 "FOF"、"portfolio")
     - 相关技能/工具词(如 "资产配置"、"量化")
   这些关键词将直接用于搜索引擎抓取岗位,必须精准、专业、覆盖全面。
10. target_cities: 目标城市列表(从简历期望地点推断,不确定则为空数组)。
11. target_industries: 目标行业列表(从经历推断,必须从以下标准分类中选择,可多选):["互联网/科技","金融","咨询/专业服务","消费/零售/快消","制造/工业","房地产/建筑","医疗/医药/健康","教育/培训","传媒/文娱/游戏","交通/物流","能源/公用事业","政府/事业单位"]。不确定则为空数组。
12. preferred_company_types: 偏好的公司类型(从简历背景和目标推断,必须从以下选择:["国央企","民企","外企","事业单位/政府","其他"],可多选)。如金融背景且求稳可推荐"国央企",技术背景可推荐"民企"。
13. preferred_difficulties: 偏好的申请难度(根据学校层次和经历推荐,可选值:["最激烈","较为激烈","中等难度","较低难度"],可多选)。顶尖院校+强实习推荐"最激烈"+"较为激烈"。
14. certificates: 已获证书列表(如 CFA/CPA/法考/PMP/四六级等)。
15. current_role: 当前身份("学生"/"在职"/"待业")。
16. summary: 候选人专业画像(100-150字),需包含:学校学历层次、核心技术栈/能力、相关实习或项目亮点、目标岗位方向。用专业但平实的语言,不要套话。
17. highlights: 简历亮点列表(3-5 条,每条不超过 30 字,突出硬核成果,如 "某券商行研实习,覆盖3个行业"、"CFA二级通过"、"GitHub 开源项目 500+ star")。

注意:
- 缺失的信息填""(字符串)或 [](数组),不要编造
- experience_years 必须是数字
- direction_keywords 的 keywords 必须是搜索友好的关键词,不要用完整句子
- 只输出 JSON 对象,不要 markdown 代码块标记
- graduation_date 必须是 YYYY-MM 格式

简历文本:
\"\"\"{resume_text}\"\"\"
"""


class LLMClient:
    """DeepSeek LLM 客户端 — 简历解析 + 信息增强"""

    def __init__(self, api_key: str = None, model: str = None):
        # 从 settings 读取(支持 .env 文件),兼容直接传参
        if not api_key:
            try:
                from config import settings
                api_key = settings.DEEPSEEK_API_KEY
            except ImportError:
                pass
        # 兜底: 环境变量(部分部署只设环境变量不写 .env,或 config 加载到空值)
        if not api_key:
            api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.api_key = api_key or ""
        self.model = model or DEEPSEEK_MODEL
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY 未配置,LLM 功能不可用")

    def _chat(self, messages: List[Dict], temperature: float = 0.1,
              max_tokens: int = 2000, json_mode: bool = True) -> Optional[str]:
        """调用 DeepSeek Chat API,返回 assistant 文本内容。失败返回 None。"""
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY 未配置,跳过 LLM 调用")
            return None
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            resp = requests.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return content
        except Exception as e:
            logger.error(f"DeepSeek API 调用失败: {e}")
            return None

    def chat_with_images(self, text: str, image_urls: List[str],
                         temperature: float = 0.1, max_tokens: int = 2000) -> Optional[str]:
        """调用 deepseek-v4-flash-vision-exp 进行图片识别(多模态),返回文本。失败返回 None。

        用于公告正文文字过短时,从图片中提取岗位信息。
        image_urls 支持:本地文件路径、http URL、base64 data URL。

        多策略重试:当默认策略(切片2500px+4M像素)失败时,自动尝试放宽像素/高度限制
        并缩小切片高度(1500px→1000px),最大程度提高识别成功率。
        超过 4 张图片时分批处理,结果拼接。
        """
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY 未配置,跳过 VL 调用")
            return None
        if not image_urls:
            return None

        # 记录每个策略的最后错误,供调用方排查
        self.last_vl_error = ""
        last_error = ""

        for strategy_idx, strategy in enumerate(VL_STRATEGIES):
            # 分批处理(每批最多 4 张),拼接所有批次的识别结果
            all_texts = []
            batch_size = 4
            batch_failed = False
            for batch_start in range(0, len(image_urls), batch_size):
                batch = image_urls[batch_start:batch_start + batch_size]
                batch_text, batch_err = self._chat_with_image_batch(
                    text, batch, temperature, max_tokens, strategy)
                if batch_text:
                    all_texts.append(batch_text)
                else:
                    # 该批次失败,记录错误并尝试下一策略
                    batch_failed = True
                    last_error = batch_err or f"策略{strategy_idx + 1}批次返回空"
                    break

            if not batch_failed and all_texts:
                if strategy_idx > 0:
                    logger.info(f"VL 策略 {strategy_idx + 1} 成功(策略1失败)")
                return "\n".join(all_texts)

            # 当前策略整体失败,尝试下一策略
            self.last_vl_error = last_error
            logger.warning(
                f"VL 策略 {strategy_idx + 1} 失败: {last_error[:120]}; "
                f"尝试下一策略..." if strategy_idx < len(VL_STRATEGIES) - 1
                else f"VL 所有策略均失败: {last_error[:120]}"
            )

        return None

    @property
    def last_vl_error_msg(self) -> str:
        """获取最近一次 VL 调用的错误信息(供调用方记录 vl_error)。"""
        return getattr(self, "last_vl_error", "")

    def _chat_with_image_batch(self, text: str, image_urls: List[str],
                               temperature: float, max_tokens: int,
                               strategy: Dict = None) -> tuple:
        """处理一批(最多4张)图片的VL识别。

        Args:
            strategy: 切片/压缩策略 dict,含 slice_height, slice_max_width,
                      compress_max_width, max_pixels, max_height, quality。
                      None 时使用 VL_STRATEGIES[0]。

        Returns:
            (text, error) — 成功时 text 非空且 error 为空;失败时 text=None,error 为错误描述。
        """
        if strategy is None:
            strategy = VL_STRATEGIES[0]
        try:
            import base64
            content_parts = [{"type": "text", "text": text}]
            for img_ref in image_urls[:4]:  # 最多 4 张/批
                raw_bytes = None

                # 1. base64 data URL
                if img_ref.startswith("data:"):
                    try:
                        b64_str = img_ref.split(",", 1)[-1]
                        raw_bytes = base64.b64decode(b64_str)
                    except Exception:
                        continue

                # 2. 本地文件路径
                elif os.path.isfile(img_ref):
                    try:
                        with open(img_ref, "rb") as f:
                            raw_bytes = f.read()
                    except Exception as e:
                        logger.warning(f"读取本地图片失败 {img_ref}: {e}")
                        continue

                # 3. http URL:下载
                elif img_ref.startswith("http"):
                    try:
                        img_resp = requests.get(
                            img_ref, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0",
                                     "Referer": "https://mp.weixin.qq.com/"}
                        )
                        if img_resp.status_code == 200 and img_resp.content:
                            raw_bytes = img_resp.content
                    except Exception as e:
                        logger.warning(f"图片下载失败: {e}")
                        continue

                if not raw_bytes:
                    continue

                # 超长图切片(微信长图上万像素高,API会拒绝),按策略切片
                image_chunks = self.slice_long_image(
                    raw_bytes,
                    max_height=strategy["slice_height"],
                    max_width=strategy["slice_max_width"],
                )
                for chunk_bytes in image_chunks:
                    b64_data = self._compress_image_to_base64(
                        chunk_bytes,
                        max_width=strategy["compress_max_width"],
                        max_pixels=strategy["max_pixels"],
                        max_height=strategy["max_height"],
                        quality=strategy["quality"],
                    )
                    if b64_data:
                        content_parts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}
                        })

            if len(content_parts) == 1:  # 只有文字没有图片
                return None, "无有效图片"
            resp = requests.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": DEEPSEEK_VL_MODEL,  # VL 视觉模型
                    "messages": [{"role": "user", "content": content_parts}],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"], ""
        except Exception as e:
            err_msg = str(e)
            logger.error(f"DeepSeek VL 调用失败: {err_msg}")
            return None, err_msg

    @staticmethod
    def _compress_image_to_base64(raw_bytes: bytes, max_width: int = 1280,
                                   max_pixels: int = 4_000_000,
                                   max_height: int = 4000,
                                   quality: int = 80) -> Optional[str]:
        """压缩图片并返回 base64 字符串。失败返回 None。

        使用 PIL 将图片转为 JPEG,限制总像素数(max_pixels)和高度(max_height)。
        若图片超高(如微信长图),会先按宽度等比缩小,再按高度切成多段。
        返回的是单段压缩后的 base64;超长图由调用方切片后逐段调用。
        """
        import base64
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(raw_bytes))
            # 旋转到正确方向(处理 EXIF orientation)
            try:
                from PIL import ImageOps
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass
            img = img.convert("RGB")
            w, h = img.size
            # 若总像素超限,先按宽度等比缩小
            total_pixels = w * h
            if total_pixels > max_pixels:
                scale = (max_pixels / total_pixels) ** 0.5
                w = max(1, int(w * scale))
                h = max(1, int(h * scale))
                img = img.resize((w, h), Image.LANCZOS)
            # 若宽度超限,再缩宽度
            if w > max_width:
                new_h = int(h * max_width / w)
                img = img.resize((max_width, new_h), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except ImportError:
            # PIL 不可用,直接返回原图 base64(可能体积较大)
            return base64.b64encode(raw_bytes).decode("utf-8")
        except Exception as e:
            logger.warning(f"图片压缩失败: {e}")
            try:
                return base64.b64encode(raw_bytes).decode("utf-8")
            except Exception:
                return None

    @staticmethod
    def slice_long_image(raw_bytes: bytes, max_height: int = 2500,
                         overlap: int = 100,
                         max_width: int = 800) -> List[bytes]:
        """将超长图片按高度切成多段,返回每段的 JPEG 字节列表。

        微信长图动辄上万像素高,DeepSeek VL API 拒绝处理。
        切片前先按 max_width 缩小宽度,加快处理并减小体积。
        切片时保留 overlap 像素重叠,避免文字被切断。
        若图片不超长,返回单元素列表(JPEG 压缩后的原图)。
        """
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(raw_bytes))
            try:
                from PIL import ImageOps
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass
            img = img.convert("RGB")
            w, h = img.size
            # 先缩小宽度,加快后续处理(BILINEAR 比 LANCZOS 快很多)
            if w > max_width:
                new_h = int(h * max_width / w)
                img = img.resize((max_width, new_h), Image.BILINEAR)
                w, h = img.size
            if h <= max_height:
                # 不超长,直接压缩返回
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=80)
                return [buf.getvalue()]
            chunks = []
            y = 0
            while y < h:
                bottom = min(y + max_height, h)
                chunk = img.crop((0, y, w, bottom))
                buf = io.BytesIO()
                chunk.save(buf, format="JPEG", quality=80)
                chunks.append(buf.getvalue())
                if bottom >= h:
                    break  # 最后一段,退出
                y = bottom - overlap
            return chunks
        except Exception as e:
            logger.warning(f"图片切片失败: {e},使用原图")
            return [raw_bytes]

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict]:
        """从 LLM 输出中提取 JSON 对象(容错:去除 markdown 标记、多余文本)。"""
        if not text:
            return None
        text = text.strip()
        # 去除 ```json ... ``` 包裹
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        # 找到第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            logger.warning(f"LLM 输出无 JSON: {text[:200]}")
            return None
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            logger.warning(f"LLM 输出 JSON 解析失败: {e}; raw={text[:300]}")
            return None

    def ocr_image(self, image_bytes: bytes, ext: str = "png") -> str:
        """
        使用 DeepSeek-VL 视觉模型对图片简历做 OCR,提取纯文本。

        输入: 图片二进制数据 + 扩展名(png/jpg/jpeg/webp/bmp)
        输出: 图片中的文字内容(纯文本)

        失败返回空字符串,不阻塞主流程。
        """
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY 未配置,跳过图片 OCR")
            return ""

        import base64
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        mime_map = {
            "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "bmp": "image/bmp", "gif": "image/gif",
        }
        mime = mime_map.get(ext.lower(), "image/png")
        data_url = f"data:{mime};base64,{b64}"

        prompt = """请识别这张简历图片中的所有文字内容,按原文顺序输出纯文本。
要求:
1. 完整提取所有文字(姓名、联系方式、教育经历、工作/实习经历、项目经历、技能、证书等)
2. 保留换行和段落结构,不要总结、不要添加解释
3. 直接输出文字内容,不要用 markdown 包裹"""

        try:
            resp = requests.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": DEEPSEEK_VL_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4000,
                },
                timeout=90,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            logger.info(f"图片 OCR 成功,提取 {len(content)} 字符")
            return content.strip()
        except Exception as e:
            logger.error(f"DeepSeek-VL OCR 失败: {e}")
            return ""

    def parse_resume(self, resume_text: str) -> Dict[str, Any]:
        """
        解析简历文本,返回结构化画像 dict。

        返回字段与 UserProfile 对齐:
        school, degree, major, graduation_year, experience_years,
        core_skills, direction_keywords, target_cities, target_industries,
        target_certificates, current_role, summary
        """
        if not resume_text or not resume_text.strip():
            logger.warning("简历文本为空")
            return self._empty_profile()

        prompt = RESUME_PARSE_PROMPT.format(resume_text=resume_text[:8000])
        content = self._chat([{"role": "user", "content": prompt}])
        parsed = self._extract_json(content) if content else None

        if not parsed:
            logger.warning("简历解析失败,返回空画像")
            return self._empty_profile()

        # 字段映射 + 类型校验
        profile = self._empty_profile()
        profile["school"] = str(parsed.get("school", "")).strip()
        profile["degree"] = str(parsed.get("degree", "")).strip()
        profile["major"] = str(parsed.get("major", "")).strip()
        profile["graduation_year"] = str(parsed.get("graduation_year", "")).strip()
        profile["graduation_date"] = str(parsed.get("graduation_date", "")).strip()
        profile["current_role"] = str(parsed.get("current_role", "")).strip()
        profile["summary"] = str(parsed.get("summary", "")).strip()

        # 经验年限:确保为数字
        try:
            profile["experience_years"] = float(parsed.get("experience_years", 0) or 0)
        except (ValueError, TypeError):
            profile["experience_years"] = 0.0

        # 列表字段
        profile["core_skills"] = self._to_list(parsed.get("core_skills"))
        profile["target_cities"] = self._to_list(parsed.get("target_cities"))
        # 行业/公司类型归一化到 mappings.json 定义的标准分类名(与 DB companies 表一致)
        import normalizer as _norm
        profile["target_industries"] = [
            _norm.normalize_industry(x) for x in self._to_list(parsed.get("target_industries"))
        ]
        profile["target_certificates"] = self._to_list(parsed.get("certificates"))
        profile["preferred_company_types"] = [
            _norm.normalize_company_type(x) for x in self._to_list(parsed.get("preferred_company_types"))
        ]
        profile["preferred_difficulties"] = self._to_list(parsed.get("preferred_difficulties"))

        # 亮点(用于丰富画像展示)
        profile["highlights"] = self._to_list(parsed.get("highlights"))

        # 目标方向 → direction_keywords (方向名 → 该方向关键词列表)
        # 优先使用 LLM 直接生成的 direction_keywords(含 5-8 个关键词/方向)
        direction_keywords: Dict[str, List[str]] = {}
        raw_dk = parsed.get("direction_keywords")
        if isinstance(raw_dk, list):
            # LLM 输出格式: [{"direction": "xxx", "keywords": ["a","b"]}, ...]
            for item in raw_dk:
                if isinstance(item, dict):
                    direction = str(item.get("direction", "")).strip()
                    kws = self._to_list(item.get("keywords"))
                    if direction and kws:
                        # 确保方向名本身在关键词列表中
                        if direction not in kws:
                            kws.insert(0, direction)
                        direction_keywords[direction] = kws[:8]  # 最多 8 个
        elif isinstance(raw_dk, dict):
            # 兼容 dict 格式: {"方向名": ["a","b"]}
            for direction, kws in raw_dk.items():
                direction = str(direction).strip()
                kws = self._to_list(kws)
                if direction and kws:
                    if direction not in kws:
                        kws.insert(0, direction)
                    direction_keywords[direction] = kws[:8]

        # 降级:若 LLM 未生成 direction_keywords,用 target_roles 兜底
        if not direction_keywords:
            target_roles = self._to_list(parsed.get("target_roles"))
            for role in target_roles:
                if role:
                    # 至少包含方向名,采集时会用
                    direction_keywords[role] = [role]
        profile["direction_keywords"] = direction_keywords

        logger.info(f"简历解析完成: school={profile['school']} degree={profile['degree']} "
                    f"major={profile['major']} skills={len(profile['core_skills'])}个 "
                    f"directions={len(direction_keywords)}个")
        return profile

    def expand_directions(self, user_directions: List[str],
                          resume_text: str = "",
                          existing_directions: List[str] = None) -> Dict[str, Any]:
        """第二轮:把用户新增的方向词扩展成结构化 fit_directions + 硬技能。

        用户在第一轮解析后,可能手动添加了想投的方向(如"AI开发""Infra"),
        这些词可能很简单或不在岗位树中。本方法用 LLM:
        1. 把方向词映射到岗位树子类(精确)或大类(歧义且简历无法消歧时)
        2. 补充该方向典型需要的硬技能

        Args:
            user_directions: 用户新增的方向词列表
            resume_text: 原始简历文本(用于判断用户是否有相关基础)
            existing_directions: 已有方向名(避免重复输出)

        Returns:
            {"fit_directions": [...], "hard_skills": [{"kw","weight"}]}
        """
        if not user_directions:
            return {"fit_directions": [], "hard_skills": []}

        import job_tree
        tree_block = job_tree.prompt_block()
        existing = existing_directions or []

        dirs_text = "、".join(user_directions)
        existing_text = "、".join(existing) if existing else "(无)"

        prompt = f"""你是校招岗位匹配专家。用户在简历解析后,手动添加了以下想投的岗位方向:
【{dirs_text}】

请基于简历内容,把这些方向词映射到下方岗位类型树的子类,并补充该方向典型需要的硬技能。

简历内容:
\"\"\"{resume_text[:6000]}\"\"\"

已有方向(不要重复输出):{existing_text}

岗位类型树(大类: 子类列表):
{tree_block}

输出严格 JSON(不要输出 JSON 以外的文字):
{{
  "fit_directions": [
    {{
      "direction": "从树中子类名选(如"大模型应用开发""后端开发")。若该词非常歧义且简历无法消歧,用大类名(如"AI工程""开发")",
      "weight": 0.4 到 0.8 之间(用户新增方向默认中等权重 0.5-0.6),
      "evidence": "一句话说明依据(简历有无相关基础/用户明确想投)"
    }}
  ],
  "hard_skills": [
    {{"kw": "该方向典型需要的硬技能名", "weight": 2.0 到 4.0}}
  ]
}}

规则:
- direction 必须是树中存在的子类名或大类名,不允许自造词
- 每个用户方向词至少输出 1 个 fit_direction
- 歧义词(如"Infra""后端")若简历无法定位具体子类,用大类名
- hard_skills 只输出该方向通用需要的技能,不要输出简历里已有的(已有技能在第一轮已提取)
- weight 用户新增方向默认 0.5-0.6,若简历有强相关基础可给到 0.7
"""
        try:
            content = self._chat([{"role": "user", "content": prompt}],
                                 temperature=0.2, max_tokens=4000)
            parsed = self._extract_json(content) if content else None
            if not parsed:
                logger.warning(f"方向扩展 LLM 返回空: {content[:200] if content else ''}")
                return {"fit_directions": [], "hard_skills": []}

            fit_dirs = []
            for item in parsed.get("fit_directions", []):
                if isinstance(item, dict):
                    direction = str(item.get("direction", "")).strip()
                    if direction:
                        fit_dirs.append({
                            "direction": direction,
                            "weight": float(item.get("weight") or 0.5),
                            "evidence": str(item.get("evidence", "")).strip()[:200],
                        })

            hard_skills = []
            for item in parsed.get("hard_skills", []):
                if isinstance(item, dict):
                    kw = str(item.get("kw", "")).strip()
                    if kw:
                        hard_skills.append({
                            "kw": kw,
                            "weight": float(item.get("weight") or 2.5),
                        })

            logger.info(f"方向扩展完成: {len(user_directions)}个方向词 → "
                        f"{len(fit_dirs)}个fit_direction, {len(hard_skills)}个硬技能")
            return {"fit_directions": fit_dirs, "hard_skills": hard_skills}

        except Exception as e:
            logger.error(f"方向扩展失败: {e}")
            return {"fit_directions": [], "hard_skills": []}

    def supplement_from_edits(self, user_edited: Dict,
                              resume_text: str = "",
                              raise_on_error: bool = False) -> Dict[str, Any]:
        """第二轮补充:基于用户编辑后的完整画像(方向/技能/公司/城市)做 AI 分析。

        与 expand_directions 不同,本方法不要求用户必须新增方向。
        只要用户编辑了任意字段(技能/公司/城市/方向),就基于完整画像返回:
        - 新增/扩展的适配方向
        - 基于目标公司和方向补充的硬技能

        Args:
            user_edited: 用户编辑后的画像,含 directions/skills/companies/cities/
                         target_industries/preferred_company_types/fit_directions
            resume_text: 简历文本(用于判断用户基础)

        Returns:
            {"fit_directions": [...], "hard_skills": [{"kw","weight"}]}
        """
        directions = user_edited.get("directions") or []
        if not directions:
            return {"fit_directions": [], "hard_skills": []}

        import job_tree
        tree_block = job_tree.prompt_block()

        skills = user_edited.get("skills") or []
        companies = user_edited.get("companies") or []
        cities = user_edited.get("cities") or []
        industries = user_edited.get("target_industries") or []
        existing_dirs = [d.get("direction", "") for d in (user_edited.get("fit_directions") or [])
                         if isinstance(d, dict)]

        prompt = f"""你是校招岗位匹配专家。用户在简历解析后,调整了求职配置。请基于以下完整画像,做补充分析:

【用户目标方向】{', '.join(directions)}
【用户核心技能】{', '.join(skills) if skills else '(未填写)'}
【目标公司】{', '.join(companies) if companies else '(未填写)'}
【目标城市】{', '.join(cities) if cities else '(未填写)'}
【目标行业】{', '.join(industries) if industries else '(未填写)'}

简历内容:
\"\"\"{resume_text[:6000]}\"\"\"

已有方向(不要重复输出):{', '.join(existing_dirs) if existing_dirs else '(无)'}

岗位类型树(大类: 子类列表):
{tree_block}

请输出严格 JSON(不要输出 JSON 以外的文字):
{{
  "fit_directions": [
    {{
      "direction": "从树中子类名选(如"AI Agent开发""后端开发")。若歧义且简历无法消歧,用大类名",
      "weight": 0.4 到 0.9,
      "evidence": "一句话说明依据(简历基础/目标公司/用户明确意向)"
    }}
  ],
  "hard_skills": [
    {{"kw": "该方向/目标公司典型需要的硬技能", "weight": 2.0 到 4.0}}
  ]
}}

规则:
- direction 必须是树中存在的子类名或大类名,不允许自造词
- 只输出新增方向(不在"已有方向"列表中的),已有方向不要重复
- hard_skills 输出该方向/目标公司典型需要但用户技能列表中没有的技能
- 若用户填了目标公司,优先考虑这些公司常见岗位需要的技能
- 若没有新增方向也没有补充技能,返回空数组
"""
        def _fail(msg: str) -> Dict[str, Any]:
            if raise_on_error:
                raise RuntimeError(msg)
            return {"fit_directions": [], "hard_skills": []}

        try:
            content = self._chat([{"role": "user", "content": prompt}],
                                 temperature=0.2, max_tokens=4000)
        except Exception as e:
            logger.error(f"补充分析异常: {e}")
            return _fail(f"补充分析异常: {e}")

        if content is None:
            logger.error("补充分析失败: LLM 返回空(可能 API Key 无效或服务不可用)")
            return _fail("补充分析失败: LLM 返回空(可能 API Key 无效或服务不可用)")

        try:
            parsed = self._extract_json(content)
        except Exception as e:
            logger.error(f"补充分析 JSON 解析失败: {e}")
            return _fail(f"补充分析 JSON 解析失败: {e}")

        if not parsed:
            logger.warning(f"补充分析 LLM 返回空: {content[:200]}")
            return _fail("补充分析返回空结果(可能画像信息不足)")

        fit_dirs = []
        for item in parsed.get("fit_directions", []):
            if isinstance(item, dict):
                direction = str(item.get("direction", "")).strip()
                if direction:
                    fit_dirs.append({
                        "direction": direction,
                        "weight": float(item.get("weight") or 0.5),
                        "evidence": str(item.get("evidence", "")).strip()[:200],
                    })

        hard_skills = []
        for item in parsed.get("hard_skills", []):
            if isinstance(item, dict):
                kw = str(item.get("kw", "")).strip()
                if kw:
                    hard_skills.append({
                        "kw": kw,
                        "weight": float(item.get("weight") or 2.5),
                    })

        logger.info(f"补充分析完成: {len(fit_dirs)}个方向, {len(hard_skills)}个技能")
        return {"fit_directions": fit_dirs, "hard_skills": hard_skills}

    @staticmethod
    def _empty_profile() -> Dict[str, Any]:
        """返回空画像结构(LLM 失败时的降级值)"""
        return {
            "school": "",
            "degree": "",
            "major": "",
            "graduation_year": "",
            "graduation_date": "",
            "experience_years": 0.0,
            "core_skills": [],
            "direction_keywords": {},
            "target_cities": [],
            "target_industries": [],
            "target_certificates": [],
            "preferred_company_types": [],
            "preferred_difficulties": [],
            "current_role": "",
            "summary": "",
            "highlights": [],
        }

    @staticmethod
    def _to_list(value: Any) -> List[str]:
        """将 LLM 输出的字段值规范化为字符串列表"""
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            # 处理 "A, B, C" 或 "A、B、C" 格式
            parts = re.split(r"[,，、;；\n]", value)
            return [p.strip() for p in parts if p.strip()]
        return [str(value).strip()] if str(value).strip() else []

    def optimize_keywords(self, direction: str, resume_text: str,
                          existing_keywords: List[str] = None) -> List[str]:
        """
        基于简历内容和用户填写的求职方向,优化生成 5-8 个搜索关键词。

        使用场景:
        - 用户手动填写方向名后,点击"优化"按钮
        - 根据简历中的经历/技能/证书,为该方向生成精准的搜索关键词

        返回关键词列表(含方向名本身)。
        """
        if not direction or not direction.strip():
            return []
        direction = direction.strip()
        existing = existing_keywords or []

        prompt = f"""你是招聘信息搜索专家。请基于以下简历内容,为求职方向"{direction}"生成精准的搜索关键词。

这些关键词将直接用于搜索引擎抓取招聘岗位,必须精准、专业、覆盖全面。

简历摘要:
\"\"\"{resume_text[:3000]}\"\"\"

用户已有的关键词(可参考改进): {', '.join(existing) if existing else '无'}

请输出 JSON(不要输出其他文字):
{{
  "keywords": ["关键词1", "关键词2", ...]
}}

关键词要求(共 5-8 个):
1. 必须包含方向名 "{direction}" 本身
2. 同义/近义岗位名(如 "FOF投资经理" → "基金投资经理"、"资产配置研究员")
3. 细分领域术语(如 "基金筛选"、"组合管理"、"母基金")
4. 英文常用缩写(如 "FOF"、"portfolio")
5. 与简历经历相关的技能/工具词
6. 关键词必须简洁,不要用完整句子
"""
        content = self._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=300,
        )
        parsed = self._extract_json(content) if content else None
        if not parsed:
            # 降级:方向名 + 已有关键词
            result = [direction]
            for kw in existing:
                if kw and kw not in result:
                    result.append(kw)
            return result[:8]

        kws = self._to_list(parsed.get("keywords"))
        # 确保方向名在列表中
        if direction not in kws:
            kws.insert(0, direction)
        # 去重并限制数量
        seen = set()
        unique = []
        for kw in kws:
            if kw and kw.lower() not in seen:
                seen.add(kw.lower())
                unique.append(kw)
        return unique[:8]

    def extract_deadline(self, jd_text: str) -> str:
        """
        从 JD 文本中提取投递截止日期(校招岗位常用)。
        返回 YYYY-MM-DD 格式字符串,提取失败返回空字符串。
        """
        if not jd_text:
            return ""
        prompt = (
            "你是招聘信息解析助手。请从以下 JD 文本中提取投递截止日期。\n"
            "只输出日期(YYYY-MM-DD 格式),没有明确截止日期则输出空字符串。\n"
            "不要输出其他文字。\n\n"
            f"JD 文本:\n{jd_text[:3000]}"
        )
        content = self._chat([{"role": "user", "content": prompt}], max_tokens=50)
        if not content:
            return ""
        content = content.strip().strip('"').strip("'")
        # 匹配 YYYY-MM-DD 或 YYYY/MM/DD
        m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", content)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return ""

    def verify_campus_announcement(self, title: str, jd_text: str,
                                    company: str = "") -> Dict:
        """
        AI 检视校招公告:确认是否为完整的 2027 届校招公告,信息是否准确。

        返回: {
            is_valid: bool,        # 是否为有效校招公告
            is_2027: bool,         # 是否为 2027 届
            job_title: str,        # 修正后的岗位标题
            publish_time: str,     # 发布时间(YYYY-MM-DD)
            confidence: str        # 高/中/低
        }
        """
        if not jd_text or len(jd_text.strip()) < 30:
            return {"is_valid": False, "is_2027": False, "job_title": title,
                    "publish_time": "", "confidence": "低"}

        prompt = f"""你是校招信息审核专家。请审核以下招聘公告,判断其是否为有效的 2027 届校园招聘公告。

公司: {company or '未知'}
标题: {title}

公告正文:
\"\"\"{jd_text[:3000]}\"\"\"

请输出 JSON(不要输出其他文字):
{{
  "is_valid": true/false,
  "is_2027": true/false,
  "job_title": "修正后的岗位标题(如果标题不准确请修正,否则原样返回)",
  "publish_time": "公告发布日期(YYYY-MM-DD,无法确定则空字符串)",
  "confidence": "高/中/低"
}}

判断标准:
- is_valid=true: 是完整的招聘公告(非列表页/广告/新闻),有明确的招聘岗位和申请方式
- is_2027=true: 面向 2027 届毕业生(含 2027届、2026年秋招、class of 2027 等表述;2026届春招不算)
"""
        content = self._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=300,
        )
        parsed = self._extract_json(content) if content else None
        if not parsed:
            return {"is_valid": False, "is_2027": False, "job_title": title,
                    "publish_time": "", "confidence": "低"}
        return {
            "is_valid": bool(parsed.get("is_valid", False)),
            "is_2027": bool(parsed.get("is_2027", False)),
            "job_title": str(parsed.get("job_title", title)).strip(),
            "publish_time": str(parsed.get("publish_time", "")).strip(),
            "confidence": str(parsed.get("confidence", "低")).strip(),
        }

    def generate_jd_summary(self, jd_text: str, title: str) -> str:
        """
        AI 生成 JD 摘要(100字内),用于总数据库展示。
        """
        if not jd_text or len(jd_text.strip()) < 30:
            return title[:100]
        prompt = f"""请用 100 字以内概括以下招聘公告的核心内容(岗位职责+要求)。

标题: {title}
正文:
\"\"\"{jd_text[:2000]}\"\"\"

只输出摘要,不要其他文字。"""
        content = self._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=200,
        )
        if content:
            return content.strip()[:200]
        return jd_text[:100].replace("\n", " ")

    def analyze_jd(self, jd_text: str, title: str, profile: Dict) -> Dict[str, str]:
        """
        基于 JD 正文深度分析,生成高质量摘要和申请建议。

        核心改进(对标参考提示词):
        - 必须基于 JD 正文(职责+要求)分析,严禁只看 title
        - 简评引用 JD 职责要点
        - 申请建议针对 JD 要求具体化

        返回: {jd_summary, match_analysis, application_advice}
        """
        if not jd_text or len(jd_text.strip()) < 50:
            return {
                "jd_summary": title,
                "match_analysis": "JD 正文信息不足",
                "application_advice": "请查看 JD 详情了解具体要求",
            }

        # 用户画像摘要(用于匹配分析)
        profile_summary = (
            f"学校:{profile.get('school','')},学历:{profile.get('degree','')},"
            f"专业:{profile.get('major','')},工作年限:{profile.get('experience_years',0)}年,"
            f"核心技能:{','.join(profile.get('core_skills',[])[:8])}"
        )

        prompt = f"""你是资深招聘顾问。请基于以下 JD 正文(而非仅标题)进行深度分析。

用户画像: {profile_summary}

JD 标题: {title}

JD 正文:
\"\"\"{jd_text[:4000]}\"\"\"

请输出 JSON(不要输出其他文字):
{{
  "jd_summary": "JD 核心摘要(100字内):提炼岗位职责和核心要求,引用JD原文要点",
  "match_analysis": "与用户画像的匹配分析(80字内):指出匹配点和差距",
  "application_advice": "申请建议(80字内):针对JD要求,说明简历应突出的具体经验"
}}
"""
        content = self._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=600,
        )
        parsed = self._extract_json(content) if content else None
        if not parsed:
            # 降级:用前 200 字作为摘要
            return {
                "jd_summary": jd_text[:200].replace("\n", " "),
                "match_analysis": "",
                "application_advice": "",
            }
        return {
            "jd_summary": str(parsed.get("jd_summary", "")).strip(),
            "match_analysis": str(parsed.get("match_analysis", "")).strip(),
            "application_advice": str(parsed.get("application_advice", "")).strip(),
        }

    def quality_screen_jobs(self, jobs: List[Dict], profile: Dict,
                            batch_size: int = 10) -> List[Dict]:
        """
        AI 质量筛选层:对采集到的原始岗位做 LLM 质量过滤。

        评估维度:
        1. 匹配度:岗位是否与用户求职方向相关
        2. 准确性:是否为真实招聘信息(非搜索页/聚合页/广告)
        3. 及时性:是否为近期发布的岗位
        4. 非垃圾:排除标题党、无关内容、重复信息

        输入: jobs = [{title, company, snippet, url, posted, ...}]
        输出: 通过质量筛选的岗位列表(可能少于输入)

        LLM 不可用时返回原列表(不阻塞主流程)。
        """
        if not jobs:
            return []

        # 构造用户方向关键词,用于匹配度评估
        all_directions = []
        direction_keywords = profile.get("direction_keywords") or {}
        if isinstance(direction_keywords, dict):
            for direction, kws in direction_keywords.items():
                all_directions.append(direction)
                all_directions.extend(kws if isinstance(kws, list) else [])
        direction_str = "、".join(all_directions[:20]) if all_directions else "未指定"
        role = profile.get("role", "") or ""
        role_label = {"internship": "实习", "campus": "校招",
                      "social": "社招"}.get(role, "未知")

        passed = []
        for i in range(0, len(jobs), batch_size):
            batch = jobs[i:i + batch_size]
            # 构造岗位列表(JSON 格式,便于 LLM 解析)
            job_list = []
            for idx, j in enumerate(batch):
                job_list.append({
                    "idx": idx,
                    "title": j.get("title", "")[:100],
                    "company": j.get("company", "")[:50],
                    "snippet": j.get("snippet", "")[:300],
                    "url": j.get("url", "")[:100],
                    "posted": j.get("posted", ""),
                })

            prompt = f"""你是招聘信息质量审核专家。请对以下岗位信息进行质量筛选。

用户求职方向: {direction_str}
用户角色: {role_label}

岗位列表(JSON):
{json.dumps(job_list, ensure_ascii=False)}

请对每个岗位评估并输出 JSON 数组(不要输出其他文字):
[
  {{
    "idx": 0,
    "pass": true/false,
    "reason": "筛选理由(30字内)"
  }}
]

筛选标准(pass=true 需同时满足):
1. 匹配度:岗位与用户求职方向相关(或为通用管培/校招)
2. 准确性:是真实招聘岗位,非搜索结果页、招聘平台列表页、广告、新闻
3. 非垃圾:非标题党、非无关内容、岗位描述完整
4. 及时性:发布时间在合理范围内(未知不扣分,但明确标注"已结束"/"过期"的排除)

注意:
- 社招用户:校招/应届/管培岗位 pass=false
- 校招用户:要求3年以上工作经验的社招岗位 pass=false
- URL 明显是搜索页(含/search、/list、?q=等)的 pass=false
"""
            content = self._chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1, max_tokens=1500,
            )
            if not content:
                # LLM 不可用,本批全部通过(不阻塞)
                passed.extend(batch)
                continue

            parsed = self._extract_json(content)
            if not parsed or not isinstance(parsed, list):
                # 解析失败,本批全部通过
                passed.extend(batch)
                continue

            # 建立 idx -> pass 映射
            pass_map = {}
            for item in parsed:
                if isinstance(item, dict) and "idx" in item:
                    pass_map[item["idx"]] = bool(item.get("pass", True))

            for idx, j in enumerate(batch):
                if pass_map.get(idx, True):
                    passed.append(j)

        logger.info(f"AI质量筛选: 输入 {len(jobs)} 条,通过 {len(passed)} 条")
        return passed
