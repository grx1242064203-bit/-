#!/usr/bin/env python3
"""本地监控看板代理: SSH 拉取服务器状态, 提供 HTTP 接口给前端看板"""
import json
import subprocess
import http.server
import socketserver
from datetime import datetime

PORT = 8765

def get_remote_status():
    """通过 SSH 获取服务器上的 pipeline 状态"""
    cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
        "-i", "/root/.ssh/id_ed25519",
        "-o", "ProxyCommand=nc -X connect -x 127.0.0.1:18080 %h %p",
        "admin@47.250.216.165",
        'cd /opt/job_assistant && venv/bin/python3 -c "'
        "import sqlite3, json, os;"
        "c=sqlite3.connect('data/jobs.db');"
        "pending=c.execute(\\\"SELECT COUNT(*) FROM announcements WHERE llm_status='pending'\\\").fetchone()[0];"
        "success=c.execute(\\\"SELECT COUNT(*) FROM announcements WHERE llm_status='success'\\\").fetchone()[0];"
        "skipped=c.execute(\\\"SELECT COUNT(*) FROM announcements WHERE llm_status='skipped'\\\").fetchone()[0];"
        "failed=c.execute(\\\"SELECT COUNT(*) FROM announcements WHERE llm_status='failed'\\\").fetchone()[0];"
        "total=c.execute(\\\"SELECT COUNT(*) FROM announcements\\\").fetchone()[0];"
        "positions=c.execute(\\\"SELECT COUNT(*) FROM positions\\\").fetchone()[0];"
        "req_empty=c.execute(\\\"SELECT COUNT(*) FROM positions WHERE requirements IS NULL OR requirements=''\\\").fetchone()[0];"
        "print(json.dumps({'pending':pending,'success':success,'skipped':skipped,'failed':failed,'total':total,'positions':positions,'req_empty':req_empty}));"
        '"'
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            data = json.loads(result.stdout.strip().split("\n")[-1])
            return data
        return {"error": result.stderr[:200]}
    except Exception as e:
        return {"error": str(e)}

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>校招 Pipeline 监控看板</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }
.container { max-width: 1000px; margin: 0 auto; }
h1 { font-size: 24px; margin-bottom: 24px; color: #f1f5f9; }
.last-update { font-size: 13px; color: #64748b; margin-bottom: 20px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
.card { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
.card .label { font-size: 13px; color: #94a3b8; margin-bottom: 8px; }
.card .value { font-size: 32px; font-weight: 700; }
.card .sub { font-size: 12px; color: #64748b; margin-top: 4px; }
.green { color: #4ade80; }
.blue { color: #60a5fa; }
.amber { color: #fbbf24; }
.red { color: #f87171; }
.purple { color: #c084fc; }
.progress-section { background: #1e293b; border-radius: 12px; padding: 24px; border: 1px solid #334155; margin-bottom: 24px; }
.progress-bar { height: 24px; background: #334155; border-radius: 12px; overflow: hidden; position: relative; }
.progress-fill { height: 100%; background: linear-gradient(90deg, #3b82f6, #8b5cf6); border-radius: 12px; transition: width 0.5s; }
.progress-text { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 600; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.5); }
.legend { display: flex; gap: 24px; margin-top: 16px; font-size: 13px; }
.legend-item { display: flex; align-items: center; gap: 8px; }
.legend-dot { width: 12px; height: 12px; border-radius: 50%; }
</style>
</head>
<body>
<div class="container">
  <h1>📊 校招 Pipeline 实时监控</h1>
  <div class="last-update" id="lastUpdate">加载中...</div>
  <div class="grid">
    <div class="card"><div class="label">公告总数</div><div class="value" id="total">-</div></div>
    <div class="card"><div class="label">处理成功</div><div class="value green" id="success">-</div><div class="sub" id="successPct"></div></div>
    <div class="card"><div class="label">降级处理</div><div class="value amber" id="skipped">-</div><div class="sub" id="skippedPct"></div></div>
    <div class="card"><div class="label">处理失败</div><div class="value red" id="failed">-</div></div>
    <div class="card"><div class="label">待处理</div><div class="value blue" id="pending">-</div><div class="sub" id="pendingPct"></div></div>
    <div class="card"><div class="label">岗位总数</div><div class="value purple" id="positions">-</div></div>
    <div class="card"><div class="label">空任职要求</div><div class="value" id="reqEmpty">-</div><div class="sub">应为 0</div></div>
  </div>
  <div class="progress-section">
    <div class="label" style="font-size:14px;margin-bottom:12px;color:#94a3b8;">处理进度</div>
    <div class="progress-bar">
      <div class="progress-fill" id="progressFill" style="width:0%"></div>
      <div class="progress-text" id="progressText">0%</div>
    </div>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:#4ade80"></div>成功</div>
      <div class="legend-item"><div class="legend-dot" style="background:#fbbf24"></div>降级</div>
      <div class="legend-item"><div class="legend-dot" style="background:#f87171"></div>失败</div>
      <div class="legend-item"><div class="legend-dot" style="background:#60a5fa"></div>待处理</div>
    </div>
  </div>
</div>
<script>
async function refresh() {
  try {
    const res = await fetch('/status');
    const d = await res.json();
    if (d.error) { document.getElementById('lastUpdate').textContent = '错误: ' + d.error; return; }
    const total = d.total || 1;
    const done = d.success + d.skipped + d.failed;
    const pct = ((done / total) * 100).toFixed(1);
    document.getElementById('total').textContent = d.total;
    document.getElementById('success').textContent = d.success;
    document.getElementById('successPct').textContent = ((d.success/total)*100).toFixed(1) + '%';
    document.getElementById('skipped').textContent = d.skipped;
    document.getElementById('skippedPct').textContent = ((d.skipped/total)*100).toFixed(1) + '%';
    document.getElementById('failed').textContent = d.failed || 0;
    document.getElementById('pending').textContent = d.pending;
    document.getElementById('pendingPct').textContent = ((d.pending/total)*100).toFixed(1) + '%';
    document.getElementById('positions').textContent = d.positions;
    document.getElementById('reqEmpty').textContent = d.req_empty;
    document.getElementById('reqEmpty').className = 'value ' + (d.req_empty === 0 ? 'green' : 'red');
    document.getElementById('progressFill').style.width = pct + '%';
    document.getElementById('progressText').textContent = pct + '% (' + done + '/' + total + ')';
    document.getElementById('lastUpdate').textContent = '最后更新: ' + new Date().toLocaleTimeString('zh-CN');
  } catch(e) {
    document.getElementById('lastUpdate').textContent = '连接失败: ' + e.message;
  }
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(get_remote_status()).encode())
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())

if __name__ == '__main__':
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"监控看板启动: http://localhost:{PORT}")
        httpd.serve_forever()
