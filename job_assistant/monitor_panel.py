"""
批量处理监控面板 — 零依赖,基于 Python 内置 http.server。

提供:
- GET /         → 可视化监控面板(HTML,自动刷新)
- GET /api/stats → JSON 实时统计数据

运行: python3 monitor_panel.py [--port 8765]
"""
import os
import sys
import json
import sqlite3
import re
import time
import argparse
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

DB_PATH = "/workspace/job_assistant/data/jobs.db"
FETCH_LOG = "/workspace/job_assistant/fetch_announcements.log"
ANALYZE_LOG = "/workspace/job_assistant/analyze_announcements.log"
TWO_STAGE_LOG = "/workspace/job_assistant/two_stage.log"
FETCH_RESULTS = "/workspace/job_assistant/fetch_results.jsonl"


def tail_file(path, n=30):
    """读取文件最后 n 行"""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-n:]]
    except Exception:
        return []


def parse_fetch_progress():
    """从 fetch log 解析最新进度"""
    lines = tail_file(FETCH_LOG, 200)
    progress = {"current": 0, "total": 0, "rate": 0, "stats": {}}
    for line in reversed(lines):
        m = re.search(r"进度 (\d+)/(\d+) \(([\d.]+)条/秒\) stats=(\{.*\})", line)
        if m:
            progress["current"] = int(m.group(1))
            progress["total"] = int(m.group(2))
            progress["rate"] = float(m.group(3))
            try:
                # Python dict 用单引号,替换为双引号再解析
                stats_str = m.group(4).replace("'", '"')
                progress["stats"] = json.loads(stats_str)
            except Exception:
                pass
            break
    return progress


def parse_analyze_progress():
    """从 analyze log 解析最新进度(兼容一次性和守护模式)"""
    lines = tail_file(ANALYZE_LOG, 200)
    progress = {"current": 0, "total": 0, "rate": 0, "stats": {}}
    for line in reversed(lines):
        # 一次性模式: 进度 N/M (X条/秒) stats={...}
        m = re.search(r"进度 (\d+)/(\d+) \(([\d.]+)条/秒\) stats=(\{.*\})", line)
        if m:
            progress["current"] = int(m.group(1))
            progress["total"] = int(m.group(2))
            progress["rate"] = float(m.group(3))
            try:
                stats_str = m.group(4).replace("'", '"')
                progress["stats"] = json.loads(stats_str)
            except Exception:
                pass
            break
        # 守护模式: 已分析 N 条 (X条/秒) stats={...}
        m = re.search(r"已分析 (\d+) 条 \(([\d.]+)条/秒\) stats=(\{.*\})", line)
        if m:
            progress["current"] = int(m.group(1))
            progress["rate"] = float(m.group(2))
            try:
                stats_str = m.group(3).replace("'", '"')
                progress["stats"] = json.loads(stats_str)
            except Exception:
                pass
            break
    for line in reversed(lines):
        if "分析守护进程结束" in line or "阶段二完成" in line:
            progress["finished"] = True
            break
    return progress


def parse_two_stage_status():
    """判断当前阶段状态(并行模式)"""
    procs = _detect_procs()
    running = bool(procs["fetch"] or procs["analyze"] or procs["parallel"])
    if not running:
        lines = tail_file(TWO_STAGE_LOG, 10)
        for line in lines:
            if "结束" in line:
                return "finished"
        return "stopped"
    if procs["fetch"] and procs["analyze"]:
        return "parallel"
    if procs["fetch"]:
        return "fetching"
    if procs["analyze"]:
        return "analyzing"
    return "running"


def _detect_procs() -> dict:
    """检测各进程是否运行,返回 dict"""
    procs = {"fetch": [], "analyze": [], "parallel": []}
    try:
        out = subprocess.run(
            ["pgrep", "-f", "fetch_announcements.py"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            procs["fetch"] = out.stdout.strip().split("\n")
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["pgrep", "-f", "analyze_daemon.py"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            procs["analyze"] = out.stdout.strip().split("\n")
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["pgrep", "-f", "run_parallel.py"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            procs["parallel"] = out.stdout.strip().split("\n")
    except Exception:
        pass
    return procs


def check_process_running():
    """检查抓取/分析进程是否在运行,返回 (running, pids_list)"""
    procs = _detect_procs()
    running = bool(procs["fetch"] or procs["analyze"] or procs["parallel"])
    all_pids = procs["fetch"] + procs["analyze"] + procs["parallel"]
    return running, all_pids


def get_db_stats():
    """查询数据库统计"""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN detail_analyzed=1 THEN 1 ELSE 0 END) as analyzed,
                   SUM(CASE WHEN detail_analyzed=0 AND link_valid=1 THEN 1 ELSE 0 END) as unanalyzed,
                   COUNT(DISTINCT company) as companies
            FROM jobs
        """).fetchone()
        # 结构化字段填充率
        row2 = conn.execute("""
            SELECT SUM(CASE WHEN job_category IS NOT NULL AND job_category != '' THEN 1 ELSE 0 END) as with_category,
                   SUM(CASE WHEN hard_skills IS NOT NULL AND hard_skills != '' THEN 1 ELSE 0 END) as with_skills,
                   SUM(CASE WHEN major_required IS NOT NULL AND major_required != '' THEN 1 ELSE 0 END) as with_major
            FROM jobs WHERE detail_analyzed=1
        """).fetchone()
        conn.close()
        return {
            "total": row[0], "analyzed": row[1] or 0,
            "unanalyzed": row[2] or 0, "companies": row[3] or 0,
            "with_category": row2[0] or 0, "with_skills": row2[1] or 0,
            "with_major": row2[2] or 0,
        }
    except Exception as e:
        return {"error": str(e)}


def count_fetch_results():
    """统计 fetch_results.jsonl 行数和各状态"""
    counts = {}
    total = 0
    if os.path.exists(FETCH_RESULTS):
        try:
            with open(FETCH_RESULTS, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    total += 1
                    try:
                        rec = json.loads(line)
                        s = rec.get("status", "unknown")
                        counts[s] = counts.get(s, 0) + 1
                    except Exception:
                        pass
        except Exception:
            pass
    return {"total": total, "by_status": counts}


def get_stats():
    running, pids = check_process_running()
    fetch = parse_fetch_progress()
    analyze = parse_analyze_progress()
    stage = parse_two_stage_status()
    db = get_db_stats()
    fetched = count_fetch_results()

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "running": running,
        "pids": pids,
        "stage": stage,
        "fetch": fetch,
        "analyze": analyze,
        "db": db,
        "fetched": fetched,
    }


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>校招批量处理监控面板</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #0f172a; color: #e2e8f0; padding: 20px; }
  .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
  .header h1 { font-size: 22px; }
  .status-badge { padding: 6px 16px; border-radius: 20px; font-size: 14px; font-weight: 600; }
  .running { background: #16a34a; color: white; }
  .stopped { background: #dc2626; color: white; }
  .finished { background: #2563eb; color: white; }
  .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
  .card { background: #1e293b; border-radius: 12px; padding: 18px; }
  .card .label { font-size: 12px; color: #94a3b8; margin-bottom: 6px; }
  .card .value { font-size: 28px; font-weight: 700; }
  .card .sub { font-size: 12px; color: #64748b; margin-top: 4px; }
  .panel { background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
  .panel h2 { font-size: 16px; margin-bottom: 14px; color: #f1f5f9; }
  .progress-bar { height: 24px; background: #334155; border-radius: 12px; overflow: hidden;
                  position: relative; margin-bottom: 10px; }
  .progress-fill { height: 100%; background: linear-gradient(90deg, #3b82f6, #06b6d4);
                   transition: width 0.5s; display: flex; align-items: center; justify-content: center;
                   font-size: 12px; font-weight: 600; }
  .stats-row { display: flex; gap: 16px; flex-wrap: wrap; font-size: 13px; }
  .stat-item { display: flex; align-items: center; gap: 6px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; }
  .dot-ok { background: #22c55e; }
  .dot-blocked { background: #ef4444; }
  .dot-failed { background: #f59e0b; }
  .dot-invalid { background: #64748b; }
  .dot-new { background: #8b5cf6; }
  .log-box { background: #0f172a; border-radius: 8px; padding: 12px; max-height: 300px;
             overflow-y: auto; font-family: "SF Mono", Monaco, monospace; font-size: 12px;
             line-height: 1.6; }
  .log-line { white-space: pre-wrap; word-break: break-all; }
  .log-warn { color: #fbbf24; }
  .log-info { color: #94a3b8; }
  .stage-indicator { display: flex; gap: 8px; margin-bottom: 16px; }
  .stage-chip { padding: 8px 16px; border-radius: 8px; font-size: 13px; font-weight: 600;
                background: #334155; color: #94a3b8; }
  .stage-chip.active { background: #3b82f6; color: white; }
  .stage-chip.done { background: #16a34a; color: white; }
  .eta { font-size: 13px; color: #94a3b8; margin-top: 8px; }
</style>
</head>
<body>

<div class="header">
  <h1>📊 校招批量处理监控面板</h1>
  <div>
    <span id="statusBadge" class="status-badge stopped">检测中...</span>
    <span style="margin-left:12px;color:#64748b;font-size:13px;" id="timestamp"></span>
  </div>
</div>

<div class="grid">
  <div class="card">
    <div class="label">数据库总岗位</div>
    <div class="value" id="dbTotal">-</div>
    <div class="sub" id="dbCompanies">- 家公司</div>
  </div>
  <div class="card">
    <div class="label">已分析岗位</div>
    <div class="value" style="color:#22c55e" id="dbAnalyzed">-</div>
    <div class="sub" id="analyzedRate">-</div>
  </div>
  <div class="card">
    <div class="label">待分析岗位</div>
    <div class="value" style="color:#f59e0b" id="dbUnanalyzed">-</div>
    <div class="sub">link_valid=1</div>
  </div>
  <div class="card">
    <div class="label">结构化字段覆盖率</div>
    <div class="value" id="structuredRate">-</div>
    <div class="sub" id="structuredDetail">-</div>
  </div>
</div>

<div class="panel">
  <h2>处理阶段</h2>
  <div class="stage-indicator">
    <div class="stage-chip" id="chipFetch">阶段一:抓取公告</div>
    <div class="stage-chip" id="chipAnalyze">阶段二:LLM 分析</div>
  </div>

  <div id="fetchPanel">
    <h2>阶段一:并发抓取 <span style="font-size:13px;color:#94a3b8;font-weight:400" id="fetchEta"></span></h2>
    <div class="progress-bar">
      <div class="progress-fill" id="fetchFill" style="width:0%">0/0</div>
    </div>
    <div class="stats-row" id="fetchStats"></div>
  </div>

  <div id="analyzePanel" style="margin-top:20px;display:none;">
    <h2>阶段二:LLM 分析 <span style="font-size:13px;color:#94a3b8;font-weight:400" id="analyzeEta"></span></h2>
    <div class="progress-bar">
      <div class="progress-fill" id="analyzeFill" style="width:0%">0/0</div>
    </div>
    <div class="stats-row" id="analyzeStats"></div>
  </div>
</div>

<div class="panel">
  <h2>📋 近期日志</h2>
  <div class="log-box" id="logBox"></div>
</div>

<script>
async function refresh() {
  try {
    const resp = await fetch('/api/stats');
    const d = await resp.json();

    document.getElementById('timestamp').textContent = d.timestamp;

    // 状态徽章
    const badge = document.getElementById('statusBadge');
    badge.className = 'status-badge';
    if (d.stage === 'finished') {
      badge.classList.add('finished');
      badge.textContent = '已完成';
    } else if (d.running) {
      badge.classList.add('running');
      badge.textContent = '运行中 (PID: ' + (d.pids[0] || '?') + ')';
    } else {
      badge.classList.add('stopped');
      badge.textContent = '已停止';
    }

    // DB 统计
    document.getElementById('dbTotal').textContent = d.db.total || 0;
    document.getElementById('dbCompanies').textContent = (d.db.companies || 0) + ' 家公司';
    document.getElementById('dbAnalyzed').textContent = d.db.analyzed || 0;
    const rate = d.db.total > 0 ? ((d.db.analyzed / d.db.total) * 100).toFixed(1) : 0;
    document.getElementById('analyzedRate').textContent = rate + '% 完成率';
    document.getElementById('dbUnanalyzed').textContent = d.db.unanalyzed || 0;
    const catRate = d.db.analyzed > 0 ? ((d.db.with_category / d.db.analyzed) * 100).toFixed(0) : 0;
    document.getElementById('structuredRate').textContent = catRate + '%';
    document.getElementById('structuredDetail').textContent =
      '分类' + (d.db.with_category||0) + ' / 技能' + (d.db.with_skills||0) + ' / 专业' + (d.db.with_major||0);

    // 阶段芯片
    const chipFetch = document.getElementById('chipFetch');
    const chipAnalyze = document.getElementById('chipAnalyze');
    chipFetch.className = 'stage-chip';
    chipAnalyze.className = 'stage-chip';
    if (d.stage === 'fetching') {
      chipFetch.classList.add('active');
    } else if (d.stage === 'analyzing') {
      chipFetch.classList.add('done');
      chipAnalyze.classList.add('active');
      document.getElementById('analyzePanel').style.display = 'block';
    } else if (d.stage === 'parallel') {
      chipFetch.classList.add('active');
      chipAnalyze.classList.add('active');
      document.getElementById('analyzePanel').style.display = 'block';
    } else if (d.stage === 'finished') {
      chipFetch.classList.add('done');
      chipAnalyze.classList.add('done');
      document.getElementById('analyzePanel').style.display = 'block';
    }

    // 阶段一进度
    const f = d.fetch;
    if (f.total > 0) {
      const pct = (f.current / f.total * 100).toFixed(1);
      document.getElementById('fetchFill').style.width = pct + '%';
      document.getElementById('fetchFill').textContent = f.current + '/' + f.total + ' (' + pct + '%)';
      const s = f.stats || {};
      document.getElementById('fetchStats').innerHTML =
        '<span class="stat-item"><span class="dot dot-ok"></span>成功 ' + (s.ok||0) + '</span>' +
        '<span class="stat-item"><span class="dot dot-blocked"></span>反爬拦截 ' + (s.blocked||0) + '</span>' +
        '<span class="stat-item"><span class="dot dot-failed"></span>抓取失败 ' + (s.fetch_failed||0) + '</span>' +
        '<span class="stat-item"><span class="dot dot-invalid"></span>链接无效 ' + (s.link_invalid||0) + '</span>' +
        '<span class="stat-item" style="color:#64748b">速度 ' + f.rate + ' 条/秒</span>';
      if (f.rate > 0) {
        const remain = (f.total - f.current) / f.rate;
        document.getElementById('fetchEta').textContent =
          '预计剩余 ' + (remain/60).toFixed(1) + ' 分钟';
      }
    }

    // 阶段二进度
    const a = d.analyze;
    if (a.current > 0 || a.total > 0) {
      const analyzeFill = document.getElementById('analyzeFill');
      if (a.total > 0) {
        const pct = (a.current / a.total * 100).toFixed(1);
        analyzeFill.style.width = pct + '%';
        analyzeFill.textContent = a.current + '/' + a.total + ' (' + pct + '%)';
      } else {
        // 守护模式:无总数,显示流式进度
        analyzeFill.style.width = '100%';
        analyzeFill.style.background = 'linear-gradient(90deg, #8b5cf6, #ec4899)';
        analyzeFill.textContent = '已分析 ' + a.current + ' 条 (流式)';
      }
      const s = a.stats || {};
      document.getElementById('analyzeStats').innerHTML =
        '<span class="stat-item"><span class="dot dot-new"></span>新增岗位 ' + (s.new_jobs||0) + '</span>' +
        '<span class="stat-item"><span class="dot dot-failed"></span>解析空 ' + (s.parse_empty||0) + '</span>' +
        '<span class="stat-item"><span class="dot dot-blocked"></span>非本届 ' + (s.not_current_grade||0) + '</span>' +
        '<span class="stat-item"><span class="dot dot-invalid"></span>抓取失败 ' + (s.fetch_failed||0) + '</span>' +
        '<span class="stat-item" style="color:#64748b">速度 ' + a.rate + ' 条/秒</span>';
    }

    // 日志
    const logLines = [];
    const fetchLog = await fetch('/api/logs/fetch').then(r => r.json());
    (fetchLog.lines || []).forEach(l => {
      const cls = l.includes('WARNING') ? 'log-warn' : 'log-info';
      logLines.push('<div class="log-line ' + cls + '">' + escapeHtml(l) + '</div>');
    });
    document.getElementById('logBox').innerHTML = logLines.join('');
    document.getElementById('logBox').scrollTop = document.getElementById('logBox').scrollHeight;

  } catch (e) {
    console.error(e);
  }
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode("utf-8"))
        elif self.path == "/api/stats":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(get_stats(), ensure_ascii=False).encode("utf-8"))
        elif self.path.startswith("/api/logs/"):
            log_type = self.path.split("/")[-1]
            log_map = {
                "fetch": FETCH_LOG,
                "analyze": ANALYZE_LOG,
                "two_stage": TWO_STAGE_LOG,
            }
            lines = tail_file(log_map.get(log_type, FETCH_LOG), 40)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"lines": lines}, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # 静默 HTTP 日志


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), Handler)
    print(f"监控面板已启动: http://{args.host}:{args.port}")
    print(f"统计接口: http://{args.host}:{args.port}/api/stats")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n监控面板已停止")
        server.server_close()


if __name__ == "__main__":
    main()
