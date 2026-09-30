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
import resume_parser

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
  /* 简历分析卡片 */
  .analysis-block { background: #fafbfc; border: 1px solid #e8eaf0; border-radius: 10px;
                   padding: 14px 16px; margin-bottom: 12px; }
  .analysis-label { font-size: 12px; color: #888; margin-bottom: 6px; font-weight: 600;
                    text-transform: uppercase; letter-spacing: 0.5px; }
  .analysis-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .skill-tag { display: inline-block; padding: 4px 10px; background: #eef2ff; color: #3370ff;
               border-radius: 12px; font-size: 13px; }
  .skill-tag.edit { cursor: pointer; }
  .skill-tag .rm { margin-left: 4px; color: #aaa; cursor: pointer; }
  .add-input { width: 120px; padding: 4px 8px; font-size: 13px; border: 1px solid #ddd;
               border-radius: 12px; }
  .add-btn { padding: 4px 10px; font-size: 12px; background: #3370ff; color: #fff;
             border: none; border-radius: 12px; cursor: pointer; }
  .profile-textarea { width: 100%; box-sizing: border-box; padding: 10px 12px;
                      font-size: 14px; line-height: 1.6; border: 1px solid #ddd;
                      border-radius: 10px; resize: vertical; font-family: inherit;
                      background: #fafafa; }
  .profile-textarea:focus { outline: none; border-color: #3370ff; background: #fff; }
  .highlight-item { font-size: 13px; color: #444; padding: 3px 0; padding-left: 16px;
                    position: relative; }
  .highlight-item::before { content: "▸"; position: absolute; left: 0; color: #3370ff; }
  .eta-bar { background: #fff8e1; border: 1px solid #ffe082; border-radius: 8px;
             padding: 10px 14px; font-size: 13px; color: #6d4c00; margin: 12px 0; }
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #fff;
             border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;
             vertical-align: middle; margin-right: 6px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .field-row { display: flex; gap: 10px; margin-bottom: 12px; }
  .field-row > div { flex: 1; }
  .field-row label { margin-bottom: 4px; }
  .field-row input { margin-bottom: 0; }
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

  <!-- Step 3: 简历分析 + 确认配置 -->
  <div id="step-profile" class="card hidden">
    <div class="section-title">第三步:AI 简历画像分析</div>
    <p style="font-size:13px;color:#888;margin-bottom:14px">AI 已解析你的简历,下方为多维度分析结果。你可以点击修改任何内容,确认后生成专属岗位库。</p>

    <div class="analysis-block">
      <div class="analysis-label">📋 基本信息</div>
      <div class="field-row">
        <div><label>学校</label><input id="school"></div>
        <div><label>学历</label>
          <select id="degree">
            <option value="">请选择</option>
            <option value="本科">本科</option>
            <option value="硕士">硕士</option>
            <option value="博士">博士</option>
            <option value="大专">大专</option>
          </select>
        </div>
      </div>
      <div class="field-row">
        <div><label>专业</label><input id="major"></div>
        <div><label>毕业年份</label>
          <select id="graduation_year">
            <option value="">请选择</option>
            <option value="2025">2025届</option>
            <option value="2026">2026届</option>
            <option value="2027">2027届</option>
            <option value="2028">2028届</option>
          </select>
        </div>
      </div>
    </div>

    <div class="analysis-block">
      <div class="analysis-label">📝 简历分析摘要 <span style="font-weight:normal;color:#aaa;font-size:11px">(可直接修改,AI 将基于此理解你的背景)</span></div>
      <textarea id="profile_summary" class="profile-textarea" rows="5" placeholder="AI 解析的简历摘要将显示在这里,你可以修改..." oninput="markEdited()"></textarea>
    </div>

    <div class="analysis-block">
      <div class="analysis-label">💡 简历亮点</div>
      <div id="highlights_list"></div>
    </div>

    <div class="analysis-block">
      <div class="analysis-label">🎯 AI 方向匹配分析 <span style="font-weight:normal;color:#aaa;font-size:11px">(AI 根据简历推断的适配方向及依据,可在下方增删调整)</span></div>
      <div id="fit_directions_list"></div>
    </div>

    <div class="analysis-block">
      <div class="analysis-label">🛠 核心技能 <span style="font-weight:normal;color:#aaa;font-size:11px">(点击 × 删除,输入后回车添加)</span></div>
      <div class="analysis-row" id="skills_tags"></div>
      <div style="margin-top:6px">
        <input class="add-input" id="skill_input" placeholder="添加技能" onkeydown="if(event.key==='Enter')addSkill()">
        <button class="add-btn" onclick="addSkill()">添加</button>
      </div>
    </div>

    <div class="analysis-block">
      <div class="analysis-label">🎯 目标岗位方向 <span style="font-weight:normal;color:#aaa;font-size:11px">(点击 × 删除,输入后回车添加。可添加简历中没有但想投的方向)</span></div>
      <div class="analysis-row" id="directions_tags"></div>
      <div style="margin-top:6px">
        <input class="add-input" id="direction_input" placeholder="添加方向,如 AI开发/Infra" onkeydown="if(event.key==='Enter')addDirection()">
        <button class="add-btn" onclick="addDirection()">添加</button>
      </div>
    </div>

    <div class="analysis-block">
      <div class="analysis-label">🏢 目标公司 <span style="font-weight:normal;color:#aaa;font-size:11px">(可选,填写后优先推荐同行业/同类型公司)</span></div>
      <div class="analysis-row" id="companies_tags"></div>
      <div style="margin-top:6px">
        <input class="add-input" id="company_input" placeholder="添加公司,如 腾讯/字节" onkeydown="if(event.key==='Enter')addCompany()">
        <button class="add-btn" onclick="addCompany()">添加</button>
      </div>
    </div>

    <div class="analysis-block">
      <div class="analysis-label">🏙 目标城市</div>
      <div class="analysis-row" id="cities_tags"></div>
      <div style="margin-top:6px">
        <input class="add-input" id="city_input" placeholder="添加城市" onkeydown="if(event.key==='Enter')addCity()">
        <button class="add-btn" onclick="addCity()">添加</button>
      </div>
    </div>

    <div class="analysis-block">
      <div class="analysis-label">🏭 目标行业</div>
      <div class="multi-select" id="industry_tags"></div>
    </div>

    <div class="analysis-block">
      <div class="analysis-label">🏢 偏好公司类型</div>
      <div class="multi-select" id="company_type_tags"></div>
    </div>

    <!-- AI 补充分析结果展示 -->
    <div id="supplement_result" class="analysis-block hidden" style="border-color:#3370ff;background:#f0f7ff">
      <div class="analysis-label" style="color:#3370ff">✨ AI 补充分析结果</div>
      <div id="supplement_dirs" style="margin-bottom:8px"></div>
      <div id="supplement_skills"></div>
      <p style="font-size:12px;color:#888;margin-top:8px">以上为 AI 根据你新增的方向补充的内容,可在下方技能区查看和修改。</p>
    </div>

    <button class="btn" id="supplement_btn" onclick="supplementProfile()" style="background:#6c5ce7;margin-bottom:10px">✨ AI 补充分析(扩展方向+技能)</button>
    <button class="btn" id="confirm_btn" onclick="confirmSetup()">生成我的岗位库</button>
    <div id="confirm-msg"></div>
  </div>

  <!-- Step 4: 完成 -->
  <div id="step-done" class="card hidden">
    <div class="section-title">🎉 配置完成!</div>
    <p>你的专属校招岗位库已创建(一个链接,内含多个页签:匹配岗位/已关闭/管培/简历/公司总表/岗位总表),每天自动更新(无需登录):</p>
    <div class="link-box" id="table_link"></div>
    <p style="font-size:13px;color:#888;margin-top:12px">
      每天早上 9 点,系统会自动把与你匹配的新岗位写入「我的匹配岗位」页签。<br>
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

// 数据存储
let profileData = {
  skills: [], directions: [], cities: [], companies: [], highlights: [],
  resume_text: '', summary: '', structured_keywords: [], fit_directions: [],
};

function parseResume() {
  const btn = document.querySelector('#step-resume .btn');
  const text = document.getElementById('resume_text').value;
  const files = document.getElementById('resume_file').files;
  if (!text && (!files || files.length === 0)) { showMsg('resume-msg', '请粘贴简历文本或上传简历文件', 'error'); return; }
  // 点击后立即灰掉,防止重复提交
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>AI 正在解析简历(约10-30秒)...';
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
        // 填充可编辑数据 + 简历解析留档数据
        profileData.skills = (p.core_skills || []).slice();
        // 方向优先用 fit_directions(结构化校验过的),降级用 direction_keywords
        if (p.fit_directions && p.fit_directions.length) {
          profileData.directions = p.fit_directions.map(d => d.direction).filter(Boolean);
        } else {
          profileData.directions = Object.keys(p.direction_keywords || {});
        }
        profileData.cities = (p.target_cities || []).slice();
        profileData.companies = (p.target_companies || []).slice();
        profileData.highlights = (p.highlights || []).slice();
        profileData.resume_text = p.resume_text || text || '';
        profileData.summary = p.summary || '';
        document.getElementById('profile_summary').value = profileData.summary;
        profileData.structured_keywords = p.structured_keywords || [];
        profileData.fit_directions = p.fit_directions || [];
        renderSkillTags();
        renderDirectionTags();
        renderCityTags();
        renderCompanyTags();
        renderHighlights();
        renderFitDirections();
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
    }).catch(() => {
      showMsg('resume-msg', '网络异常,简历解析失败', 'error');
      // 失败:2 分钟后可重试,期间显示倒计时
      let remain = 120;
      btn.innerHTML = '⏳ 解析失败, ' + remain + 's 后可重试';
      const timer = setInterval(() => {
        remain--;
        if (remain <= 0) {
          clearInterval(timer);
          btn.disabled = false;
          btn.innerHTML = 'AI 解析简历';
        } else {
          btn.innerHTML = '⏳ 解析失败, ' + remain + 's 后可重试';
        }
      }, 1000);
    });
}

// === 可编辑标签渲染 ===
// 用户编辑标记:当用户增删技能/方向/公司/城市/摘要时,重新启用 AI 补充按钮
function markEdited() {
  const btn = document.getElementById('supplement_btn');
  if (btn.disabled) {
    btn.disabled = false;
    btn.innerHTML = '✨ AI 补充分析(根据你的修改重新分析)';
    btn.style.opacity = '1';
    btn.style.cursor = 'pointer';
  }
}

function renderSkillTags() {
  const c = document.getElementById('skills_tags');
  c.innerHTML = profileData.skills.map((s,i) =>
    '<span class="skill-tag">' + s + '<span class="rm" onclick="removeSkill('+i+')">×</span></span>'
  ).join('');
}
function removeSkill(i) { profileData.skills.splice(i,1); renderSkillTags(); markEdited(); }
function addSkill() {
  const v = document.getElementById('skill_input').value.trim();
  if (v && !profileData.skills.includes(v)) { profileData.skills.push(v); renderSkillTags(); markEdited(); }
  document.getElementById('skill_input').value = '';
}

function renderDirectionTags() {
  const c = document.getElementById('directions_tags');
  c.innerHTML = profileData.directions.map((d,i) =>
    '<span class="skill-tag">' + d + '<span class="rm" onclick="removeDirection('+i+')">×</span></span>'
  ).join('');
}
function removeDirection(i) { profileData.directions.splice(i,1); renderDirectionTags(); markEdited(); }
function addDirection() {
  const v = document.getElementById('direction_input').value.trim();
  if (v && !profileData.directions.includes(v)) { profileData.directions.push(v); renderDirectionTags(); markEdited(); }
  document.getElementById('direction_input').value = '';
}

function renderCityTags() {
  const c = document.getElementById('cities_tags');
  c.innerHTML = profileData.cities.map((ct,i) =>
    '<span class="skill-tag">' + ct + '<span class="rm" onclick="removeCity('+i+')">×</span></span>'
  ).join('');
}
function removeCity(i) { profileData.cities.splice(i,1); renderCityTags(); markEdited(); }
function addCity() {
  const v = document.getElementById('city_input').value.trim();
  if (v && !profileData.cities.includes(v)) { profileData.cities.push(v); renderCityTags(); markEdited(); }
  document.getElementById('city_input').value = '';
}

function renderCompanyTags() {
  const c = document.getElementById('companies_tags');
  c.innerHTML = profileData.companies.map((ct,i) =>
    '<span class="skill-tag">' + ct + '<span class="rm" onclick="removeCompany('+i+')">×</span></span>'
  ).join('');
}
function removeCompany(i) { profileData.companies.splice(i,1); renderCompanyTags(); markEdited(); }
function addCompany() {
  const v = document.getElementById('company_input').value.trim();
  if (v && !profileData.companies.includes(v)) { profileData.companies.push(v); renderCompanyTags(); markEdited(); }
  document.getElementById('company_input').value = '';
}

// === AI 补充分析(第二轮) ===
function supplementProfile() {
  if (!profileData.directions.length) {
    alert('请先添加至少一个目标方向');
    return;
  }
  const btn = document.getElementById('supplement_btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>AI 正在分析(约10-20秒)...';

  // 用用户编辑后的摘要作为 AI 理解背景的上下文
  const editedSummary = document.getElementById('profile_summary').value || profileData.summary;
  // 收集用户所有编辑(方向/技能/公司/城市),让 AI 基于完整修改做补充分析
  const industries = getSelectedTags('industry_tags');
  const companyTypes = getSelectedTags('company_type_tags');
  const userEdited = {
    directions: profileData.directions,
    fit_directions: profileData.fit_directions,
    structured_keywords: profileData.structured_keywords,
    skills: profileData.skills,
    companies: profileData.companies,
    cities: profileData.cities,
    target_industries: industries,
    preferred_company_types: companyTypes,
  };

  fetch('/api/supplement-profile', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({profile: userEdited, resume_text: editedSummary})
  }).then(r => r.json()).then(data => {
    if (data.fit_directions) {
      profileData.fit_directions = data.fit_directions;
      profileData.structured_keywords = data.structured_keywords;
      profileData.directions = data.fit_directions.map(d => d.direction).filter(Boolean);
      renderDirectionTags();
      renderFitDirections();

      // 展示 AI 补充的新方向和新技能
      const newDirs = data.new_directions || [];
      const newSkills = data.new_skills || [];
      let dirsHtml = '<div style="font-size:13px;color:#3370ff;margin-bottom:4px">📌 新增/扩展方向:</div>';
      if (newDirs.length) {
        dirsHtml += newDirs.map(d =>
          '<span class="skill-tag" style="background:#e8e4ff">' + d.direction +
          ' <span style="color:#888;font-size:11px">(' + (d.weight||0).toFixed(1) + ')</span></span>'
        ).join(' ');
      } else {
        dirsHtml += '<span style="color:#888;font-size:12px">方向已覆盖,无新增</span>';
      }
      document.getElementById('supplement_dirs').innerHTML = dirsHtml;

      let skillsHtml = '<div style="font-size:13px;color:#3370ff;margin-bottom:4px">🛠 补充技能:</div>';
      if (newSkills.length) {
        skillsHtml += newSkills.map(s =>
          '<span class="skill-tag" style="background:#e8e4ff">' + s.kw + '</span>'
        ).join(' ');
      } else {
        skillsHtml += '<span style="color:#888;font-size:12px">技能已覆盖,无新增</span>';
      }
      document.getElementById('supplement_skills').innerHTML = skillsHtml;
      document.getElementById('supplement_result').classList.remove('hidden');

      // 同步技能到可编辑区(把补充的硬技能加入 skills 列表)
      newSkills.forEach(s => {
        if (s.kw && !profileData.skills.includes(s.kw)) {
          profileData.skills.push(s.kw);
        }
      });
      renderSkillTags();

      showMsg('confirm-msg', '✅ AI 补充完成,你可以继续修改,满意后点击「生成我的岗位库」', 'success');
      // 补充成功后按钮保持禁用(一轮流程只补充一次),但用户再次编辑时会自动重新启用
      btn.disabled = true;
      btn.innerHTML = '✅ 已完成 AI 补充(修改内容后可再次分析)';
      btn.style.opacity = '0.6';
      btn.style.cursor = 'not-allowed';
    } else {
      showMsg('confirm-msg', data.error || 'AI 补充失败', 'error');
      btn.disabled = false;
      btn.innerHTML = '✨ AI 补充分析(根据你的修改重新分析)';
    }
  }).catch(() => {
    showMsg('confirm-msg', '网络异常,请重试', 'error');
    btn.disabled = false;
    btn.innerHTML = '✨ AI 补充分析(扩展方向+技能)';
  });
}

function renderHighlights() {
  const c = document.getElementById('highlights_list');
  if (!profileData.highlights.length) { c.innerHTML = '<div style="font-size:13px;color:#aaa">暂无亮点</div>'; return; }
  c.innerHTML = profileData.highlights.map(h => '<div class="highlight-item">' + h + '</div>').join('');
}

function renderFitDirections() {
  const c = document.getElementById('fit_directions_list');
  const dirs = profileData.fit_directions || [];
  if (!dirs.length) {
    c.innerHTML = '<div style="font-size:13px;color:#aaa">暂无方向分析,请在下方添加目标方向</div>';
    return;
  }
  c.innerHTML = dirs.map(d => {
    const w = (d.weight || 0).toFixed(1);
    const pct = Math.round((d.weight || 0) * 100);
    const evidence = (d.evidence || '').replace(/"/g, '&quot;');
    return '<div style="margin-bottom:10px;padding:10px;background:#f8f9ff;border-radius:8px">' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">' +
      '<span style="font-size:14px;font-weight:600;color:#3370ff">' + (d.direction || '') + '</span>' +
      '<span style="font-size:12px;color:#888">适配度 ' + pct + '%</span>' +
      '</div>' +
      '<div style="height:4px;background:#e8eaf0;border-radius:2px;overflow:hidden;margin-bottom:4px">' +
      '<div style="height:100%;width:' + pct + '%;background:#3370ff;border-radius:2px"></div>' +
      '</div>' +
      '<div style="font-size:12px;color:#666">' + (evidence || 'AI 推断,建议确认') + '</div>' +
      '</div>';
  }).join('');
}

function renderTags(containerId, options, selected) {
  const c = document.getElementById(containerId);
  c.innerHTML = '';
  options.forEach(opt => {
    const chip = document.createElement('div');
    chip.className = 'chip' + (selected.includes(opt) ? ' active' : '');
    chip.textContent = opt;
    chip.onclick = () => { chip.classList.toggle('active'); markEdited(); };
    c.appendChild(chip);
  });
}

function getSelectedTags(containerId) {
  return Array.from(document.getElementById(containerId).querySelectorAll('.chip.active'))
    .map(c => c.textContent);
}

function confirmSetup() {
  const btn = document.getElementById('confirm_btn');
  if (btn.disabled) return;
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>正在创建岗位库(约1-2分钟)...';
  const industries = getSelectedTags('industry_tags');
  const companyTypes = getSelectedTags('company_type_tags');
  const dirKw = {};
  profileData.directions.forEach(d => { if (d) dirKw[d] = [d]; });
  const profile = {
    role: 'campus',
    school: document.getElementById('school').value,
    degree: document.getElementById('degree').value,
    major: document.getElementById('major').value,
    graduation_year: document.getElementById('graduation_year').value,
    target_cities: profileData.cities,
    target_companies: profileData.companies,
    target_industries: industries,
    preferred_company_types: companyTypes,
    direction_keywords: dirKw,
    core_skills: profileData.skills,
    // 简历解析留档数据(用户最终确认版)
    resume_text: profileData.resume_text,
    summary: document.getElementById('profile_summary').value || profileData.summary,
    highlights: profileData.highlights,
    structured_keywords: profileData.structured_keywords,
    fit_directions: profileData.fit_directions,
  };
  showMsg('confirm-msg', '', '');
  fetch('/api/confirm-setup', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({order_id: currentOrderId, profile})
  }).then(r => r.json()).then(data => {
    if (data.share_url) {
      document.getElementById('step-profile').classList.add('hidden');
      document.getElementById('step-done').classList.remove('hidden');
      // 所有表在同一个多维表格(base)内,只需一个链接,用户在飞书内切换页签
      let html = '<div style="margin:8px 0"><a href="' + data.share_url + '" target="_blank" style="font-size:16px;font-weight:600">📋 打开我的校招岗位库(点击进入)</a></div>';
      html += '<div style="font-size:12px;color:#888;margin-top:6px">内含页签:我的匹配岗位 | 已关闭岗位 | 管培项目 | 简历解析数据 | 秋招公司总表 | 校招岗位总表</div>';
      if (data.master_warning) {
        html += '<div style="margin-top:12px;padding:10px;background:#fff7e6;border:1px solid #ffd591;border-radius:6px;color:#ad6800;font-size:13px">⚠️ ' + data.master_warning + '</div>';
      }
      html += '<div style="margin-top:12px;font-size:13px;color:#888">岗位匹配正在后台进行,通常 1-3 分钟后可在「我的匹配岗位」页签中查看结果。</div>';
      document.getElementById('table_link').innerHTML = html;
    } else {
      showMsg('confirm-msg', data.msg || '创建失败,请重试', 'error');
      btn.disabled = false;
      btn.innerHTML = '生成我的岗位库';
    }
  }).catch(() => {
    showMsg('confirm-msg', '网络异常,请重试', 'error');
    btn.disabled = false;
    btn.innerHTML = '生成我的岗位库';
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
        # 第一轮:生成结构化关键词 + 适配方向(供匹配引擎使用)
        parse_result = resume_parser.parse_resume_text(resume_text, llm_client=llm_client)
        profile["structured_keywords"] = parse_result.get("keywords", [])
        profile["fit_directions"] = parse_result.get("fit_directions", [])
        # 带回原始简历文本(含 OCR 结果),供 confirm-setup 留档
        profile["resume_text"] = resume_text
        return jsonify({"profile": profile})
    except Exception as e:
        logger.error(f"简历解析失败: {e}")
        return jsonify({"error": "简历解析失败,请稍后重试"}), 500


@app.route("/api/supplement-profile", methods=["POST"])
def api_supplement_profile():
    """第二轮:用户编辑后,AI 补充分析(扩展用户新增方向 + 补充硬技能)。

    输入:用户编辑后的画像(directions/fit_directions/structured_keywords) + resume_text
    输出:补充后的 fit_directions + structured_keywords
    """
    data = request.get_json() or {}
    user_edited = data.get("profile", {}) or {}
    resume_text = data.get("resume_text", "")

    if not user_edited.get("directions"):
        return jsonify({"error": "请先添加目标方向"}), 400

    try:
        result = resume_parser.supplement_profile(
            user_edited=user_edited,
            resume_text=resume_text,
            llm_client=llm_client,
        )
        return jsonify({
            "fit_directions": result["fit_directions"],
            "structured_keywords": result["structured_keywords"],
            "new_directions": result["new_directions"],
            "new_skills": result["new_skills"],
        })
    except Exception as e:
        logger.error(f"画像补充失败: {e}")
        return jsonify({"error": "AI 补充失败,请稍后重试"}), 500


@app.route("/api/confirm-setup", methods=["POST"])
def api_confirm_setup():
    """确认配置 → 创建/更新用户 + 飞书表格 → 写入简历快照 → 返回链接。

    支持同一订单多次解析:
    - 首次确认:创建用户 + 多维表格 + 写简历快照 v1 + 触发即时匹配
    - 再次确认:复用已有表格,更新画像,写简历快照 v{n+1},触发重新匹配
    """
    data = request.get_json() or {}
    order_id = data.get("order_id", "").strip()
    profile_data = data.get("profile", {})

    # 1. 验证订单
    order_info = _validate_order(order_id)
    if not order_info:
        return jsonify({"error": "订单号无效"}), 400

    # 2. 查找/创建用户
    user_id = f"xhs_{order_id}"
    user = user_store.get(user_id)
    is_new_user = user is None
    if is_new_user:
        plan = order_info.get("plan", "autumn")
        expire_days = order_info.get("expire_days", 90)
        expire_ts = time.time() + expire_days * 86400
        expire_date = time.strftime("%Y-%m-%d", time.localtime(expire_ts))
        user = User(id=user_id, order_id=order_id, plan=plan, expire_date=expire_date)

    # 3. 设置画像(含简历解析数据:resume_text/summary/highlights/structured_keywords/fit_directions)
    filtered = {k: v for k, v in profile_data.items()
                if k in UserProfile.__dataclass_fields__}
    user.profile = UserProfile(**filtered)
    user.profile.role = "campus"  # 强制校招

    # 归一化目标行业/公司类型到 mappings.json 标准分类名
    # (兜底:前端选项已来自标准分类,但防止测试/旧数据传入非标准值导致 DB 匹配失败)
    import normalizer as _norm
    if user.profile.target_industries:
        user.profile.target_industries = [
            _norm.normalize_industry(x) for x in user.profile.target_industries
        ]
    if user.profile.preferred_company_types:
        user.profile.preferred_company_types = [
            _norm.normalize_company_type(x) for x in user.profile.preferred_company_types
        ]

    # 归一化 structured_keywords:前端可能传 dict 列表,需转 KeywordTag
    sk = filtered.get("structured_keywords") or []
    if sk and isinstance(sk[0], dict):
        from models import KeywordTag
        user.profile.structured_keywords = [
            KeywordTag(
                kw=d.get("kw", ""),
                standard=d.get("standard", d.get("kw", "")),
                category=d.get("category", "other"),
                weight=d.get("weight", 1.0),
            ) for d in sk
        ]

    # 4. 创建或复用飞书表格
    if is_new_user or not user.feishu_base_token:
        # 新建多维表格(以订单 ID 命名)
        try:
            table_result = table_service.create_user_bitable(
                order_id=order_id,
                user_display_name=profile_data.get("school", "校招用户"),
            )
            user.feishu_base_token = table_result["app_token"]
            user.feishu_table_id = table_result["jobs_table_id"]
            user.feishu_closed_table_id = table_result["closed_table_id"]
            user.feishu_mt_table_id = table_result["mt_table_id"]
            user.feishu_resume_table_id = table_result["resume_table_id"]
            user.feishu_company_table_id = table_result["company_table_id"]
            user.feishu_position_table_id = table_result["position_table_id"]
            share_url = table_result["share_url"]
        except Exception as e:
            logger.error(f"飞书表格创建失败: {e}")
            return jsonify({"error": "岗位库创建失败,请稍后重试"}), 500
    else:
        # 复用已有表格(避免孤儿表)
        share_url = table_service.client.get_share_url(user.feishu_base_token)

    # 5. 简历版本号 +1,写入简历解析数据快照
    user.resume_parse_count += 1
    if user.feishu_resume_table_id:
        table_service.write_resume_snapshot(
            user.feishu_base_token, user.feishu_resume_table_id,
            user.profile, version=user.resume_parse_count,
        )

    # 6. 保存用户
    user_store.upsert(user)
    logger.info(
        f"用户配置完成(新用户={is_new_user}, 简历版本=v{user.resume_parse_count}): "
        f"{user_id} -> {share_url}"
    )

    # 7. 后台触发即时匹配 + 总表数据同步(用户立即可见数据,不等次日 cron)
    try:
        from daily_runner import DailyRunner
        runner = DailyRunner(user)
        import threading

        def _bg_work():
            # 先同步公司/岗位总库到用户表格(单链接多页签)
            try:
                table_service.sync_master_tables_to_user(
                    user.feishu_base_token,
                    user.feishu_company_table_id,
                    user.feishu_position_table_id,
                )
            except Exception as e:
                logger.warning(f"用户总表同步失败(将由次日 cron 补跑): {e}")
            # 再跑岗位匹配
            try:
                runner.run()
            except Exception as e:
                logger.warning(f"即时匹配触发失败(将由次日 cron 补跑): {e}")

        t = threading.Thread(target=_bg_work, daemon=True)
        t.start()
        logger.info(f"已触发即时匹配 + 总表同步: {user_id}")
    except Exception as e:
        logger.warning(f"后台任务触发失败(将由次日 cron 补跑): {e}")

    # 8. 返回链接(用户表 + 简历表 + 公司总表 + 岗位总表)
    from config import settings
    master_base = settings.MASTER_APP_TOKEN
    master_verified = table_service.verify_master_tables(
        master_base,
        settings.MASTER_COMPANY_TABLE_ID,
        settings.MASTER_POSITION_TABLE_ID,
    )
    company_table_url = (
        f"https://www.feishu.cn/base/{master_base}?table={master_verified['company_table_id']}"
        if master_verified["company_table_id"] else ""
    )
    position_table_url = (
        f"https://www.feishu.cn/base/{master_base}?table={master_verified['position_table_id']}"
        if master_verified["position_table_id"] else ""
    )
    resume_table_url = (
        f"https://www.feishu.cn/base/{user.feishu_base_token}?table={user.feishu_resume_table_id}"
        if user.feishu_resume_table_id else ""
    )

    resp = {
        "share_url": share_url,
        "user_table_url": share_url,
        "resume_table_url": resume_table_url,
        "company_table_url": company_table_url,
        "position_table_url": position_table_url,
        "is_new_user": is_new_user,
        "resume_version": f"v{user.resume_parse_count}",
    }
    if not master_verified["ok"]:
        logger.warning(
            f"总表校验失败: company={master_verified['company_table_id']!r}, "
            f"position={master_verified['position_table_id']!r} (配置 ID 可能已过期)"
        )
        resp["master_warning"] = "公司/岗位总表暂不可用,请联系管理员"
    return jsonify(resp)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=5000, debug=False)
