"""网页版管理后台：/admin 路径提供用户管理界面。

功能：
- 管理员邮箱密码登录（复用 /api/v1/auth/login）
- 用户列表：搜索（邮箱/备注/订单号）、分页
- 用户操作：建号、停用/恢复、设/撤管理员、改备注、删除
- 批量操作：批量停用/恢复
- 安全：所有操作走 /api/v1/admin/* 接口，需要管理员 JWT
"""
from __future__ import annotations

ADMIN_CONSOLE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Offer搭子 · 管理后台</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif; background:#f5f6fa; color:#1a1a2e; min-height:100vh; }

/* 登录页 */
.login-wrap { display:flex; align-items:center; justify-content:center; min-height:100vh; padding:24px; }
.login-box { background:#fff; border-radius:16px; padding:40px; width:100%; max-width:380px; box-shadow:0 4px 24px rgba(0,0,0,0.08); }
.login-box h1 { font-size:22px; font-weight:700; margin-bottom:6px; }
.login-box p { font-size:13px; color:#888; margin-bottom:24px; }
.login-box label { display:block; font-size:13px; font-weight:600; margin-bottom:6px; color:#444; }
.login-box input { width:100%; padding:10px 12px; border:1px solid #e0e0e0; border-radius:8px; font-size:14px; margin-bottom:16px; outline:none; transition:border 0.2s; }
.login-box input:focus { border-color:#667eea; }
.login-box button { width:100%; padding:11px; background:#1a1a2e; color:#fff; border:none; border-radius:8px; font-size:14px; font-weight:600; cursor:pointer; transition:opacity 0.2s; }
.login-box button:hover { opacity:0.9; }
.login-box .error { color:#e74c3c; font-size:13px; margin-top:12px; text-align:center; }

/* 主界面 */
.topbar { background:#1a1a2e; color:#fff; padding:14px 28px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.topbar .brand { font-weight:700; font-size:16px; }
.topbar .brand span { color:#ffd700; }
.topbar .user-info { display:flex; align-items:center; gap:16px; font-size:13px; }
.topbar button { background:#e74c3c; color:#fff; border:none; padding:6px 14px; border-radius:6px; font-size:12px; cursor:pointer; }
.topbar button:hover { opacity:0.9; }

.container { max-width:1200px; margin:0 auto; padding:24px; }

.stats { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }
.stat-card { background:#fff; border-radius:12px; padding:20px; box-shadow:0 2px 8px rgba(0,0,0,0.04); }
.stat-card .label { font-size:12px; color:#888; margin-bottom:6px; }
.stat-card .value { font-size:28px; font-weight:700; color:#1a1a2e; }
.stat-card.green .value { color:#27ae60; }
.stat-card.red .value { color:#e74c3c; }
.stat-card.gold .value { color:#f39c12; }

.panel { background:#fff; border-radius:12px; padding:20px; margin-bottom:20px; box-shadow:0 2px 8px rgba(0,0,0,0.04); }
.panel h2 { font-size:16px; font-weight:700; margin-bottom:16px; }

.toolbar { display:flex; gap:12px; margin-bottom:16px; flex-wrap:wrap; align-items:center; }
.toolbar input[type="text"] { padding:8px 12px; border:1px solid #e0e0e0; border-radius:8px; font-size:13px; flex:1; min-width:200px; outline:none; }
.toolbar input[type="text"]:focus { border-color:#667eea; }
.toolbar button { padding:8px 16px; border-radius:8px; font-size:13px; font-weight:600; cursor:pointer; border:none; }
.btn-primary { background:#1a1a2e; color:#fff; }
.btn-primary:hover { opacity:0.9; }
.btn-success { background:#27ae60; color:#fff; }
.btn-danger { background:#e74c3c; color:#fff; }
.btn-ghost { background:#f0f0f0; color:#444; }
.btn-ghost:hover { background:#e0e0e0; }

table { width:100%; border-collapse:collapse; font-size:13px; }
th { text-align:left; padding:12px 10px; background:#f8f9fc; color:#666; font-weight:600; font-size:12px; border-bottom:2px solid #e8e8e8; position:sticky; top:0; }
td { padding:12px 10px; border-bottom:1px solid #f0f0f0; vertical-align:middle; }
tr:hover { background:#fafbfc; }
tr.selected { background:#eef2ff; }
td.email { font-family:ui-monospace,monospace; font-size:12px; }
td.order { font-family:ui-monospace,monospace; font-size:12px; color:#667eea; }
td.time { font-size:12px; color:#888; }

.badge { display:inline-block; padding:2px 10px; border-radius:12px; font-size:11px; font-weight:600; }
.badge.active { background:#d4edda; color:#155724; }
.badge.inactive { background:#f8d7da; color:#721c24; }
.badge.admin { background:#e2e8f0; color:#475569; }
.badge.user { background:#f1f5f9; color:#64748b; }

.row-actions { display:flex; gap:6px; flex-wrap:wrap; }
.row-actions button { padding:4px 10px; border-radius:6px; font-size:11px; border:1px solid #ddd; background:#fff; cursor:pointer; white-space:nowrap; }
.row-actions button:hover { background:#f0f0f0; }
.row-actions .act-danger { color:#e74c3c; border-color:#f5c6cb; }
.row-actions .act-danger:hover { background:#f8d7da; }

.notes-input { padding:4px 8px; border:1px solid #e0e0e0; border-radius:6px; font-size:12px; width:140px; }
.notes-input:focus { border-color:#667eea; outline:none; }

.pagination { display:flex; justify-content:space-between; align-items:center; margin-top:16px; font-size:13px; color:#666; }
.pagination .pages { display:flex; gap:8px; }
.pagination button { padding:6px 12px; border:1px solid #ddd; border-radius:6px; background:#fff; cursor:pointer; font-size:13px; }
.pagination button:disabled { opacity:0.4; cursor:not-allowed; }

.modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; z-index:100; padding:20px; }
.modal { background:#fff; border-radius:12px; padding:24px; width:100%; max-width:420px; }
.modal h3 { font-size:18px; font-weight:700; margin-bottom:16px; }
.modal label { display:block; font-size:13px; font-weight:600; margin-bottom:6px; color:#444; }
.modal input { width:100%; padding:10px 12px; border:1px solid #e0e0e0; border-radius:8px; font-size:14px; margin-bottom:14px; outline:none; }
.modal input:focus { border-color:#667eea; }
.modal-actions { display:flex; gap:10px; justify-content:flex-end; margin-top:8px; }
.modal-actions button { padding:8px 16px; border-radius:8px; font-size:13px; font-weight:600; cursor:pointer; border:none; }
.toast { position:fixed; top:20px; right:20px; padding:12px 20px; border-radius:8px; color:#fff; font-size:13px; z-index:200; box-shadow:0 4px 12px rgba(0,0,0,0.15); animation:slideIn 0.3s; }
.toast.success { background:#27ae60; }
.toast.error { background:#e74c3c; }
@keyframes slideIn { from { transform:translateX(100%); opacity:0; } to { transform:translateX(0); opacity:1; } }

@media(max-width:768px) {
  .stats { grid-template-columns:repeat(2,1fr); }
  .container { padding:12px; }
  th, td { padding:8px 6px; font-size:12px; }
  .notes-input { width:100px; }
}
</style>
</head>
<body>
<div id="app"></div>
<script>
const TOKEN_KEY = 'admin_token';
const ADMIN_INFO_KEY = 'admin_email';
const API = '/api/v1';
let state = { users:[], total:0, offset:0, limit:20, search:'', selected:new Set(), loading:false };

function getToken(){ return localStorage.getItem(TOKEN_KEY); }
function setToken(t){ t ? localStorage.setItem(TOKEN_KEY,t) : localStorage.removeItem(TOKEN_KEY); }
function setAdminInfo(e){ e ? localStorage.setItem(ADMIN_INFO_KEY,e) : localStorage.removeItem(ADMIN_INFO_KEY); }
function getAdminInfo(){ return localStorage.getItem(ADMIN_INFO_KEY); }

function toast(msg, type='success'){
  const el = document.createElement('div');
  el.className = 'toast '+type;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(()=>el.remove(), 3000);
}

async function api(path, opts={}){
  const headers = {'Content-Type':'application/json', ...(opts.headers||{})};
  const token = getToken();
  if(token) headers['Authorization'] = 'Bearer '+token;
  const res = await fetch(API+path, {...opts, headers});
  if(res.status === 401 || res.status === 403){
    setToken(null); setAdminInfo(null);
    render();
    throw new Error(res.status === 403 ? '需要管理员权限' : '登录已过期，请重新登录');
  }
  if(!res.ok){
    let err = '请求失败';
    try { const d = await res.json(); err = d.detail || d.error || err; } catch(e){}
    throw new Error(err);
  }
  if(res.status === 204) return null;
  return res.json();
}

// ===== 登录页 =====
function renderLogin(){
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="login-wrap">
      <div class="login-box">
        <h1>Offer<span style="color:#ffd700">搭子</span></h1>
        <p>管理后台 · 请使用管理员账号登录</p>
        <form id="login-form">
          <label>邮箱</label>
          <input type="email" id="email" placeholder="admin@example.com" required autofocus>
          <label>密码</label>
          <input type="password" id="password" placeholder="••••••••" required>
          <button type="submit">登 录</button>
          <div class="error" id="login-err"></div>
        </form>
      </div>
    </div>`;
  document.getElementById('login-form').addEventListener('submit', async (e)=>{
    e.preventDefault();
    const err = document.getElementById('login-err');
    err.textContent = '';
    try {
      const data = await api('/auth/login', { method:'POST', body:JSON.stringify({
        email: document.getElementById('email').value,
        password: document.getElementById('password').value,
      })});
      setToken(data.token);
      setAdminInfo(document.getElementById('email').value);
      toast('登录成功');
      render();
    } catch(ex){
      err.textContent = ex.message;
    }
  });
}

// ===== 主界面 =====
async function loadUsers(){
  state.loading = true;
  try {
    const qs = new URLSearchParams({ limit:state.limit, offset:state.offset });
    if(state.search) qs.set('search', state.search);
    const data = await api('/admin/users?'+qs.toString());
    state.users = data.users;
    state.total = data.total;
  } catch(ex){
    toast(ex.message, 'error');
  }
  state.loading = false;
  renderMain();
}

function renderMain(){
  const app = document.getElementById('app');
  const activeCount = state.users.filter(u=>u.is_active).length;
  const adminCount = state.users.filter(u=>u.is_admin).length;
  const noOrderCount = state.users.filter(u=>!u.xhs_order_id).length;

  app.innerHTML = `
    <div class="topbar">
      <div class="brand">Offer<span>搭子</span> · 管理后台</div>
      <div class="user-info">
        <span>${getAdminInfo()||''}</span>
        <button onclick="logout()">退出</button>
      </div>
    </div>
    <div class="container">
      <div class="stats">
        <div class="stat-card"><div class="label">当前页用户</div><div class="value">${state.users.length}</div></div>
        <div class="stat-card green"><div class="label">活跃用户</div><div class="value">${activeCount}</div></div>
        <div class="stat-card gold"><div class="label">管理员</div><div class="value">${adminCount}</div></div>
        <div class="stat-card red"><div class="label">无订单号</div><div class="value">${noOrderCount}</div></div>
      </div>

      <div class="panel">
        <h2>用户列表</h2>
        <div class="toolbar">
          <input type="text" id="search" placeholder="搜索邮箱 / 备注 / 订单号" value="${state.search}">
          <button class="btn-primary" onclick="doSearch()">搜索</button>
          <button class="btn-ghost" onclick="resetSearch()">重置</button>
          <button class="btn-primary" onclick="showCreateModal()">+ 新建用户</button>
          ${state.selected.size > 0 ? `
            <button class="btn-danger" onclick="bulkToggle(false)">批量停用 (${state.selected.size})</button>
            <button class="btn-success" onclick="bulkToggle(true)">批量恢复 (${state.selected.size})</button>
          ` : ''}
        </div>
        <div style="overflow-x:auto">
          <table>
            <thead><tr>
              <th><input type="checkbox" id="sel-all" onchange="toggleAll(this)"></th>
              <th>邮箱</th><th>状态</th><th>角色</th><th>XHS订单号</th><th>备注</th><th>注册时间</th><th>最近登录</th><th>操作</th>
            </tr></thead>
            <tbody>
              ${state.users.length === 0 ? `<tr><td colspan="9" style="text-align:center;color:#888;padding:40px">${state.loading?'加载中...':'暂无用户'}</td></tr>` :
                state.users.map(u => `
                <tr class="${state.selected.has(u.id)?'selected':''}">
                  <td><input type="checkbox" ${state.selected.has(u.id)?'checked':''} onchange="toggleSelect('${u.id}', this.checked)"></td>
                  <td class="email">${u.email}</td>
                  <td><span class="badge ${u.is_active?'active':'inactive'}">${u.is_active?'正常':'停用'}</span>
                    ${!u.is_verified?'<span class="badge inactive" style="margin-left:4px">未验证</span>':''}</td>
                  <td><span class="badge ${u.is_admin?'admin':'user'}">${u.is_admin?'管理员':'普通'}</span></td>
                  <td class="order">${u.xhs_order_id || '<span style="color:#e74c3c">—</span>'}</td>
                  <td><input type="text" class="notes-input" value="${(u.notes||'').replace(/"/g,'&quot;')}" placeholder="备注..." onchange="saveNotes('${u.id}', this.value)"></td>
                  <td class="time">${(u.created_at||'').slice(0,10)}</td>
                  <td class="time">${u.last_login_at ? u.last_login_at.slice(0,16).replace('T',' ') : '—'}</td>
                  <td class="row-actions">
                    <button onclick="toggleActive('${u.id}', ${!u.is_active})">${u.is_active?'停用':'恢复'}</button>
                    <button onclick="toggleAdmin('${u.id}', ${!u.is_admin})">${u.is_admin?'撤管理员':'设管理员'}</button>
                    <button class="act-danger" onclick="delUser('${u.id}', '${u.email}')">删除</button>
                  </td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
        <div class="pagination">
          <span>共 ${state.total} 个用户</span>
          <div class="pages">
            <button onclick="prevPage()" ${state.offset===0?'disabled':''}>上一页</button>
            <span>${state.offset+1}-${Math.min(state.offset+state.limit, state.total)}</span>
            <button onclick="nextPage()" ${state.offset+state.limit>=state.total?'disabled':''}>下一页</button>
          </div>
        </div>
      </div>
    </div>
    <div id="modal-root"></div>`;
}

// ===== 操作 =====
function toggleAll(cb){
  if(cb.checked) state.users.forEach(u=>state.selected.add(u.id));
  else state.selected.clear();
  renderMain();
}
function toggleSelect(id, checked){
  if(checked) state.selected.add(id); else state.selected.delete(id);
  renderMain();
}
function doSearch(){ state.search = document.getElementById('search').value; state.offset=0; state.selected.clear(); loadUsers(); }
function resetSearch(){ state.search=''; state.offset=0; state.selected.clear(); loadUsers(); }
function prevPage(){ if(state.offset>0){ state.offset -= state.limit; loadUsers(); } }
function nextPage(){ if(state.offset+state.limit < state.total){ state.offset += state.limit; loadUsers(); } }

async function toggleActive(id, toActive){
  try {
    await api('/admin/users/'+id, { method:'PATCH', body:JSON.stringify({is_active:toActive}) });
    toast(toActive?'已恢复':'已停用');
    loadUsers();
  } catch(ex){ toast(ex.message, 'error'); }
}
async function toggleAdmin(id, toAdmin){
  if(!confirm(toAdmin?'确定设为管理员？':'确定撤销管理员？')) return;
  try {
    await api('/admin/users/'+id, { method:'PATCH', body:JSON.stringify({is_admin:toAdmin}) });
    toast(toAdmin?'已设为管理员':'已撤销管理员');
    loadUsers();
  } catch(ex){ toast(ex.message, 'error'); }
}
async function saveNotes(id, notes){
  try {
    await api('/admin/users/'+id, { method:'PATCH', body:JSON.stringify({notes:notes||null}) });
    toast('备注已保存');
  } catch(ex){ toast(ex.message, 'error'); loadUsers(); }
}
async function delUser(id, email){
  if(!confirm(`确定删除用户 ${email}？此操作不可恢复。`)) return;
  try {
    await api('/admin/users/'+id, { method:'DELETE' });
    toast('已删除');
    loadUsers();
  } catch(ex){ toast(ex.message, 'error'); }
}
async function bulkToggle(toActive){
  const ids = Array.from(state.selected);
  if(ids.length===0) return;
  if(!confirm(`确定批量${toActive?'恢复':'停用'} ${ids.length} 个用户？`)) return;
  let ok=0, fail=0;
  for(const id of ids){
    try { await api('/admin/users/'+id, { method:'PATCH', body:JSON.stringify({is_active:toActive}) }); ok++; }
    catch(e){ fail++; }
  }
  toast(`完成：成功 ${ok}${fail?', 失败 '+fail:''}`);
  state.selected.clear();
  loadUsers();
}

// ===== 新建用户弹窗 =====
function showCreateModal(){
  document.getElementById('modal-root').innerHTML = `
    <div class="modal-overlay" onclick="if(event.target===this)closeModal()">
      <div class="modal">
        <h3>新建用户</h3>
        <form id="create-form">
          <label>邮箱</label>
          <input type="email" id="c-email" required autofocus>
          <label>初始密码（≥6位）</label>
          <input type="text" id="c-password" minlength="6" required value="${Math.random().toString(36).slice(2,10)}">
          <label>备注（可选）</label>
          <input type="text" id="c-notes" placeholder="如：微信昵称-付费日期">
          <div class="modal-actions">
            <button type="button" class="btn-ghost" onclick="closeModal()">取消</button>
            <button type="submit" class="btn-primary">创建</button>
          </div>
        </form>
      </div>
    </div>`;
  document.getElementById('create-form').addEventListener('submit', async (e)=>{
    e.preventDefault();
    try {
      await api('/admin/users', { method:'POST', body:JSON.stringify({
        email: document.getElementById('c-email').value,
        password: document.getElementById('c-password').value,
        notes: document.getElementById('c-notes').value || undefined,
      })});
      toast('用户创建成功');
      closeModal();
      loadUsers();
    } catch(ex){ toast(ex.message, 'error'); }
  });
}
function closeModal(){ document.getElementById('modal-root').innerHTML=''; }

function logout(){ setToken(null); setAdminInfo(null); state.selected.clear(); render(); }

function render(){
  if(!getToken()) renderLogin();
  else { renderMain(); loadUsers(); }
}
render();
</script>
</body>
</html>"""
