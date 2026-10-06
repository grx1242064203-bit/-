// 管理后台：用户列表 / 建号 / 吊销恢复 / 改备注 / 重置密码 / 删除 / 批量审核。
import { useEffect, useState, useCallback } from "react";
import { adminApi, type AdminUser } from "../api/admin";
import { extractErrorMessage } from "../api/client";

interface ListParams {
  limit?: number;
  offset?: number;
  search?: string;
}

export default function Admin() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkMsg, setBulkMsg] = useState<string | null>(null);
  const limit = 20;

  const load = useCallback(
    async (params: ListParams = {}) => {
      setLoading(true);
      setError(null);
      try {
        const data = await adminApi.listUsers({
          limit,
          offset: params.offset ?? offset,
          search: params.search ?? (search || undefined),
        });
        setUsers(data.users);
        setTotal(data.total);
        setSelected(new Set()); // 翻页/搜索后清空选择
      } catch (e) {
        setError(extractErrorMessage(e));
      } finally {
        setLoading(false);
      }
    },
    [offset, search],
  );

  useEffect(() => {
    load({ offset: 0 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSearch = () => {
    setOffset(0);
    load({ offset: 0, search });
  };

  const handlePrev = () => {
    const newOffset = Math.max(0, offset - limit);
    setOffset(newOffset);
    load({ offset: newOffset });
  };

  const handleNext = () => {
    const newOffset = offset + limit;
    if (newOffset >= total) return;
    setOffset(newOffset);
    load({ offset: newOffset });
  };

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelected((prev) => {
      if (prev.size === users.length) return new Set();
      return new Set(users.map((u) => u.id));
    });
  };

  const handleBulkActivate = async (is_active: boolean) => {
    if (selected.size === 0) {
      setBulkMsg("请先勾选用户");
      return;
    }
    if (!confirm(`确定批量${is_active ? "启用" : "停用"} ${selected.size} 个用户？`)) return;
    setBulkLoading(true);
    setBulkMsg(null);
    try {
      const res = await adminApi.bulkUpdateUsers({
        user_ids: Array.from(selected),
        is_active,
      });
      setBulkMsg(res.message + (res.skipped_self ? `（已自动跳过自己 ${res.skipped_self} 个）` : ""));
      setSelected(new Set());
      load();
    } catch (e) {
      setBulkMsg(extractErrorMessage(e));
    } finally {
      setBulkLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {error && (
        <div className="glass-soft rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <UserCreateForm onCreated={() => load({ offset: 0 })} />

      <div className="glass-soft rounded-lg border border-line p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-text">用户列表</h2>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="搜索邮箱/备注/订单号"
              className="w-56 rounded-md border border-line bg-white px-3 py-1.5 text-sm"
            />
            <button
              type="button"
              onClick={handleSearch}
              className="rounded-md bg-ink px-3 py-1.5 text-sm text-white hover:opacity-90"
            >
              搜索
            </button>
            <button
              type="button"
              onClick={() => load({ offset: 0 })}
              disabled={loading}
              className="rounded-md border border-line bg-white px-3 py-1.5 text-sm text-text-muted hover:text-text"
            >
              {loading ? "加载中…" : "刷新"}
            </button>
          </div>
        </div>

        {/* 批量操作工具栏 */}
        <div className="mb-3 flex items-center justify-between rounded-md border border-line bg-gray-50 px-3 py-2 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-text-muted">
              已选 {selected.size} / {users.length}
            </span>
            {selected.size > 0 && (
              <>
                <button
                  type="button"
                  onClick={() => handleBulkActivate(false)}
                  disabled={bulkLoading}
                  className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs text-red-700 hover:bg-red-100"
                >
                  批量停用
                </button>
                <button
                  type="button"
                  onClick={() => handleBulkActivate(true)}
                  disabled={bulkLoading}
                  className="rounded border border-green-300 bg-green-50 px-2 py-1 text-xs text-green-700 hover:bg-green-100"
                >
                  批量启用
                </button>
              </>
            )}
          </div>
          {bulkMsg && <span className="text-xs text-orange-600">{bulkMsg}</span>}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-text-muted">
                <th className="px-3 py-2 w-8">
                  <input
                    type="checkbox"
                    checked={selected.size === users.length && users.length > 0}
                    onChange={toggleSelectAll}
                  />
                </th>
                <th className="px-3 py-2">邮箱</th>
                <th className="px-3 py-2">状态</th>
                <th className="px-3 py-2">角色</th>
                <th className="px-3 py-2">XHS订单号</th>
                <th className="px-3 py-2">备注</th>
                <th className="px-3 py-2">注册时间</th>
                <th className="px-3 py-2">最近登录</th>
                <th className="px-3 py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <UserRow
                  key={u.id}
                  user={u}
                  checked={selected.has(u.id)}
                  onToggle={() => toggleSelect(u.id)}
                  onChanged={() => load()}
                />
              ))}
              {users.length === 0 && !loading && (
                <tr>
                  <td colSpan={9} className="px-3 py-6 text-center text-text-muted">
                    暂无用户
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="mt-3 flex items-center justify-between text-xs text-text-muted">
          <span>共 {total} 个用户</span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handlePrev}
              disabled={offset === 0}
              className="rounded-md border border-line bg-white px-3 py-1 disabled:opacity-50"
            >
              上一页
            </button>
            <span className="px-2 py-1">
              {offset + 1} - {Math.min(offset + limit, total)}
            </span>
            <button
              type="button"
              onClick={handleNext}
              disabled={offset + limit >= total}
              className="rounded-md border border-line bg-white px-3 py-1 disabled:opacity-50"
            >
              下一页
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function UserCreateForm({ onCreated }: { onCreated: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const user = await adminApi.createUser({
        email,
        password,
        notes: notes || undefined,
      });
      setSuccess(`已建号：${user.email}（已验证，可直接登录）`);
      setEmail("");
      setPassword("");
      setNotes("");
      onCreated();
    } catch (e) {
      setError(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="glass-soft rounded-lg border border-line p-4"
    >
      <h2 className="mb-3 text-lg font-semibold text-text">手动建号（管理员建号无 XHS 订单号）</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <input
          type="email"
          required
          placeholder="用户邮箱"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded-md border border-line bg-white px-3 py-1.5 text-sm"
        />
        <input
          type="text"
          required
          minLength={6}
          placeholder="初始密码（≥6位）"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded-md border border-line bg-white px-3 py-1.5 text-sm"
        />
        <input
          type="text"
          placeholder="备注（如微信昵称-付费日期）"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="rounded-md border border-line bg-white px-3 py-1.5 text-sm sm:col-span-2"
        />
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-ink px-4 py-1.5 text-sm text-white hover:opacity-90"
        >
          {loading ? "建号中…" : "建号"}
        </button>
        {error && <span className="text-sm text-red-600">{error}</span>}
        {success && <span className="text-sm text-green-600">{success}</span>}
      </div>
    </form>
  );
}

interface UserRowProps {
  user: AdminUser;
  checked: boolean;
  onToggle: () => void;
  onChanged: () => void;
}

function UserRow({ user, checked, onToggle, onChanged }: UserRowProps) {
  const [notesDraft, setNotesDraft] = useState(user.notes ?? "");
  const [loading, setLoading] = useState(false);
  const [showReset, setShowReset] = useState(false);
  const [newPwd, setNewPwd] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const handleToggleActive = async () => {
    setLoading(true);
    try {
      await adminApi.updateUser(user.id, { is_active: !user.is_active });
      onChanged();
    } catch (e) {
      alert(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  const handleToggleAdmin = async () => {
    if (!confirm(`确定${user.is_admin ? "撤销" : "设为"}管理员？`)) return;
    setLoading(true);
    try {
      await adminApi.updateUser(user.id, { is_admin: !user.is_admin });
      onChanged();
    } catch (e) {
      alert(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  const handleSaveNotes = async () => {
    setLoading(true);
    try {
      await adminApi.updateUser(user.id, { notes: notesDraft });
      onChanged();
    } catch (e) {
      alert(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`确定删除用户 ${user.email}？此操作不可恢复。`)) return;
    setLoading(true);
    try {
      await adminApi.deleteUser(user.id);
      onChanged();
    } catch (e) {
      alert(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async () => {
    if (newPwd.length < 6) {
      setMsg("密码至少 6 位");
      return;
    }
    setLoading(true);
    setMsg(null);
    try {
      await adminApi.resetUserPassword(user.id, newPwd);
      setMsg(`已重置，新密码：${newPwd}`);
      setNewPwd("");
      setShowReset(false);
    } catch (e) {
      setMsg(extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <tr className="border-b border-line/50">
      <td className="px-3 py-2">
        <input
          type="checkbox"
          checked={checked}
          onChange={onToggle}
          disabled={user.is_admin} // 管理员不能被批量操作
        />
      </td>
      <td className="px-3 py-2 font-mono text-xs">{user.email}</td>
      <td className="px-3 py-2">
        {user.is_active ? (
          <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">正常</span>
        ) : (
          <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700">已停用</span>
        )}
        {!user.is_verified && (
          <span className="ml-1 rounded-full bg-yellow-100 px-2 py-0.5 text-xs text-yellow-700">未验证</span>
        )}
      </td>
      <td className="px-3 py-2">
        {user.is_admin ? (
          <span className="rounded-full bg-purple-100 px-2 py-0.5 text-xs text-purple-700">管理员</span>
        ) : (
          <span className="text-xs text-text-muted">普通</span>
        )}
      </td>
      <td className="px-3 py-2 font-mono text-xs">
        {user.xhs_order_id ? (
          <span className="text-text">{user.xhs_order_id}</span>
        ) : (
          <span className="text-text-muted">—</span>
        )}
      </td>
      <td className="px-3 py-2">
        <input
          type="text"
          value={notesDraft}
          onChange={(e) => setNotesDraft(e.target.value)}
          className="w-40 rounded border border-line bg-white px-2 py-1 text-xs"
        />
        <button
          type="button"
          onClick={handleSaveNotes}
          disabled={loading}
          className="ml-1 text-xs text-primary hover:underline"
        >
          保存
        </button>
      </td>
      <td className="px-3 py-2 text-xs text-text-muted">
        {user.created_at?.slice(0, 10)}
      </td>
      <td className="px-3 py-2 text-xs text-text-muted">
        {user.last_login_at?.slice(0, 16).replace("T", " ") || "—"}
      </td>
      <td className="px-3 py-2">
        <div className="flex flex-wrap gap-1">
          <button
            type="button"
            onClick={handleToggleActive}
            disabled={loading}
            className="rounded border border-line bg-white px-2 py-0.5 text-xs hover:bg-gray-50"
          >
            {user.is_active ? "停用" : "恢复"}
          </button>
          <button
            type="button"
            onClick={handleToggleAdmin}
            disabled={loading}
            className="rounded border border-line bg-white px-2 py-0.5 text-xs hover:bg-gray-50"
          >
            {user.is_admin ? "撤销管理员" : "设为管理员"}
          </button>
          <button
            type="button"
            onClick={() => setShowReset(!showReset)}
            disabled={loading}
            className="rounded border border-line bg-white px-2 py-0.5 text-xs hover:bg-gray-50"
          >
            重置密码
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={loading}
            className="rounded border border-red-300 bg-red-50 px-2 py-0.5 text-xs text-red-700 hover:bg-red-100"
          >
            删除
          </button>
        </div>
        {showReset && (
          <div className="mt-1 flex gap-1">
            <input
              type="text"
              placeholder="新密码（≥6位）"
              value={newPwd}
              onChange={(e) => setNewPwd(e.target.value)}
              className="w-32 rounded border border-line bg-white px-2 py-0.5 text-xs"
            />
            <button
              type="button"
              onClick={handleResetPassword}
              disabled={loading}
              className="rounded bg-ink px-2 py-0.5 text-xs text-white"
            >
              确认
            </button>
          </div>
        )}
        {msg && <div className="mt-1 text-xs text-orange-600">{msg}</div>}
      </td>
    </tr>
  );
}
