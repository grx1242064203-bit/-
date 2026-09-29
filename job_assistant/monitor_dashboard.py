"""实时监控看板 — Flask 服务, 每分钟刷新"""
import json, time, sqlite3, os
from flask import Flask, jsonify, render_template_string

DB = os.path.join(os.path.dirname(__file__), "data", "job_assistant.db")
app = Flask(__name__)

HTML = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>校园招聘助理 · 实时监控</title>
<meta http-equiv="refresh" content="10">
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 20px; }
h1 { color: #38bdf8; margin: 0 0 20px; }
h2 { color: #94a3b8; font-size: 14px; margin: 30px 0 10px; text-transform: uppercase; letter-spacing: 2px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.card { background: #1e293b; border-radius: 10px; padding: 16px; }
.card .label { font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 1px; }
.card .value { font-size: 32px; font-weight: 700; margin-top: 4px; }
.card.green .value { color: #4ade80; }
.card.blue .value { color: #38bdf8; }
.card.yellow .value { color: #facc15; }
.card.orange .value { color: #fb923c; }
.card.red .value { color: #f87171; }
.progress { background: #334155; border-radius: 10px; height: 24px; overflow: hidden; }
.progress-bar { height: 100%; background: linear-gradient(90deg, #38bdf8, #6366f1); transition: width 0.5s; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; }
table { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 10px; overflow: hidden; }
th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #334155; font-size: 13px; }
th { background: #334155; color: #94a3b8; font-weight: 500; }
tr:hover { background: #334155; }
.badge { padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; }
.badge.success { background: #065f46; color: #4ade80; }
.badge.skipped { background: #78350f; color: #fbbf24; }
.badge.failed { background: #7f1d1d; color: #f87171; }
.badge.pending { background: #1e3a8a; color: #93c5fd; }
.badge.vl_failed { background: #7c2d12; color: #fdba74; }
footer { margin-top: 30px; color: #475569; font-size: 12px; }
</style>
</head>
<body>
<h1>🔍 校园招聘助理 · 实时监控看板</h1>

<h2>整体进度</h2>
<div class="grid">
  <div class="card blue"><div class="label">已抓取成功</div><div class="value">{{ data.crawled }}</div></div>
  <div class="card green"><div class="label">已分析 success</div><div class="value">{{ data.success }}</div></div>
  <div class="card yellow"><div class="label">已分析 skipped</div><div class="value">{{ data.skipped }}</div></div>
  <div class="card orange"><div class="label">待分析 pending</div><div class="value">{{ data.pending }}</div></div>
  <div class="card"><div class="label">已拆出岗位</div><div class="value">{{ data.positions }}</div></div>
  <div class="card"><div class="label">hard_skills 非空率</div><div class="value">{{ data.hs_pct }}%</div></div>
</div>

<h2>Enricher 进度 (已抓取 vs 已分析)</h2>
<div class="progress" style="margin-bottom:20px">
  <div class="progress-bar" style="width:{{ data.pct }}%">{{ data.success + data.skipped }} / {{ data.crawled }} ({{ data.pct }}%)</div>
</div>

<h2>VL 识别状态</h2>
<div class="grid">
  <div class="card green"><div class="label">VL success</div><div class="value">{{ data.vl_success }}</div></div>
  <div class="card red"><div class="label">VL failed</div><div class="value">{{ data.vl_failed }}</div></div>
  <div class="card blue"><div class="label">VL not_needed</div><div class="value">{{ data.vl_not_needed }}</div></div>
  <div class="card orange"><div class="label">VL pending</div><div class="value">{{ data.vl_pending }}</div></div>
</div>

<h2>最新已完成公告 (最近 15 条)</h2>
<table>
<tr><th>ID</th><th>公司</th><th>标题</th><th>状态</th><th>岗位数</th><th>更新时间</th></tr>
{% for r in data.recent %}
<tr>
  <td>{{ r[0] }}</td>
  <td>{{ r[1] }}</td>
  <td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ r[2] }}</td>
  <td><span class="badge {{ r[3] }}">{{ r[3] }}</span></td>
  <td>{{ r[4] }}</td>
  <td style="color:#64748b">{{ (r[5] or '')[:16] }}</td>
</tr>
{% endfor %}
</table>

<h2>VL 识别失败记录</h2>
<table>
<tr><th>ID</th><th>公司</th><th>标题</th><th>错误</th></tr>
{% for r in data.vl_fail_list %}
<tr>
  <td>{{ r[0] }}</td>
  <td>{{ r[1] }}</td>
  <td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ r[2] }}</td>
  <td style="color:#f87171;font-size:12px">{{ r[3][:80] if r[3] else '' }}</td>
</tr>
{% else %}
<tr><td colspan="4" style="color:#4ade80;text-align:center">✅ 无 VL 失败</td></tr>
{% endfor %}
</table>

<footer>⏱ 自动刷新 · DB: {{ data.db }}</footer>
</body>
</html>
"""

def get_stats():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    d = {}
    d["crawled"] = conn.execute("SELECT COUNT(*) FROM announcements WHERE crawl_status='success' OR (content IS NOT NULL AND content!='')").fetchone()[0]
    d["success"] = conn.execute("SELECT COUNT(*) FROM announcements WHERE llm_status='success'").fetchone()[0]
    d["skipped"] = conn.execute("SELECT COUNT(*) FROM announcements WHERE llm_status='skipped'").fetchone()[0]
    d["failed"] = conn.execute("SELECT COUNT(*) FROM announcements WHERE llm_status='failed'").fetchone()[0]
    d["pending"] = conn.execute("SELECT COUNT(*) FROM announcements WHERE llm_status='pending'").fetchone()[0]
    d["positions"] = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
    hs = conn.execute("SELECT COUNT(*) FROM positions WHERE hard_skills != '' AND hard_skills != '[]'").fetchone()[0]
    d["hs_pct"] = round(hs * 100 / max(d["positions"], 1))
    d["pct"] = round((d["success"] + d["skipped"]) * 100 / max(d["crawled"], 1))
    
    # VL 状态
    d["vl_success"] = conn.execute("SELECT COUNT(*) FROM announcements WHERE vl_status='success'").fetchone()[0]
    d["vl_failed"] = conn.execute("SELECT COUNT(*) FROM announcements WHERE vl_status='failed'").fetchone()[0]
    d["vl_not_needed"] = conn.execute("SELECT COUNT(*) FROM announcements WHERE vl_status='not_needed'").fetchone()[0]
    d["vl_pending"] = conn.execute("SELECT COUNT(*) FROM announcements WHERE vl_status='pending'").fetchone()[0]
    
    d["recent"] = conn.execute("""
        SELECT id, company_name, announcement_title, llm_status, positions_count, llm_time
        FROM announcements WHERE llm_status IN ('success','skipped','failed')
        ORDER BY COALESCE(llm_time,'') DESC, id DESC LIMIT 15
    """).fetchall()
    
    d["vl_fail_list"] = conn.execute("""
        SELECT id, company_name, announcement_title, vl_error
        FROM announcements WHERE vl_status='failed' ORDER BY id DESC
    """).fetchall()
    
    d["db"] = DB
    conn.close()
    return d

@app.route("/")
def index():
    return render_template_string(HTML, data=get_stats())

@app.route("/api/stats")
def api_stats():
    d = get_stats()
    # 把 sqlite3.Row 转成 tuple 才能 jsonify
    d["recent"] = [tuple(r) for r in d["recent"]]
    d["vl_fail_list"] = [tuple(r) for r in d["vl_fail_list"]]
    return jsonify(d)

if __name__ == "__main__":
    print("🔍 监控看板启动: http://localhost:8765/")
    app.run(host="0.0.0.0", port=8765, debug=False)
