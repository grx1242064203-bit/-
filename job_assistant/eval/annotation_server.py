"""
评测集标注工具 — 本地 Web 界面。

启动后用浏览器访问 http://localhost:8765
- 左侧：公告原文 + LLM 拆岗结果
- 右侧：标注表单
- 自动保存到 evalset_positions_slim.json
- 支持上一条/下一条切换
- 进度统计

用法:
    cd /workspace/job_assistant
    python3 eval/annotation_server.py
    # 浏览器打开 http://localhost:8765
"""
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parent.parent
EVALSET_PATH = ROOT / "eval" / "evalset_positions.json"

PORT = 8765


def load_evalset():
    with open(EVALSET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_evalset(data):
    with open(EVALSET_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>拆岗评测集标注工具</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #0f172a; color: #e2e8f0; }
.header { background: #1e293b; padding: 16px 24px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 10; }
.header h1 { font-size: 18px; color: #f97316; }
.progress { font-size: 14px; color: #94a3b8; }
.progress .done { color: #22c55e; font-weight: 600; }
.progress .total { color: #e2e8f0; }
.container { display: flex; gap: 1px; background: #334155; min-height: calc(100vh - 57px); }
.panel { flex: 1; background: #0f172a; padding: 20px; overflow-y: auto; }
.panel-left { flex: 1.2; }
.panel-right { flex: 1; }
.panel-title { font-size: 14px; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #334155; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; margin-left: 8px; }
.badge-A { background: #1e3a5f; color: #60a5fa; }
.badge-B { background: #1e3f2e; color: #4ade80; }
.badge-C { background: #3f2e1e; color: #fb923c; }
.badge-D { background: #3f1e1e; color: #f87171; }
.badge-E { background: #2e1e3f; color: #c084fc; }
.meta-row { display: flex; gap: 16px; margin-bottom: 8px; font-size: 13px; }
.meta-label { color: #64748b; min-width: 80px; }
.meta-value { color: #e2e8f0; }
.content-box { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 14px; font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; max-height: 400px; overflow-y: auto; margin-bottom: 16px; }
.position-list { list-style: none; }
.position-item { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; font-size: 13px; }
.position-item .title { color: #f97316; font-weight: 600; }
.position-item .cat { color: #64748b; font-size: 12px; margin-left: 8px; }
.form-group { margin-bottom: 16px; }
.form-label { display: block; font-size: 13px; color: #cbd5e1; margin-bottom: 6px; font-weight: 600; }
.form-label .hint { color: #64748b; font-weight: 400; font-size: 12px; }
.form-input, .form-select, .form-textarea { width: 100%; background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 8px 10px; color: #e2e8f0; font-size: 14px; font-family: inherit; }
.form-input:focus, .form-select:focus, .form-textarea:focus { outline: none; border-color: #f97316; }
.form-textarea { min-height: 60px; resize: vertical; line-height: 1.5; }
.form-row { display: flex; gap: 12px; }
.form-row .form-group { flex: 1; }
.score-group { display: flex; gap: 8px; }
.score-btn { flex: 1; padding: 8px; background: #1e293b; border: 1px solid #334155; border-radius: 6px; color: #94a3b8; cursor: pointer; font-size: 14px; text-align: center; transition: all 0.15s; }
.score-btn:hover { border-color: #475569; color: #e2e8f0; }
.score-btn.active { background: #f97316; border-color: #f97316; color: #fff; }
.score-btn.active.s1 { background: #ef4444; border-color: #ef4444; }
.score-btn.active.s2 { background: #f97316; border-color: #f97316; }
.score-btn.active.s3 { background: #eab308; border-color: #eab308; }
.score-btn.active.s4 { background: #84cc16; border-color: #84cc16; }
.score-btn.active.s5 { background: #22c55e; border-color: #22c55e; }
.nav { display: flex; gap: 12px; margin-top: 24px; padding-top: 16px; border-top: 1px solid #334155; }
.nav-btn { padding: 10px 20px; background: #334155; border: 1px solid #475569; border-radius: 6px; color: #e2e8f0; cursor: pointer; font-size: 14px; }
.nav-btn:hover { background: #475569; }
.nav-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.nav-btn.save { background: #16a34a; border-color: #16a34a; }
.nav-btn.save:hover { background: #15803d; }
.save-status { font-size: 12px; color: #22c55e; margin-left: 12px; opacity: 0; transition: opacity 0.3s; }
.save-status.show { opacity: 1; }
.tag-list { display: flex; flex-wrap: wrap; gap: 4px; }
.tag { background: #1e293b; border: 1px solid #334155; border-radius: 4px; padding: 2px 8px; font-size: 12px; color: #94a3b8; }
.tag.remove { cursor: pointer; }
.tag.remove:hover { background: #3f1e1e; border-color: #f87171; color: #f87171; }
.add-tag { display: flex; gap: 6px; margin-top: 6px; }
.add-tag input { flex: 1; }
.add-tag button { padding: 4px 10px; background: #334155; border: 1px solid #475569; border-radius: 4px; color: #e2e8f0; cursor: pointer; font-size: 12px; }
.position-item-full { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 12px; margin-bottom: 12px; }
.pos-header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid #334155; }
.pos-num { background: #f97316; color: #fff; border-radius: 50%; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; }
.pos-title { color: #f97316; font-weight: 600; font-size: 14px; }
.pos-tag { background: #1e3f2e; color: #4ade80; padding: 1px 6px; border-radius: 3px; font-size: 11px; }
.pos-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 12px; margin-bottom: 8px; }
.pos-field { display: flex; flex-direction: column; gap: 1px; }
.pos-field-full { display: flex; gap: 8px; margin-top: 4px; }
.pf-label { font-size: 11px; color: #64748b; min-width: 60px; }
.pf-val { font-size: 13px; color: #e2e8f0; line-height: 1.4; }
.empty-state { text-align: center; padding: 60px 20px; color: #64748b; }
</style>
</head>
<body>

<div class="header">
    <h1>拆岗评测集标注</h1>
    <div class="progress">
        已标注 <span class="done" id="doneCount">0</span> / <span class="total" id="totalCount">0</span>
    </div>
</div>

<div class="container">
    <div class="panel panel-left">
        <div class="panel-title">公告信息 + LLM 拆岗结果</div>
        <div id="leftContent"><div class="empty-state">加载中...</div></div>
    </div>
    <div class="panel panel-right">
        <div class="panel-title">标注表单</div>
        <div id="rightContent"><div class="empty-state">加载中...</div></div>
    </div>
</div>

<script>
let evalData = [];
let currentIndex = 0;

async function loadData() {
    const resp = await fetch('/api/data');
    evalData = await resp.json();
    if (evalData.length > 0) {
        render();
    }
}

function updateProgress() {
    const done = evalData.filter(i => i.annotation && i.annotation.correct_position_count !== null).length;
    document.getElementById('doneCount').textContent = done;
    document.getElementById('totalCount').textContent = evalData.length;
}

function render() {
    const item = evalData[currentIndex];
    if (!item) return;

    // 左侧：公告信息 + LLM完整输出
    const bucketClass = 'badge-' + item.bucket.charAt(0);
    let positionsHtml = '';
    if (item.llm_positions && item.llm_positions.length > 0) {
        positionsHtml = '<div class="position-list">';
        item.llm_positions.forEach((pos, i) => {
            const hardSkills = (pos.hard_skills || []).join(', ');
            const softSkills = (pos.soft_skills || []).join(', ');
            const keywords = (pos.keywords || []).join(', ');
            const certs = (pos.certifications || []).join(', ');
            const langs = (pos.languages || []).join(', ');
            positionsHtml += `<div class="position-item-full">
                <div class="pos-header">
                    <span class="pos-num">${i + 1}</span>
                    <span class="pos-title">${escapeHtml(pos.position_title || '')}</span>
                    ${pos.is_management_trainee ? '<span class="pos-tag">管培</span>' : ''}
                </div>
                <div class="pos-grid">
                    <div class="pos-field"><span class="pf-label">大类</span><span class="pf-val">${escapeHtml(pos.job_category || '')}</span></div>
                    <div class="pos-field"><span class="pf-label">子类</span><span class="pf-val">${escapeHtml(pos.job_subcategory || '')}</span></div>
                    <div class="pos-field"><span class="pf-label">学历</span><span class="pf-val">${escapeHtml(pos.min_education || '')}</span></div>
                    <div class="pos-field"><span class="pf-label">城市</span><span class="pf-val">${escapeHtml(pos.city || '')}</span></div>
                    <div class="pos-field"><span class="pf-label">专业要求</span><span class="pf-val">${escapeHtml(pos.major_required || '')}</span></div>
                    <div class="pos-field"><span class="pf-label">专业大类</span><span class="pf-val">${escapeHtml(pos.major_category || '')}</span></div>
                    <div class="pos-field"><span class="pf-label">硬技能</span><span class="pf-val">${escapeHtml(hardSkills)}</span></div>
                    <div class="pos-field"><span class="pf-label">软技能</span><span class="pf-val">${escapeHtml(softSkills)}</span></div>
                    <div class="pos-field"><span class="pf-label">证书</span><span class="pf-val">${escapeHtml(certs)}</span></div>
                    <div class="pos-field"><span class="pf-label">语言</span><span class="pf-val">${escapeHtml(langs)}</span></div>
                    <div class="pos-field"><span class="pf-label">难度</span><span class="pf-val">${escapeHtml(pos.difficulty || '')}</span></div>
                    <div class="pos-field"><span class="pf-label">公司档位</span><span class="pf-val">${escapeHtml(pos.company_tier || '')}</span></div>
                    <div class="pos-field"><span class="pf-label">关键词</span><span class="pf-val">${escapeHtml(keywords)}</span></div>
                </div>
                <div class="pos-field-full"><span class="pf-label">职责</span><span class="pf-val">${escapeHtml(pos.responsibilities || '')}</span></div>
                <div class="pos-field-full"><span class="pf-label">要求</span><span class="pf-val">${escapeHtml(pos.requirements || '')}</span></div>
                <div class="pos-field-full"><span class="pf-label">加分项</span><span class="pf-val">${escapeHtml(pos.bonus_points || '')}</span></div>
                <div class="pos-field-full"><span class="pf-label">摘要</span><span class="pf-val">${escapeHtml(pos.jd_summary || '')}</span></div>
            </div>`;
        });
        positionsHtml += '</div>';
    }

    document.getElementById('leftContent').innerHTML = `
        <div class="meta-row">
            <span class="meta-label">ID:</span>
            <span class="meta-value">${item.id}</span>
            <span class="badge ${bucketClass}">${item.bucket}</span>
        </div>
        <div class="meta-row">
            <span class="meta-label">LLM拆出:</span>
            <span class="meta-value">${item.llm_position_count} 个岗位</span>
        </div>
        <div class="panel-title" style="margin-top:16px">公告原文</div>
        <div class="content-box">${escapeHtml(item.crawl_content_excerpt || '[无正文]')}</div>
        <div class="panel-title">LLM 拆岗结果 (${item.llm_position_count}个 · 完整字段)</div>
        ${positionsHtml}
    `;

    // 右侧：标注表单
    const ann = item.annotation || {};
    const score = ann.overall_score || 0;

    document.getElementById('rightContent').innerHTML = `
        <div class="form-group">
            <label class="form-label">实际岗位数量 <span class="hint">（公告里实际有几个可独立投递的岗位）</span></label>
            <input type="number" class="form-input" id="correctCount" value="${ann.correct_position_count ?? ''}" min="0">
        </div>

        <div class="form-group">
            <label class="form-label">拆岗判定</label>
            <select class="form-select" id="splitVerdict">
                <option value="">请选择</option>
                <option value="correct" ${ann.split_verdict === 'correct' ? 'selected' : ''}>✓ 拆对了</option>
                <option value="under_split" ${ann.split_verdict === 'under_split' ? 'selected' : ''}>⚠ 漏拆了</option>
                <option value="over_split" ${ann.split_verdict === 'over_split' ? 'selected' : ''}>⚠ 拆多了</option>
            </select>
        </div>

        <div class="form-group">
            <label class="form-label">漏拆的岗位名 <span class="hint">（应拆但没拆的，逗号分隔）</span></label>
            <textarea class="form-textarea" id="missedPositions" placeholder="如：模拟设计,数字设计,数字验证">${(ann.missed_positions || []).join(', ')}</textarea>
        </div>

        <div class="form-group">
            <label class="form-label">误拆/幻觉岗位 <span class="hint">（拆了但公告里不存在的，逗号分隔）</span></label>
            <textarea class="form-textarea" id="hallucinatedPositions" placeholder="如：虚构岗位名">${(ann.hallucinated_positions || []).join(', ')}</textarea>
        </div>

        <div class="form-group">
            <label class="form-label">归类错误 <span class="hint">（job_category/job_subcategory 填错的）</span></label>
            <textarea class="form-textarea" id="categoryErrors" placeholder="如：产品工程师|大类应为:研发|实际填:产品">${(ann.category_errors || []).map(e => typeof e === 'string' ? e : JSON.stringify(e)).join('\n')}</textarea>
        </div>

        <div class="form-group">
            <label class="form-label">字段错误 <span class="hint">（city/major/education等填错的）</span></label>
            <textarea class="form-textarea" id="fieldErrors" placeholder="如：产品工程师|学历应为:硕士|实际填:本科">${(ann.field_errors || []).map(e => typeof e === 'string' ? e : JSON.stringify(e)).join('\n')}</textarea>
        </div>

        <div class="form-group">
            <label class="form-label">整体评分</label>
            <div class="score-group">
                ${[1,2,3,4,5].map(s => `<div class="score-btn s${s} ${score === s ? 'active' : ''}" data-score="${s}">${s}</div>`).join('')}
            </div>
        </div>

        <div class="form-group">
            <label class="form-label">Bad Case 类型</label>
            <select class="form-select" id="badCaseType">
                <option value="">请选择</option>
                <option value="none" ${ann.bad_case_type === 'none' ? 'selected' : ''}>无问题</option>
                <option value="missed" ${ann.bad_case_type === 'missed' ? 'selected' : ''}>漏拆</option>
                <option value="hallucinated" ${ann.bad_case_type === 'hallucinated' ? 'selected' : ''}>幻觉/误拆</option>
                <option value="wrong_category" ${ann.bad_case_type === 'wrong_category' ? 'selected' : ''}>归类错误</option>
                <option value="wrong_field" ${ann.bad_case_type === 'wrong_field' ? 'selected' : ''}>字段错误</option>
            </select>
        </div>

        <div class="form-group">
            <label class="form-label">备注 <span class="hint">（根因分析等）</span></label>
            <textarea class="form-textarea" id="notes" placeholder="如：标题多岗位无分隔符，LLM只取最后一个">${escapeHtml(ann.notes || '')}</textarea>
        </div>

        <div class="nav">
            <button class="nav-btn" id="prevBtn" ${currentIndex === 0 ? 'disabled' : ''}>← 上一条</button>
            <button class="nav-btn save" id="saveBtn">保存</button>
            <button class="nav-btn" id="nextBtn" ${currentIndex === evalData.length - 1 ? 'disabled' : ''}>下一条 →</button>
            <span class="save-status" id="saveStatus">已保存 ✓</span>
        </div>
    `;

    // 绑定事件
    document.querySelectorAll('.score-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.score-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });

    document.getElementById('prevBtn').addEventListener('click', () => {
        saveCurrent();
        if (currentIndex > 0) { currentIndex--; render(); }
    });
    document.getElementById('nextBtn').addEventListener('click', () => {
        saveCurrent();
        if (currentIndex < evalData.length - 1) { currentIndex++; render(); }
    });
    document.getElementById('saveBtn').addEventListener('click', () => saveCurrent(true));

    // 自动保存：失焦时
    document.querySelectorAll('.form-input, .form-select, .form-textarea').forEach(el => {
        el.addEventListener('blur', () => saveCurrent());
    });
}

function saveCurrent(showStatus = false) {
    const item = evalData[currentIndex];
    if (!item) return;

    const correctCount = parseInt(document.getElementById('correctCount').value) || null;
    const splitVerdict = document.getElementById('splitVerdict').value;
    const missed = document.getElementById('missedPositions').value.split(/[,，]/).map(s => s.trim()).filter(s => s);
    const hallucinated = document.getElementById('hallucinatedPositions').value.split(/[,，]/).map(s => s.trim()).filter(s => s);
    const catErrorsRaw = document.getElementById('categoryErrors').value.trim();
    const fieldErrorsRaw = document.getElementById('fieldErrors').value.trim();
    const activeScore = document.querySelector('.score-btn.active');
    const score = activeScore ? parseInt(activeScore.dataset.score) : null;
    const badCaseType = document.getElementById('badCaseType').value;
    const notes = document.getElementById('notes').value;

    item.annotation = {
        correct_position_count: correctCount,
        split_verdict: splitVerdict || null,
        missed_positions: missed,
        hallucinated_positions: hallucinated,
        category_errors: catErrorsRaw ? catErrorsRaw.split('\n').map(s => s.trim()).filter(s => s) : [],
        field_errors: fieldErrorsRaw ? fieldErrorsRaw.split('\n').map(s => s.trim()).filter(s => s) : [],
        overall_score: score,
        bad_case_type: badCaseType || null,
        notes: notes,
    };

    // 发送到服务端保存
    fetch('/api/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({index: currentIndex, annotation: item.annotation}),
    }).then(() => {
        updateProgress();
        if (showStatus) {
            const status = document.getElementById('saveStatus');
            status.classList.add('show');
            setTimeout(() => status.classList.remove('show'), 2000);
        }
    });
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

loadData();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/data":
            data = load_evalset()
            self.send_json(data)
        elif self.path == "/" or self.path == "":
            self.send_html(HTML_TEMPLATE)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/save":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body)
            idx = payload["index"]
            annotation = payload["annotation"]

            data = load_evalset()
            if 0 <= idx < len(data):
                data[idx]["annotation"] = annotation
                save_evalset(data)
                self.send_json({"ok": True, "index": idx})
            else:
                self.send_json({"ok": False, "error": "index out of range"}, 400)
        else:
            self.send_error(404)

    def send_json(self, obj, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def send_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # 静默日志


def main():
    data = load_evalset()
    done = sum(1 for i in data if i.get("annotation", {}).get("correct_position_count") is not None)
    print(f"\n{'='*50}")
    print(f"  拆岗评测集标注工具")
    print(f"{'='*50}")
    print(f"  评测集: {EVALSET_PATH}")
    print(f"  总样本: {len(data)} 条")
    print(f"  已标注: {done} 条")
    print(f"{'='*50}")
    print(f"\n  浏览器打开: http://localhost:{PORT}\n")
    print(f"  操作说明:")
    print(f"    - 左侧看公告原文和LLM拆岗结果")
    print(f"    - 右侧填标注表单")
    print(f"    - 切换或失焦自动保存")
    print(f"    - 也可点[保存]按钮手动保存")
    print(f"\n  Ctrl+C 退出\n")

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
        save_evalset(load_evalset())  # 确保最后保存


if __name__ == "__main__":
    main()
