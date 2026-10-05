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
import { colorMap, pillClass } from "../utils/colorMap";

interface Props {
  application: Application;
}

const SOURCE_LABEL: Record<string, string> = {
  db_job: "岗位库",
  db_company: "公司库",
  manual: "自建",
  email: "邮件",
};

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

// 计算距今天数(d-0=今天,d<=3 视为即将截止)
function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const target = new Date(iso.slice(0, 10) + "T23:59:59");
  if (Number.isNaN(target.getTime())) return null;
  const now = new Date();
  const diff = target.getTime() - now.getTime();
  return Math.ceil(diff / (24 * 60 * 60 * 1000));
}

function deadlineBadge(deadline: string | null | undefined): {
  text: string;
  className: string;
} | null {
  const d = daysUntil(deadline);
  if (d === null) return null;
  if (d < 0) return { text: "已截止", className: "bg-danger/15 text-danger" };
  if (d === 0) return { text: "今日截止", className: "bg-danger text-white" };
  if (d <= 3) return { text: `${d}天后截止`, className: "bg-amber-500 text-white" };
  if (d <= 7) return { text: `${d}天后截止`, className: "bg-amber-200 text-amber-900" };
  return null;
}

export default function RecruitmentCard({ application }: Props) {
  const setSelectedAppId = useAppStore((s) => s.setSelectedAppId);
  const [notes, setNotes] = useState(application.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [dd, setDd] = useState<DueDiligence | null>(null);
  const [ddLoading, setDdLoading] = useState(false);
  const [ddError, setDdError] = useState<string | null>(null);

  const statusLabel =
    KANBAN_COLUMNS.find((c) => c.status === application.status)?.label ||
    application.status;
  const dBadge = deadlineBadge(application.deadline);

  // 加载公司尽调
  useEffect(() => {
    if (!application.company_name) return;
    setDdLoading(true);
    setDdError(null);
    getCompanyDueDiligence(application.company_name)
      .then((data) => {
        setDd(data);
        setDdError(null);
      })
      .catch((err) => {
        // 提取具体错误原因（429 配额 / 503 服务不可用 / 其他）
        const msg =
          (err as { error?: string })?.error ||
          (err as Error)?.message ||
          "尽调生成失败，请稍后重试";
        setDdError(msg);
      })
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
  const isDbJob = application.source === "db_job";

  // 字段详情：公司库 / 岗位库 来源时展示数据库内的关联字段。
  // 用 colorMap 渲染彩色胶囊标签，便于快速识别行业/类型/学历/难度等。
  const fieldPills: { label: string; value: string | null | undefined; pair?: { bg: string; text: string } }[] = [];
  if (isDbLinked) {
    if (application.industry) {
      fieldPills.push({ label: "行业", value: application.industry, pair: colorMap.industry(application.industry) });
    }
    if (application.company_type) {
      fieldPills.push({ label: "公司类型", value: application.company_type, pair: colorMap.companyType(application.company_type) });
    }
    if (application.recruit_type) {
      fieldPills.push({ label: "招聘类型", value: application.recruit_type, pair: colorMap.recruitType(application.recruit_type) });
    }
    // 公司层级(顶/中/保底) - 来自 positions 表 company_tier 字段或公司聚合
    const tier = application.company_tier;
    if (tier) {
      const tierPair: Record<string, { bg: string; text: string }> = {
        "顶": { bg: "bg-rose-100", text: "text-rose-700" },
        "中": { bg: "bg-blue-100", text: "text-blue-700" },
        "保底": { bg: "bg-emerald-100", text: "text-emerald-700" },
      };
      fieldPills.push({
        label: "公司层级",
        value: tier,
        pair: tierPair[tier] || { bg: "bg-gray-100", text: "text-gray-600" },
      });
    }
    if (isDbJob) {
      // 岗位库专属字段
      if (application.job_category) {
        fieldPills.push({ label: "岗位分类", value: application.job_category, pair: colorMap.category(application.job_category) });
      }
      if (application.job_subcategory) {
        fieldPills.push({ label: "岗位子类", value: application.job_subcategory });
      }
      if (application.min_education) {
        fieldPills.push({ label: "最低学历", value: application.min_education, pair: colorMap.education(application.min_education) });
      }
      if (application.is_management_trainee || application.is_mt) {
        const v = String(application.is_management_trainee || application.is_mt || "");
        const isYes = v === "1" || v === "true" || v === "True" || v === "是";
        fieldPills.push({ label: "管培", value: isYes ? "是" : "否", pair: colorMap.isMt(isYes ? 1 : 0) });
      }
      if (application.difficulty) {
        fieldPills.push({ label: "难度", value: application.difficulty, pair: colorMap.difficulty(application.difficulty) });
      }
    }
  }

  // 时间字段
  const timeFields: { label: string; value: string | null | undefined }[] = [];
  if (isDbLinked) {
    if (application.publish_time) {
      timeFields.push({ label: "发布时间", value: application.publish_time });
    }
    if (application.deadline) {
      timeFields.push({ label: "截止时间", value: application.deadline });
    }
  }

  // 长文本/列表字段(独立展示区)
  const longFields: { label: string; value: string | null | undefined }[] = [];
  if (isDbLinked) {
    if (application.recruit_target) {
      longFields.push({ label: "招聘对象", value: application.recruit_target });
    }
    if (application.location) {
      longFields.push({ label: "工作地点", value: application.location });
    }
    if (!isDbJob && application.positions_count != null) {
      longFields.push({ label: "招聘人数", value: String(application.positions_count) });
    }
    if (!isDbJob && application.position_titles) {
      longFields.push({ label: "招聘岗位", value: application.position_titles });
    }
    if (isDbJob) {
      if (application.major_category) {
        longFields.push({ label: "专业大类", value: application.major_category });
      }
      if (application.major_required) {
        longFields.push({ label: "专业要求", value: application.major_required });
      }
      const hs = application.hard_skills;
      if (hs) {
        const hsText = Array.isArray(hs) ? hs.join("、") : String(hs);
        if (hsText) longFields.push({ label: "硬技能", value: hsText });
      }
      const kw = application.keywords;
      if (kw) {
        const kwText = Array.isArray(kw) ? kw.join("、") : String(kw);
        if (kwText) longFields.push({ label: "关键词", value: kwText });
      }
    }
  }

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
              <span className="rounded bg-primary-soft px-2 py-0.5 text-xs font-medium text-primary-ink">
                {statusLabel}
              </span>
              {application.status === "interview" && application.interview_round > 0 && (
                <span className="rounded bg-amber-200 px-2 py-0.5 text-xs font-medium text-amber-900">
                  {application.interview_round}面
                </span>
              )}
              {dBadge && (
                <span className={`rounded px-2 py-0.5 text-xs font-semibold ${dBadge.className}`}>
                  ⏰ {dBadge.text}
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
        <div className="mt-4 grid grid-cols-4 gap-2 text-xs">
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
          <div className={`rounded-lg p-2 ${
            dBadge ? "bg-amber-100" : "bg-white/40"
          }`}>
            <div className="text-text-faint">招聘截止</div>
            <div className="font-medium text-text">{formatDate(application.deadline)}</div>
          </div>
        </div>

        {/* 数据库关联字段详情：公司库 / 岗位库 来源时展示 */}
        {isDbLinked && (fieldPills.length > 0 || timeFields.length > 0 || isDbJob) && (
          <div className="mt-4 rounded-xl border border-white/60 bg-white/40 p-3">
            <div className="mb-2 flex items-center gap-2 text-xs font-medium text-text-muted">
              <span className="rounded bg-info-soft px-1.5 py-0.5 text-info">
                {isDbJob ? "岗位库字段" : "公司库字段"}
              </span>
              <span className="text-text-faint">来自数据库关联</span>
            </div>

            {/* 彩色胶囊字段 */}
            {fieldPills.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {fieldPills.map((f) => (
                  <span
                    key={f.label}
                    className={pillClass(f.pair || { bg: "bg-gray-100", text: "text-gray-600" })}
                    title={`${f.label}: ${f.value}`}
                  >
                    {f.label} · {f.value}
                  </span>
                ))}
              </div>
            )}

            {/* 时间字段 */}
            {timeFields.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
                {timeFields.map((t) => (
                  <span key={t.label}>
                    <span className="text-text-faint">{t.label}:</span>
                    <span className="ml-1 font-medium text-text">{formatDate(t.value)}</span>
                  </span>
                ))}
              </div>
            )}

            {/* 长文本字段(招聘对象/工作地点/招聘岗位/专业/技能/关键词) */}
            {longFields.length > 0 && (
              <div className="mt-2 space-y-1 border-t border-white/60 pt-2 text-xs">
                {longFields.map((f) => (
                  <div key={f.label} className="flex gap-2">
                    <span className="w-16 shrink-0 text-text-faint">{f.label}:</span>
                    <span className="flex-1 break-words leading-relaxed text-text">
                      {f.value}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* JD 摘要(岗位库专属) */}
            {isDbJob && application.jd_summary && (
              <div className="mt-2">
                <div className="text-xs font-medium text-text-muted">JD 摘要</div>
                <p className="mt-0.5 text-xs leading-relaxed text-text line-clamp-4">
                  {application.jd_summary}
                </p>
              </div>
            )}
          </div>
        )}

        {/* 链接区：DB 关联显示公告/投递；邮件显示邮件链接。
            颜色区分:招聘公告=info(蓝)/投递链接=success(绿)/邮件=info-soft(浅蓝)。 */}
        <div className="mt-4 flex flex-wrap gap-2">
          {isDbLinked && application.announcement_url && (
            <button
              type="button"
              onClick={() => void openExternalUrl(application.announcement_url)}
              className="rounded-pill bg-info px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-info-dark"
            >
              📢 招聘公告
            </button>
          )}
          {isDbLinked && application.apply_url && (
            <button
              type="button"
              onClick={() => void openExternalUrl(application.apply_url)}
              className="rounded-pill bg-success px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-success-dark"
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
              {dd.intro && (
                <div>
                  <div className="text-xs font-medium text-text-muted">公司简介</div>
                  <p className="mt-1 text-sm leading-relaxed text-text">{dd.intro}</p>
                </div>
              )}
              {dd.official_website && (
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
              )}
              {dd.news_links.length > 0 && (
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
              )}
              {dd.why_company_questions.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-text-muted">
                    面试准备：「为什么选择这家公司」(点击问题展开专业回答)
                  </div>
                  <div className="mt-1 space-y-2">
                    {dd.why_company_questions.map((q, i) => (
                      <details
                        key={i}
                        className="rounded-lg bg-white/40 p-2 [&_summary]:cursor-pointer"
                      >
                        <summary className="text-sm font-medium text-text marker:text-text-muted">
                          <span className="text-primary">Q{i + 1}:</span> {q.question}
                        </summary>
                        {q.answer && (
                          <div className="mt-2 space-y-1.5 border-t border-white/60 pt-2 text-xs leading-relaxed text-text">
                            {q.answer.split(/\n+/).filter(Boolean).map((p, idx) => (
                              <p key={idx} className="whitespace-pre-wrap">{p}</p>
                            ))}
                          </div>
                        )}
                        {!q.answer && q.hint && (
                          <div className="mt-2 text-xs italic text-text-muted">
                            💡 {q.hint}
                          </div>
                        )}
                      </details>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="mt-3 text-center">
              <p className="text-xs text-warning">{ddError || "尽调生成失败，请稍后重试"}</p>
              <button
                type="button"
                onClick={() => {
                  setDdError(null);
                  setDdLoading(true);
                  getCompanyDueDiligence(application.company_name)
                    .then((data) => {
                      setDd(data);
                      setDdError(null);
                    })
                    .catch((err) => {
                      const msg =
                        (err as { error?: string })?.error ||
                        (err as Error)?.message ||
                        "尽调生成失败，请稍后重试";
                      setDdError(msg);
                    })
                    .finally(() => setDdLoading(false));
                }}
                className="mt-2 rounded-lg bg-primary/80 px-3 py-1 text-xs font-medium text-ink hover:bg-primary"
              >
                ↻ 重试
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
