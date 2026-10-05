import { useEffect, useState } from "react";
import { useAppStore, type AppStatus } from "../stores/appStore";
import KanbanBoard from "../components/KanbanBoard";
import RecruitmentCard from "../components/RecruitmentCard";

export default function Applications() {
  const {
    applications,
    isLoading,
    error,
    loadApplications,
    addApplication,
    selectedAppId,
  } = useAppStore();

  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    void loadApplications();
  }, [loadApplications]);

  const selectedApp = applications.find((a) => a.id === selectedAppId) || null;
  const isEmpty = !isLoading && applications.length === 0;

  return (
    <div className="space-y-5 animate-fade-in">
      {/* 顶部：标题 + 操作 */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-text-muted">
          共 {applications.length} 条记录
        </span>
        <div className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="rounded-pill bg-primary px-4 py-1.5 text-sm font-semibold text-ink hover:bg-primary-dark"
          >
            + 新建记录
          </button>
          <button
            type="button"
            onClick={() => void loadApplications()}
            className="glass-soft rounded-pill px-4 py-1.5 text-sm text-text-muted transition hover:text-text"
          >
            刷新
          </button>
        </div>
      </div>

      {/* 错误条 */}
      {error && (
        <div className="rounded-xl bg-danger-soft px-4 py-2 text-sm text-danger">
          {error}
        </div>
      )}

      {/* 主体 */}
      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-primary" />
        </div>
      ) : isEmpty ? (
        <div className="glass flex h-64 flex-col items-center justify-center rounded-xl shadow-sm">
          <div className="text-4xl">📭</div>
          <p className="mt-2 text-base font-medium text-text">还没有投递记录</p>
          <p className="mt-1 text-sm text-text-muted">
            去「岗位列表」或「公司总览」收藏/投递，或点击右上角新建记录
          </p>
        </div>
      ) : (
        <KanbanBoard />
      )}

      {/* 招聘卡详情弹窗 */}
      {selectedApp && <RecruitmentCard application={selectedApp} />}

      {/* 新建自建记录弹窗 */}
      {showCreate && (
        <CreateManualModal
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            void loadApplications();
          }}
          addApplication={addApplication}
        />
      )}
    </div>
  );
}

function CreateManualModal({
  onClose,
  onCreated,
  addApplication,
}: {
  onClose: () => void;
  onCreated: () => void;
  addApplication: (data: {
    job_title?: string;
    company_name?: string;
    status?: AppStatus;
    source?: "manual";
    notes?: string;
  }) => Promise<unknown>;
}) {
  const [companyName, setCompanyName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState<AppStatus>("favorite");
  const [submitting, setSubmitting] = useState(false);

  function handleSubmit() {
    if (!companyName.trim() && !jobTitle.trim()) return;
    setSubmitting(true);
    addApplication({
      company_name: companyName.trim(),
      job_title: jobTitle.trim(),
      status,
      source: "manual",
      notes: notes.trim() || undefined,
    })
      .then(() => onCreated())
      .catch(() => {})
      .finally(() => setSubmitting(false));
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass w-96 rounded-2xl p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold text-text">新建投递记录</h3>
        <p className="mt-1 text-xs text-text-muted">用户自建，不关联岗位数据库</p>

        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs font-medium text-text-muted">公司名称 *</label>
            <input
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="如：字节跳动"
              className="mt-1 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm focus:border-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-text-muted">岗位名称</label>
            <input
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              placeholder="如：后端开发工程师"
              className="mt-1 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm focus:border-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-text-muted">初始状态</label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as AppStatus)}
              className="mt-1 w-full rounded-lg border border-line bg-white px-3 py-2 text-sm focus:border-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/30"
            >
              <option value="favorite">⭐ 收藏</option>
              <option value="applied">📮 已投递</option>
              <option value="assessment">📝 测评</option>
              <option value="interview">💬 面试中</option>
              <option value="offer">🎉 已录用</option>
              <option value="rejected">❌ 已拒绝</option>
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-text-muted">备注</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="mt-1 w-full resize-none rounded-lg border border-line bg-white px-3 py-2 text-sm focus:border-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="glass-soft rounded-pill px-4 py-1.5 text-sm text-text-muted hover:text-text"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting || (!companyName.trim() && !jobTitle.trim())}
            className="rounded-pill bg-primary px-4 py-1.5 text-sm font-semibold text-ink hover:bg-primary-dark disabled:opacity-50"
          >
            {submitting ? "创建中…" : "创建"}
          </button>
        </div>
      </div>
    </div>
  );
}
