import { useEffect, useState } from "react";
import {
  useAppStore,
  KANBAN_COLUMNS,
  type Application,
} from "../stores/appStore";
import {
  getCompanyDueDiligence,
  updateApplication,
  type DueDiligence,
} from "../api/applications";
import { openExternalUrl } from "../utils/link";

interface Props {
  application: Application;
}

const SOURCE_LABEL: Record<string, string> = {
  db_job: "岗位库",
  db_company: "公司库",
  manual: "自建",
  email: "邮件",
};

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

export default function RecruitmentCard({ application }: Props) {
  const setSelectedAppId = useAppStore((s) => s.setSelectedAppId);
  const [notes, setNotes] = useState(application.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [dd, setDd] = useState<DueDiligence | null>(null);
  const [ddLoading, setDdLoading] = useState(false);

  const statusLabel =
    KANBAN_COLUMNS.find((c) => c.status === application.status)?.label ||
    application.status;

  // 加载公司尽调
  useEffect(() => {
    if (!application.company_name) return;
    setDdLoading(true);
    getCompanyDueDiligence(application.company_name)
      .then(setDd)
      .catch(() => {})
      .finally(() => setDdLoading(false));
  }, [application.company_name]);

  function handleSaveNotes() {
    setSaving(true);
    updateApplication(application.id, { notes: notes.trim() || null })
      .then(() => {
        useAppStore.setState((s) => ({
          applications: s.applications.map((a) =>
            a.id === application.id
              ? { ...a, notes: notes.trim() || null }
              : a
          ),
        }));
      })
      .catch(() => {})
      .finally(() => setSaving(false));
  }

  const isDbLinked = application.source === "db_job" || application.source === "db_company";
  const isEmail = application.source === "email";

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-6 backdrop-blur-sm"
      onClick={() => setSelectedAppId(null)}
    >
      <div
        className="glass my-8 w-full max-w-2xl rounded-2xl p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded bg-white/60 px-2 py-0.5 text-xs font-medium text-text-muted">
                {SOURCE_LABEL[application.source] || application.source}
              </span>
              <span className="rounded bg-primary-soft px-2 py-0.5 text-xs font-medium text-primary-dark">
                {statusLabel}
              </span>
              {application.status === "interview" && application.interview_round > 0 && (
                <span className="rounded bg-warning/20 px-2 py-0.5 text-xs font-medium text-ink">
                  {application.interview_round}面
                </span>
              )}
            </div>
            <h2 className="mt-2 text-xl font-bold text-text">
              {application.company_name || "（未知公司）"}
            </h2>
            <p className="text-sm text-text-muted">
              {application.job_title || "（未填岗位）"}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setSelectedAppId(null)}
            className="text-text-faint hover:text-text"
          >
            ✕
          </button>
        </div>

        {/* 关键时间线 */}
        <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
          <div className="rounded-lg bg-white/40 p-2">
            <div className="text-text-faint">收藏日期</div>
            <div className="font-medium text-text">{formatDate(application.favorite_at)}</div>
          </div>
          <div className="rounded-lg bg-white/40 p-2">
            <div className="text-text-faint">投递日期</div>
            <div className="font-medium text-text">{formatDate(application.applied_at)}</div>
          </div>
          <div className="rounded-lg bg-white/40 p-2">
            <div className="text-text-faint">面试日期</div>
            <div className="font-medium text-text">{formatDate(application.interview_at)}</div>
          </div>
        </div>

        {/* 链接区：DB 关联显示公告/投递；邮件显示邮件链接 */}
        <div className="mt-4 flex flex-wrap gap-2">
          {isDbLinked && application.announcement_url && (
            <button
              type="button"
              onClick={() => void openExternalUrl(application.announcement_url)}
              className="rounded-pill bg-primary-soft px-3 py-1.5 text-xs font-medium text-primary-dark hover:bg-primary-light"
            >
              📢 招聘公告
            </button>
          )}
          {isDbLinked && application.apply_url && (
            <button
              type="button"
              onClick={() => void openExternalUrl(application.apply_url)}
              className="rounded-pill bg-success/15 px-3 py-1.5 text-xs font-medium text-success hover:bg-success/25"
            >
              📮 投递链接
            </button>
          )}
          {isEmail && (
            <span className="rounded-pill bg-info-soft px-3 py-1.5 text-xs font-medium text-info">
              📧 来源：邮件同步
            </span>
          )}
          {!isDbLinked && !isEmail && (
            <span className="rounded-pill bg-white/40 px-3 py-1.5 text-xs text-text-muted">
              用户自建记录
            </span>
          )}
        </div>

        {/* 备注 */}
        <div className="mt-4">
          <label className="text-xs font-medium text-text-muted">备注</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="HR 联系方式、面试反馈、注意事项…"
            rows={3}
            className="mt-1 w-full resize-none rounded-lg border border-white/60 bg-white/40 p-2 text-sm text-text placeholder:text-text-faint focus:border-primary-dark focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
          <div className="mt-1 flex justify-end">
            <button
              type="button"
              onClick={handleSaveNotes}
              disabled={saving}
              className="rounded-pill bg-primary px-4 py-1.5 text-xs font-semibold text-ink hover:bg-primary-dark disabled:opacity-50"
            >
              {saving ? "保存中…" : "保存备注"}
            </button>
          </div>
        </div>

        {/* 公司尽调卡 */}
        <div className="mt-5 rounded-xl border border-white/60 bg-white/30 p-4">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-text">
            🔍 公司尽调
            {dd?.cached && (
              <span className="rounded bg-white/60 px-1.5 py-0.5 text-[10px] text-text-faint">
                已缓存
              </span>
            )}
          </h3>

          {ddLoading ? (
            <div className="mt-3 text-center text-xs text-text-faint">
              正在生成公司尽调…（联网搜索 + AI 分析）
            </div>
          ) : dd ? (
            <div className="mt-3 space-y-3">
              {dd.intro ? (
                <div>
                  <div className="text-xs font-medium text-text-muted">公司简介</div>
                  <p className="mt-1 text-sm leading-relaxed text-text">{dd.intro}</p>
                </div>
              ) : (
                <div className="rounded-lg bg-warning-soft/30 px-3 py-2 text-xs text-warning-dark">
                  ⚠️ AI 未能生成公司简介，可能是公司名称不明确或联网搜索受限。
                </div>
              )}
              {dd.official_website ? (
                <div>
                  <div className="text-xs font-medium text-text-muted">官网</div>
                  <button
                    type="button"
                    onClick={() => void openExternalUrl(dd.official_website)}
                    className="mt-1 text-sm text-info hover:underline"
                  >
                    {dd.official_website}
                  </button>
                </div>
              ) : (
                <div className="text-xs text-text-faint">官网：暂未识别到</div>
              )}
              {dd.news_links.length > 0 ? (
                <div>
                  <div className="text-xs font-medium text-text-muted">近期新闻</div>
                  <ul className="mt-1 space-y-1">
                    {dd.news_links.map((n, i) => (
                      <li key={i}>
                        <button
                          type="button"
                          onClick={() => void openExternalUrl(n.url)}
                          className="text-left text-sm text-text hover:text-info hover:underline"
                        >
                          • {n.title}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="text-xs text-text-faint">近期新闻：暂未搜索到</div>
              )}
              {dd.why_company_questions.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-text-muted">
                    面试准备：「为什么选择这家公司」
                  </div>
                  <div className="mt-1 space-y-2">
                    {dd.why_company_questions.map((q, i) => {
                      const answer = q.answer || q.hint || "";
                      return (
                        <div key={i} className="rounded-lg bg-white/40 p-2">
                          <div className="text-sm font-medium text-text">Q: {q.question}</div>
                          {answer && (
                            <div className="mt-0.5 text-xs leading-relaxed text-text-muted">
                              💡 {answer}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              {dd.generated_at && (
                <div className="text-[10px] text-text-faint">
                  生成时间：{dd.generated_at}
                </div>
              )}
            </div>
          ) : (
            <div className="mt-3 text-center text-xs text-text-faint">
              尽调生成失败，请稍后重试
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
