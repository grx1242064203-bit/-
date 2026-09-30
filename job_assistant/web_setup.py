"""
求职配置 Web 页 — XHS 店铺用户的入口。

流程:
  1. 用户从 XHS 店铺收到配置链接: /setup?order_id=xxx
  2. 验证订单号(开发阶段接受任意,生产对接小红书 API)
  3. 上传/粘贴简历 → AI 解析画像
  4. 确认/调整配置 → 创建专属飞书表格
  5. 返回飞书表格链接(互联网可查看,无需登录)

第一性原理:
- 零安装零登录:用户用浏览器打开链接即可完成全部配置
- 订单号即身份:order_id 是用户唯一标识,不需要飞书账号
- 配置即开即用:填完立即拿到岗位表格

对抗性审查:
- 订单号被冒用:生产阶段必须对接小红书 API 验证订单真实性
- 简历文本过长:截断到 8000 字符,避免 LLM 超限
- 飞书表格创建失败:给用户友好提示,可重试
"""
import os
import json
import logging
import time
from typing import Optional

from flask import Flask, request, jsonify, render_template_string, send_from_directory

from config import settings
from models import User, UserProfile, UserStore
from llm_client import LLMClient
from feishu_table_service import FeishuTableService
import normalizer

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB 上传限制

user_store = UserStore()
llm_client = LLMClient()
table_service = FeishuTableService()

# 有效订单白名单(开发阶段用,生产对接小红书 API)
# key=order_id, value={"plan": "autumn", "expire_days": 90}
VALID_ORDERS_FILE = os.path.join(settings.DATA_DIR, "valid_orders.json")


def _load_valid_orders() -> dict:
    if os.path.exists(VALID_ORDERS_FILE):
        with open(VALID_ORDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _validate_order(order_id: str) -> Optional[dict]:
    """
    验证订单号是否有效。
    开发阶段:白名单机制(管理员手动录入)。
    生产阶段:对接小红书开放平台订单 API 实时验证。
    """
    if not order_id:
        return None
    orders = _load_valid_orders()
    if order_id in orders:
        return orders[order_id]
    # 开发阶段兜底:若白名单为空,接受任意订单(方便测试)
    if not orders:
        logger.warning(f"白名单为空,开发模式接受任意订单: {order_id}")
        return {"plan": "autumn", "expire_days": 90}
    return None


def _parse_resume_text(file_storage) -> str:
    """从上传的文件中提取简历文本(支持 .txt/.pdf/.docx)。"""
    if not file_storage:
        return ""
    filename = file_storage.filename.lower()
    content = file_storage.read()
    if filename.endswith(".txt"):
        return content.decode("utf-8", errors="ignore")
    if filename.endswith(".pdf"):
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            return "\n".join(
                page.extract_text() for page in reader.pages
                if page.extract_text()
            )
        except Exception as e:
            logger.warning(f"PDF 解析失败: {e}")
            return ""
    if filename.endswith(".docx"):
        try:
            import io
            from docx import Document
            doc = Document(io.BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            logger.warning(f"DOCX 解析失败: {e}")
            return ""
    return content.decode("utf-8", errors="ignore")


# ==================== 页面路由 ====================

SETUP_PAGE_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>校招岗位雷达 - 求职配置</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #f5f7fa; color: #333; padding: 20px; }
  .container { max-width: 600px; margin: 0 auto; }
  .card { background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 16px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
  h1 { font-size: 22px; margin-bottom: 8px; }
  .subtitle { color: #888; font-size: 14px; margin-bottom: 20px; }
  label { display: block; font-size: 14px; color: #555; margin-bottom: 6px; font-weight: 500; }
  input, select, textarea { width: 100%; padding: 10px 12px; border: 1px solid #ddd;
           border-radius: 8px; font-size: 14px; margin-bottom: 14px; }
  textarea { min-height: 120px; resize: vertical; }
  .btn { display: inline-block; padding: 12px 24px; background: #3370ff; color: #fff;
         border: none; border-radius: 8px; font-size: 15px; cursor: pointer; width: 100%; }
  .btn:hover { background: #2860e0; }
  .btn:disabled { background: #aaa; cursor: not-allowed; }
  .tag { display: inline-block; padding: 4px 10px; background: #eef2ff; color: #3370ff;
         border-radius: 12px; font-size: 12px; margin: 3px; }
  .section-title { font-size: 16px; font-weight: 600; margin: 16px 0 12px; }
  .error { color: #e53935; font-size: 13px; margin: 8px 0; }
  .success { color: #43a047; font-size: 14px; margin: 8px 0; }
  .hidden { display: none; }
  .link-box { background: #f0f7ff; border: 1px solid #b3d4ff; border-radius: 8px;
              padding: 12px; word-break: break-all; margin: 12px 0; }
  .multi-select { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
  .chip { padding: 6px 12px; border: 1px solid #ddd; border-radius: 16px; font-size: 13px;
          cursor: pointer; user-select: none; }
  .chip.active { background: #3370ff; color: #fff; border-color: #3370ff; }
  .loading { text-align: center; padding: 20px; color: #888; }
</style>
</head>
<body>
<div class="container">
  <div class="card">
    <h1>🎯 校招岗位雷达</h1>
    <div class="subtitle">配置你的求职偏好,AI 每天为你筛选最匹配的校招岗位</div>
  </div>

  <!-- Step 1: 订单验证 -->
  <div id="step-verify" class="card">
    <div class="section-title">第一步:验证订单</div>
    <label>小红书订单号</label>
    <input id="order_id" placeholder="请输入订单号" value="{{ order_id }}">
    <button class="btn" onclick="verifyOrder()">验证订单</button>
    <div id="verify-msg"></div>
  </div>

  <!-- Step 2: 简历上传 -->
  <div id="step-resume" class="card hidden">
    <div class="section-title">第二步:上传简历</div>
    <label>粘贴简历文本</label>
    <textarea id="resume_text" placeholder="粘贴你的简历文本,AI 将自动解析你的学校、专业、技能等信息"></textarea>
    <label>或上传简历文件(支持图片/.txt/.pdf/.docx,可多选)</label>
    <input type="file" id="resume_file" accept=".txt,.pdf,.docx,.png,.jpg,.jpeg,.webp,.bmp" multiple>
    <div id="file-list" style="font-size:12px;color:#888;margin-top:4px"></div>
    <button class="btn" onclick="parseResume()" style="margin-top:12px">AI 解析简历</button>
    <div id="resume-msg"></div>
  </div>

  <!-- Step 3: 确认配置 -->
  <div id="step-profile" class="card hidden">
    <div class="section-title">第三步:确认求职配置</div>
    <label>学校</label>
    <input id="school">
    <label>学历</label>
    <select id="degree">
      <option value="">请选择</option>
      <option value="大专">大专</option>
      <option value="本科">本科</option>
      <option value="硕士">硕士</option>
      <option value="博士">博士</option>
    </select>
    <label>专业</label>
    <input id="major">
    <label>毕业年份</label>
    <select id="graduation_year">
      <option value="">请选择</option>
      <option value="2025">2025届</option>
      <option value="2026">2026届</option>
      <option value="2027">2027届</option>
      <option value="2028">2028届</option>
    </select>
    <label>目标城市(逗号分隔,留空=不限)</label>
    <input id="target_cities" placeholder="如:北京,上海,深圳">
    <label>目标行业</label>
    <div class="multi-select" id="industry_tags"></div>
    <label>偏好公司类型</label>
    <div class="multi-select" id="company_type_tags"></div>
    <label>目标岗位方向(逗号分隔)</label>
    <input id="directions" placeholder="如:产品经理,运营,数据分析">
    <button class="btn" onclick="confirmSetup()">生成我的岗位库</button>
    <div id="confirm-msg"></div>
  </div>

  <!-- Step 4: 完成 -->
  <div id="step-done" class="card hidden">
    <div class="section-title">🎉 配置完成!</div>
    <p>你的专属校招岗位库已创建,以下三张表每天自动更新(无需登录):</p>
    <div class="link-box" id="table_link"></div>
    <p style="font-size:13px;color:#888;margin-top:12px">
      每天早上 9 点,系统会自动把与你匹配的新岗位写入「我的匹配岗位」表。<br>
      建议收藏该页面链接,每天打开查看最新岗位。
    </p>
  </div>
</div>

<script>
const INDUSTRIES = {{ industries | safe }};
const COMPANY_TYPES = {{ company_types | safe }};

let currentOrderId = "";

function verifyOrder() {
  const orderId = document.getElementById('order_id').value.trim();
  if (!orderId) { showMsg('verify-msg', '请输入订单号', 'error'); return; }
  fetch('/api/verify-order', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({order_id: orderId})
  }).then(r => r.json()).then(data => {
    if (data.valid) {
      currentOrderId = orderId;
      document.getElementById('step-verify').classList.add('hidden');
      document.getElementById('step-resume').classList.remove('hidden');
      showMsg('verify-msg', '', '');
    } else {
      showMsg('verify-msg', data.msg || '订单号无效', 'error');
    }
  });
}

function parseResume() {
  const text = document.getElementById('resume_text').value;
  const files = document.getElementById('resume_file').files;
  if (!text && (!files || files.length === 0)) { showMsg('resume-msg', '请粘贴简历文本或上传简历文件', 'error'); return; }
  showMsg('resume-msg', '⏳ AI 正在解析简历(图片需OCR,约10-30秒)...', '');
  const fd = new FormData();
  fd.append('resume_text', text);
  for (let i = 0; i < files.length; i++) fd.append('resume_files', files[i]);
  fetch('/api/parse-resume', {method: 'POST', body: fd})
    .then(r => r.json()).then(data => {
      if (data.profile) {
        const p = data.profile;
        document.getElementById('school').value = p.school || '';
        document.getElementById('degree').value = p.degree || '';
        document.getElementById('major').value = p.major || '';
        document.getElementById('graduation_year').value = p.graduation_year || '';
        document.getElementById('target_cities').value = (p.target_cities || []).join(',');
        document.getElementById('directions').value = Object.keys(p.direction_keywords || {}).join(',');
        renderTags('industry_tags', INDUSTRIES, p.target_industries || []);
        renderTags('company_type_tags', COMPANY_TYPES, p.preferred_company_types || []);
        document.getElementById('step-resume').classList.add('hidden');
        document.getElementById('step-profile').classList.remove('hidden');
        showMsg('resume-msg', '✅ 简历解析完成,请确认配置', 'success');
      } else {
        showMsg('resume-msg', '简历解析失败,请手动填写配置', 'error');
        document.getElementById('step-resume').classList.add('hidden');
        document.getElementById('step-profile').classList.remove('hidden');
      }
    });
}

function renderTags(containerId, options, selected) {
  const c = document.getElementById(containerId);
  c.innerHTML = '';
  options.forEach(opt => {
    const chip = document.createElement('div');
    chip.className = 'chip' + (selected.includes(opt) ? ' active' : '');
    chip.textContent = opt;
    chip.onclick = () => chip.classList.toggle('active');
    c.appendChild(chip);
  });
}

function getSelectedTags(containerId) {
  return Array.from(document.getElementById(containerId).querySelectorAll('.chip.active'))
    .map(c => c.textContent);
}

function confirmSetup() {
  const industries = getSelectedTags('industry_tags');
  const companyTypes = getSelectedTags('company_type_tags');
  const directions = document.getElementById('directions').value.split(',').map(s=>s.trim()).filter(Boolean);
  const dirKw = {};
  directions.forEach(d => { if (d) dirKw[d] = [d]; });
  const profile = {
    role: 'campus',
    school: document.getElementById('school').value,
    degree: document.getElementById('degree').value,
    major: document.getElementById('major').value,
    graduation_year: document.getElementById('graduation_year').value,
    target_cities: document.getElementById('target_cities').value.split(',').map(s=>s.trim()).filter(Boolean),
    target_industries: industries,
    preferred_company_types: companyTypes,
    direction_keywords: dirKw,
  };
  showMsg('confirm-msg', '⏳ 正在创建你的岗位库...', '');
  fetch('/api/confirm-setup', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({order_id: currentOrderId, profile})
  }).then(r => r.json()).then(data => {
    if (data.share_url) {
      document.getElementById('step-profile').classList.add('hidden');
      document.getElementById('step-done').classList.remove('hidden');
      const links = [
        {label: '📋 我的匹配岗位', url: data.user_table_url || data.share_url},
        {label: '🏢 秋招公司总表', url: data.company_table_url},
        {label: '💼 校招岗位总表', url: data.position_table_url},
      ];
      document.getElementById('table_link').innerHTML = links.map(l =>
        '<div style="margin:8px 0"><a href="' + l.url + '" target="_blank" style="font-size:15px">' + l.label + '</a></div>'
      ).join('');
    } else {
      showMsg('confirm-msg', data.msg || '创建失败,请重试', 'error');
    }
  });
}

function showMsg(id, text, type) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = type || '';
}

// 初始化行业和公司类型标签
renderTags('industry_tags', INDUSTRIES, []);
renderTags('company_type_tags', COMPANY_TYPES, []);

// 文件选择预览
document.getElementById('resume_file').addEventListener('change', function() {
  const names = Array.from(this.files).map(f => f.name);
  document.getElementById('file-list').textContent = names.length ? '已选: ' + names.join(', ') : '';
});

// URL 带 order_id 时自动填充
const urlParams = new URLSearchParams(window.location.search);
const oid = urlParams.get('order_id');
if (oid) document.getElementById('order_id').value = oid;
</script>
</body>
</html>
"""


@app.route("/setup")
def setup_page():
    """配置页入口。"""
    order_id = request.args.get("order_id", "")
    return render_template_string(
        SETUP_PAGE_HTML,
        order_id=order_id,
        industries=json.dumps(normalizer.get_industry_options(), ensure_ascii=False),
        company_types=json.dumps(normalizer.get_company_type_options(), ensure_ascii=False),
    )


@app.route("/api/verify-order", methods=["POST"])
def api_verify_order():
    """验证订单号。"""
    data = request.get_json() or {}
    order_id = data.get("order_id", "").strip()
    order_info = _validate_order(order_id)
    if order_info:
        return jsonify({"valid": True, "plan": order_info.get("plan", "autumn")})
    return jsonify({"valid": False, "msg": "订单号无效或已使用"}), 400


@app.route("/api/parse-resume", methods=["POST"])
def api_parse_resume():
    """上传简历 → AI 解析画像。支持文本、txt/pdf/docx、图片(OCR)。"""
    resume_text = request.form.get("resume_text", "")

    # 处理上传的文件(支持多文件)
    files = request.files.getlist("resume_files")
    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
    doc_exts = {".txt", ".pdf", ".docx"}
    ocr_texts = []

    for f in files:
        if not f or not f.filename:
            continue
        ext = "." + f.filename.lower().rsplit(".", 1)[-1] if "." in f.filename else ""
        if ext in image_exts:
            # 图片:用 DeepSeek VL OCR 提取文字
            img_bytes = f.read()
            logger.info(f"图片简历 OCR: {f.filename} ({len(img_bytes)} bytes)")
            ocr_text = llm_client.ocr_image(img_bytes, ext.lstrip("."))
            if ocr_text:
                ocr_texts.append(ocr_text)
            else:
                logger.warning(f"图片 OCR 失败: {f.filename}")
        elif ext in doc_exts:
            text = _parse_resume_text(f)
            if text:
                resume_text = (resume_text + "\n" + text).strip() if resume_text else text

    # 合并 OCR 文本
    if ocr_texts:
        ocr_combined = "\n\n".join(ocr_texts)
        resume_text = (resume_text + "\n\n" + ocr_combined).strip() if resume_text else ocr_combined

    if not resume_text or len(resume_text.strip()) < 20:
        return jsonify({"error": "简历内容过短或图片识别失败,请提供完整简历"}), 400

    try:
        profile = llm_client.parse_resume(resume_text)
        return jsonify({"profile": profile})
    except Exception as e:
        logger.error(f"简历解析失败: {e}")
        return jsonify({"error": "简历解析失败,请稍后重试"}), 500


@app.route("/api/confirm-setup", methods=["POST"])
def api_confirm_setup():
    """确认配置 → 创建用户 + 飞书表格 → 返回链接。"""
    data = request.get_json() or {}
    order_id = data.get("order_id", "").strip()
    profile_data = data.get("profile", {})

    # 1. 验证订单
    order_info = _validate_order(order_id)
    if not order_info:
        return jsonify({"error": "订单号无效"}), 400

    # 2. 检查是否已创建(防重复)
    existing = user_store.get_by_order_id(order_id)
    if existing and existing.feishu_base_token:
        share_url = table_service.client.get_share_url(existing.feishu_base_token)
        return jsonify({"share_url": share_url, "msg": "你已创建过岗位库"})

    # 3. 创建用户
    user_id = f"xhs_{order_id}"
    user = user_store.get(user_id)
    if not user:
        # 计算过期日期
        plan = order_info.get("plan", "autumn")
        expire_days = order_info.get("expire_days", 90)
        expire_ts = time.time() + expire_days * 86400
        expire_date = time.strftime("%Y-%m-%d", time.localtime(expire_ts))
        user = User(id=user_id, order_id=order_id, plan=plan, expire_date=expire_date)

    # 4. 设置画像
    user.profile = UserProfile(**{k: v for k, v in profile_data.items()
                                  if k in UserProfile.__dataclass_fields__})
    user.profile.role = "campus"  # 强制校招

    # 5. 创建专属飞书表格
    try:
        table_result = table_service.create_user_bitable(
            user_display_name=profile_data.get("school", "校招用户")
        )
        user.feishu_base_token = table_result["app_token"]
        user.feishu_table_id = table_result["jobs_table_id"]
        user.feishu_closed_table_id = table_result["closed_table_id"]
        user.feishu_mt_table_id = table_result["mt_table_id"]
    except Exception as e:
        logger.error(f"飞书表格创建失败: {e}")
        return jsonify({"error": "岗位库创建失败,请稍后重试"}), 500

    # 6. 保存用户
    user_store.upsert(user)
    logger.info(f"用户配置完成: {user_id} -> {table_result['share_url']}")

    # 7. 返回三张表链接(用户匹配表 + 公司总表 + 岗位总表)
    from config import settings
    master_base = settings.MASTER_APP_TOKEN
    company_table_url = f"https://www.feishu.cn/base/{master_base}?table={settings.MASTER_COMPANY_TABLE_ID}"
    position_table_url = f"https://www.feishu.cn/base/{master_base}?table={settings.MASTER_POSITION_TABLE_ID}"

    return jsonify({
        "share_url": table_result["share_url"],
        "user_table_url": table_result["share_url"],
        "company_table_url": company_table_url,
        "position_table_url": position_table_url,
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=5000, debug=False)
