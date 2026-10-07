// 日程页：月历视图（周一为每周第一天，标注节假日/节气/农历节日）
// 点击日期格查看当天所有日程卡片
import { useEffect, useMemo, useState } from "react";
import { useScheduleStore } from "../stores/scheduleStore";
import { extractErrorMessage } from "../api/client";
import type {
  Schedule,
  ScheduleType,
  CreateScheduleRequest,
  UpdateScheduleRequest,
  ExtractedSchedule,
} from "../api/schedules";

// ---- 类型 / 标签 / 颜色（保留）----

const TYPE_LABEL: Record<ScheduleType, string> = {
  assessment: "测评",
  written: "笔试",
  interview: "面试",
  other: "其他",
};

const TYPE_COLOR: Record<ScheduleType, string> = {
  assessment: "border-l-info bg-info-soft",
  written: "border-l-warning bg-warning-soft",
  interview: "border-l-success bg-success-soft",
  other: "border-l-gray-400 bg-gray-50",
};

const TYPE_BADGE: Record<ScheduleType, string> = {
  assessment: "bg-info text-info-foreground",
  written: "bg-warning text-warning-foreground",
  interview: "bg-success text-success-foreground",
  other: "bg-gray-500 text-white",
};

// 日历格小圆点颜色（与日程类型对应，方便日历上一眼区分）
const TYPE_DOT: Record<ScheduleType, string> = {
  assessment: "bg-info",
  written: "bg-warning",
  interview: "bg-success",
  other: "bg-gray-500",
};

const CONF_LABEL: Record<ExtractedSchedule["confidence"], string> = {
  high: "高置信",
  medium: "中置信",
  low: "低置信",
};

const CONF_COLOR: Record<ExtractedSchedule["confidence"], string> = {
  high: "bg-success-soft text-success-dark",
  medium: "bg-warning-soft text-warning-dark",
  low: "bg-red-50 text-red-600",
};

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatTimeHM(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function isoToLocalInput(iso: string | null): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
      d.getHours()
    )}:${pad(d.getMinutes())}`;
  } catch {
    return "";
  }
}

function localInputToIso(local: string): string | null {
  if (!local) return null;
  try {
    const d = new Date(local);
    if (isNaN(d.getTime())) return null;
    return d.toISOString();
  } catch {
    return null;
  }
}

// ---- 日期工具 ----

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function dateKey(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

// ---- 节假日 / 节气 / 农历节日数据 ----

// 节假日标识类型：
// - holiday  法定节假日（红字）
// - festival 传统节日（农历，橙字）
// - memo     普通纪念日（灰字）
type DayTagKind = "holiday" | "festival" | "memo";
interface DayTag {
  name: string;
  kind: DayTagKind;
}

// 2026 年中国法定节假日 + 传统节日 + 普通纪念日
const DAY_TAGS_2026: Record<string, DayTag> = {
  "2026-01-01": { name: "元旦", kind: "holiday" },
  "2026-02-14": { name: "情人节", kind: "memo" },
  "2026-02-15": { name: "除夕", kind: "holiday" }, // 农历腊月三十（2026年春节前一天）
  "2026-02-16": { name: "春节", kind: "holiday" }, // 农历正月初一
  "2026-02-17": { name: "初二", kind: "holiday" },
  "2026-02-18": { name: "初三", kind: "holiday" },
  "2026-03-03": { name: "元宵节", kind: "festival" }, // 农历正月十五
  "2026-03-08": { name: "妇女节", kind: "memo" },
  "2026-03-12": { name: "植树节", kind: "memo" },
  "2026-04-01": { name: "愚人节", kind: "memo" },
  "2026-04-04": { name: "清明", kind: "holiday" },
  "2026-05-01": { name: "劳动节", kind: "holiday" },
  "2026-05-04": { name: "青年节", kind: "memo" },
  "2026-05-31": { name: "端午节", kind: "holiday" }, // 农历五月初五
  "2026-06-01": { name: "儿童节", kind: "memo" },
  "2026-07-01": { name: "建党节", kind: "memo" },
  "2026-08-01": { name: "建军节", kind: "memo" },
  "2026-08-19": { name: "七夕", kind: "festival" }, // 农历七月初七
  "2026-09-10": { name: "教师节", kind: "memo" },
  "2026-09-25": { name: "中秋节", kind: "holiday" }, // 农历八月十五
  "2026-10-01": { name: "国庆节", kind: "holiday" },
  "2026-10-18": { name: "重阳节", kind: "festival" }, // 农历九月初九
  "2026-11-11": { name: "光棍节", kind: "memo" },
  "2026-12-24": { name: "平安夜", kind: "memo" },
  "2026-12-25": { name: "圣诞节", kind: "memo" },
};

// 24 节气 2026（紫金山天文台精确日期）
const SOLAR_TERMS_2026: Record<string, string> = {
  "2026-01-05": "小寒",
  "2026-01-20": "大寒",
  "2026-02-04": "立春",
  "2026-02-18": "雨水",
  "2026-03-05": "惊蛰",
  "2026-03-20": "春分",
  "2026-04-05": "清明",
  "2026-04-20": "谷雨",
  "2026-05-05": "立夏",
  "2026-05-21": "小满",
  "2026-06-05": "芒种",
  "2026-06-21": "夏至",
  "2026-07-07": "小暑",
  "2026-07-22": "大暑",
  "2026-08-07": "立秋",
  "2026-08-23": "处暑",
  "2026-09-07": "白露",
  "2026-09-23": "秋分",
  "2026-10-08": "寒露",
  "2026-10-23": "霜降",
  "2026-11-07": "立冬",
  "2026-11-22": "小雪",
  "2026-12-07": "大雪",
  "2026-12-22": "冬至",
};

// 节假日颜色映射
const TAG_COLOR: Record<DayTagKind, string> = {
  holiday: "text-red-600 font-semibold",
  festival: "text-amber-800",
  memo: "text-text-muted",
};

function getDayTag(d: Date): DayTag | null {
  return DAY_TAGS_2026[dateKey(d)] ?? null;
}

function getSolarTerm(d: Date): string | null {
  return SOLAR_TERMS_2026[dateKey(d)] ?? null;
}

// ---- 月历组件 ----

const WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

interface Cell {
  date: Date;
  inMonth: boolean; // 是否属于当前显示月份
  isToday: boolean;
  isWeekend: boolean;
  tag: DayTag | null;
  solarTerm: string | null;
  schedules: Schedule[];
}

function buildMonthCells(year: number, month: number, schedules: Schedule[]): Cell[] {
  // month: 0-11
  const firstOfMonth = new Date(year, month, 1);
  // 周一为每周第一天：getDay() 周日=0，周一=1，...，周六=6
  // 转换为「本月1号之前需要补几个上周日」
  const firstWeekday = (firstOfMonth.getDay() + 6) % 7; // 周一=0，周二=1，...，周日=6
  const gridStart = new Date(year, month, 1 - firstWeekday);

  const today = new Date();
  const cells: Cell[] = [];

  for (let i = 0; i < 42; i++) {
    // 6 行 × 7 列，覆盖任意月份
    const d = new Date(gridStart);
    d.setDate(gridStart.getDate() + i);
    // 防御性：跳过 event_time 缺失或解析失败的 schedule，避免 new Date(null) Invalid Date 影响 filter
    const daySchedules = schedules.filter((s) => {
      if (!s || !s.event_time) return false;
      const sd = new Date(s.event_time);
      if (isNaN(sd.getTime())) return false;
      return isSameDay(sd, d);
    });
    cells.push({
      date: d,
      inMonth: d.getMonth() === month,
      isToday: isSameDay(d, today),
      isWeekend: d.getDay() === 0 || d.getDay() === 6,
      tag: getDayTag(d),
      solarTerm: getSolarTerm(d),
      schedules: daySchedules,
    });
  }
  return cells;
}

function DateCell({ cell, onClick }: { cell: Cell; onClick: () => void }) {
  const { date, inMonth, isToday, isWeekend, tag, solarTerm, schedules } = cell;

  // 日期数字颜色
  let dateColor = "text-text";
  if (isToday) dateColor = "text-white";
  else if (!inMonth) dateColor = "text-text-muted/40";
  else if (tag?.kind === "holiday") dateColor = "text-red-600";
  else if (isWeekend) dateColor = "text-amber-800";

  // 单元格背景
  let bg = "bg-white";
  if (isToday) bg = "bg-primary ring-2 ring-primary";
  else if (!inMonth) bg = "bg-gray-50/50";

  // 显示前 2 个日程
  const visible = schedules.slice(0, 2);
  const more = schedules.length - visible.length;

  return (
    <button
      type="button"
      onClick={onClick}
      className={`group relative flex min-h-[88px] flex-col items-stretch p-1.5 text-left ${bg} transition hover:shadow-md`}
    >
      <div className="flex items-center justify-between">
        <span className={`text-xs font-medium ${dateColor}`}>
          {date.getDate()}
        </span>
        {tag && (
          <span
            className={`truncate text-[10px] ${TAG_COLOR[tag.kind]} ${
              isToday ? "text-white" : ""
            }`}
          >
            {tag.name}
          </span>
        )}
      </div>
      {solarTerm && !tag && (
        <div
          className={`text-[10px] text-emerald-600 ${
            isToday ? "text-white" : ""
          }`}
        >
          {solarTerm}
        </div>
      )}
      {/* 日程徽章列表 */}
      <div className="mt-1 flex-1 space-y-0.5">
        {visible.map((s) => (
          <div
            key={s.id}
            className={`truncate rounded px-1 py-0.5 text-[10px] ${
              isToday
                ? "bg-white/30 text-white"
                : "bg-gray-100 text-text-muted"
            }`}
          >
            <span
              className={`mr-0.5 inline-block h-1.5 w-1.5 rounded-full ${
                TYPE_DOT[s.schedule_type]
              }`}
            />
            <span className="font-medium text-text">【{TYPE_LABEL[s.schedule_type]}】</span>
            {formatTimeHM(s.event_time)} {s.company || s.job_title || ""}
          </div>
        ))}
        {more > 0 && (
          <div className="text-[10px] text-text-muted">+{more} 更多</div>
        )}
      </div>
    </button>
  );
}

function MonthGrid({
  year,
  month,
  schedules,
  onSelectDay,
}: {
  year: number;
  month: number;
  schedules: Schedule[];
  onSelectDay: (cell: Cell) => void;
}) {
  const cells = useMemo(
    () => buildMonthCells(year, month, schedules),
    [year, month, schedules]
  );

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-white">
      {/* 表头：周一-周日 */}
      <div className="grid grid-cols-7 bg-gray-50 text-center text-xs font-medium text-text-muted">
        {WEEKDAYS.map((w, i) => (
          <div
            key={w}
            className={`py-2 ${
              i === 5 || i === 6 ? "text-amber-800" : ""
            }`}
          >
            {w}
          </div>
        ))}
      </div>
      {/* 6 行 × 7 列网格 */}
      <div className="grid grid-cols-7">
        {cells.map((c, i) => (
          <div
            key={i}
            className={`border-b border-r border-line ${
              i % 7 === 6 ? "border-r-0" : ""
            } ${i >= 35 ? "border-b-0" : ""}`}
          >
            <DateCell cell={c} onClick={() => onSelectDay(c)} />
          </div>
        ))}
      </div>
    </div>
  );
}

// 当天日程列表弹窗
function DaySchedulesModal({
  cell,
  onClose,
  onEdit,
}: {
  cell: Cell;
  onClose: () => void;
  onEdit: (s: Schedule) => void;
}) {
  const { date, tag, solarTerm, schedules } = cell;
  const dateStr = `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
  const weekday = WEEKDAYS[(date.getDay() + 6) % 7];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold">{dateStr}</h3>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-text-muted">
              <span>{weekday}</span>
              {tag && (
                <span className={`font-medium ${TAG_COLOR[tag.kind]}`}>
                  · {tag.name}
                </span>
              )}
              {solarTerm && (
                <span className="text-emerald-600">· {solarTerm}</span>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg px-3 py-1 text-sm text-text-muted hover:bg-gray-100"
          >
            关闭
          </button>
        </div>
        {schedules.length === 0 ? (
          <p className="py-8 text-center text-sm text-text-muted">
            当天没有日程，点击右上角「+ 手动新建」或「✨ AI 智能建日程」添加
          </p>
        ) : (
          <div className="space-y-3">
            {schedules
              .slice()
              .sort(
                (a, b) =>
                  new Date(a.event_time).getTime() -
                  new Date(b.event_time).getTime()
              )
              .map((s) => (
                <ScheduleCard key={s.id} schedule={s} onEdit={onEdit} />
              ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---- 日程卡片（保留，用于详情弹窗 + 列表 ----

function ScheduleCard({ schedule, onEdit }: { schedule: Schedule; onEdit: (s: Schedule) => void }) {
  const removeSchedule = useScheduleStore((s) => s.removeSchedule);
  const [deleting, setDeleting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleDelete = async () => {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setDeleting(true);
    setDeleteError(null);
    try {
      await removeSchedule(schedule.id);
    } catch (e) {
      setDeleteError(extractErrorMessage(e));
    } finally {
      setDeleting(false);
      setConfirming(false);
    }
  };

  const isFromEmail = Boolean(schedule.email_link);
  const sourceLabel = isFromEmail ? "邮件同步" : "手动创建";
  const sourceColor = isFromEmail
    ? "bg-primary-soft text-primary-ink"
    : "bg-gray-100 text-text-muted";

  return (
    <div
      className={`rounded-xl border-l-4 p-4 shadow-sm ${TYPE_COLOR[schedule.schedule_type]}`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${TYPE_BADGE[schedule.schedule_type]}`}
            >
              {TYPE_LABEL[schedule.schedule_type]}
            </span>
            <span className="text-sm font-semibold text-text">
              {schedule.company || "未知公司"}
            </span>
            {schedule.job_title && (
              <span className="text-sm text-text-muted">
                · {schedule.job_title}
              </span>
            )}
            <span
              className={`rounded-full px-1.5 py-0.5 text-[10px] ${sourceColor}`}
            >
              {sourceLabel}
            </span>
          </div>
          <div className="text-sm text-text">
            ⏰ {formatTime(schedule.event_time)}
            <span className="ml-2 text-xs text-text-muted">
              （{schedule.duration_minutes} 分钟）
            </span>
          </div>
          {schedule.meeting_link && (
            <a
              href={schedule.meeting_link}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-block max-w-full truncate text-xs text-primary-dark hover:underline"
            >
              🔗 会议/链接
            </a>
          )}
          {schedule.notes && (
            <div className="mt-1 text-xs text-text-muted">
              📝 {schedule.notes}
            </div>
          )}
          {schedule.reminders?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {schedule.reminders.map((r) => (
                <span
                  key={r.id}
                  className={`rounded-full px-2 py-0.5 text-[10px] ${
                    r.fired
                      ? "bg-gray-200 text-gray-500 line-through"
                      : "bg-primary-soft text-primary-ink"
                  }`}
                >
                  ⏰ {formatTime(r.remind_at)}
                  {r.fired ? " 已提醒" : ""}
                </span>
              ))}
            </div>
          )}
          {!schedule.verified_at && (
            <span className="mt-1 inline-block text-[10px] text-amber-800">
              ⚠️ 未验证
            </span>
          )}
        </div>
        <div className="flex shrink-0 flex-col gap-1">
          <button
            onClick={() => onEdit(schedule)}
            className="rounded-lg bg-primary-soft px-2 py-1 text-xs font-medium text-primary-ink hover:bg-primary/20"
          >
            编辑
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            onMouseLeave={() => setConfirming(false)}
            className={`rounded-lg px-2 py-1 text-xs disabled:opacity-50 ${
              confirming
                ? "bg-red-500 text-white hover:bg-red-600"
                : "bg-red-50 text-red-600 hover:bg-red-100"
            }`}
          >
            {deleting ? "删除中..." : confirming ? "确认删除？" : "删除"}
          </button>
        </div>
      </div>
      {deleteError && (
        <div className="mt-2 rounded-lg bg-red-50 border border-red-200 px-2 py-1 text-[11px] text-red-700">
          删除失败：{deleteError}
        </div>
      )}
    </div>
  );
}

// ---- 表单 / AI 提取弹窗（保留）----

interface FormState {
  schedule_type: ScheduleType;
  company: string;
  job_title: string;
  event_time_local: string;
  duration_minutes: number;
  meeting_link: string;
  notes: string;
}

const EMPTY_FORM: FormState = {
  schedule_type: "interview",
  company: "",
  job_title: "",
  event_time_local: "",
  duration_minutes: 60,
  meeting_link: "",
  notes: "",
};

function ScheduleFormModal({
  initial,
  title,
  submitLabel,
  aiBadge,
  onClose,
  onSubmit,
}: {
  initial: FormState;
  title: string;
  submitLabel: string;
  aiBadge?: ExtractedSchedule["confidence"] | null;
  onClose: () => void;
  onSubmit: (req: CreateScheduleRequest) => Promise<void>;
}) {
  const [form, setForm] = useState<FormState>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = <K extends keyof FormState>(key: K, val: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: val }));

  const handleSubmit = async () => {
    setError(null);
    if (!form.event_time_local) {
      setError("请填写事件时间");
      return;
    }
    const iso = localInputToIso(form.event_time_local);
    if (!iso) {
      setError("时间格式无效，请重新选择");
      return;
    }
    if (!form.company.trim() && !form.job_title.trim()) {
      setError("公司名和岗位名至少填写一个");
      return;
    }
    const req: CreateScheduleRequest = {
      schedule_type: form.schedule_type,
      event_time: iso,
      company: form.company.trim(),
      job_title: form.job_title.trim(),
      duration_minutes: form.duration_minutes,
      meeting_link: form.meeting_link.trim(),
      notes: form.notes.trim(),
      reminder_offsets_minutes: [120, 30],
    };
    setBusy(true);
    try {
      await onSubmit(req);
      onClose();
    } catch (e) {
      setError(extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">{title}</h3>
          {aiBadge && (
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${CONF_COLOR[aiBadge]}`}
            >
              ✨ AI {CONF_LABEL[aiBadge]}
            </span>
          )}
        </div>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-text-muted">日程类型</label>
            <div className="flex flex-wrap gap-2">
              {(["interview", "written", "assessment", "other"] as ScheduleType[]).map(
                (t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => set("schedule_type", t)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                      form.schedule_type === t
                        ? `${TYPE_BADGE[t]} ring-2 ring-offset-1 ring-primary`
                        : "bg-gray-100 text-text-muted hover:bg-gray-200"
                    }`}
                  >
                    {TYPE_LABEL[t]}
                  </button>
                )
              )}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-text-muted">公司名</label>
              <input
                value={form.company}
                onChange={(e) => set("company", e.target.value)}
                placeholder="公司名（选填，但建议填写）"
                className="w-full rounded-lg border border-line px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-text-muted">岗位名</label>
              <input
                value={form.job_title}
                onChange={(e) => set("job_title", e.target.value)}
                placeholder="如 后端开发工程师"
                className="w-full rounded-lg border border-line px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-text-muted">事件时间</label>
              <input
                type="datetime-local"
                value={form.event_time_local}
                onChange={(e) => set("event_time_local", e.target.value)}
                className="w-full rounded-lg border border-line px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-text-muted">时长（分钟）</label>
              <input
                type="number"
                min={1}
                max={1440}
                value={form.duration_minutes}
                onChange={(e) =>
                  set("duration_minutes", Number(e.target.value) || 60)
                }
                className="w-full rounded-lg border border-line px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-muted">
              会议 / 笔试 / 测评 链接
            </label>
            <input
              value={form.meeting_link}
              onChange={(e) => set("meeting_link", e.target.value)}
              placeholder="https://meeting.tencent.com/..."
              className="w-full rounded-lg border border-line px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-muted">备注</label>
            <textarea
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              placeholder="如：腾讯会议 二面 / HR 面 / 终面"
              rows={2}
              className="w-full rounded-lg border border-line px-3 py-2 text-sm"
            />
          </div>
          <div className="rounded-lg bg-primary-soft px-3 py-2 text-[11px] text-primary-ink">
            ⏰ 创建后将自动生成 2 条提醒：提前 2 小时 + 30 分钟
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-text-muted hover:bg-gray-100"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={busy}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-ink disabled:opacity-50"
          >
            {busy ? "提交中..." : submitLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function AIExtractModal({
  onClose,
  onExtracted,
}: {
  onClose: () => void;
  onExtracted: (extracted: ExtractedSchedule) => void;
}) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const extractFromEmail = useScheduleStore((s) => s.extractFromEmail);

  const handleExtract = async () => {
    setError(null);
    if (!body.trim()) {
      setError("请粘贴邮件正文");
      return;
    }
    setBusy(true);
    try {
      const extracted = await extractFromEmail(subject.trim(), body.trim());
      onExtracted(extracted);
      onClose();
    } catch (e) {
      setError(extractErrorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl">
        <h3 className="mb-2 text-lg font-semibold">✨ AI 智能建日程</h3>
        <p className="mb-4 text-xs text-text-muted">
          粘贴面试/笔试/测评邀请邮件正文，AI 自动识别公司、岗位、时间、会议链接，预填到表单后你可再编辑确认。
        </p>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-text-muted">
              邮件主题（可选）
            </label>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="如：字节跳动-后端开发工程师-面试邀请"
              className="w-full rounded-lg border border-line px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-muted">邮件正文</label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="粘贴邮件全文，AI 会自动提取：公司名、岗位、时间、会议链接等关键信息"
              rows={10}
              className="w-full rounded-lg border border-line px-3 py-2 font-mono text-xs"
            />
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-text-muted hover:bg-gray-100"
          >
            取消
          </button>
          <button
            onClick={handleExtract}
            disabled={busy}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-ink disabled:opacity-50"
          >
            {busy ? "AI 提取中..." : "✨ AI 提取并填表"}
          </button>
        </div>
      </div>
    </div>
  );
}

function extractedToForm(ex: ExtractedSchedule): FormState {
  return {
    schedule_type: ex.task_type,
    company: ex.company || "",
    job_title: ex.job_title || "",
    event_time_local: isoToLocalInput(ex.event_time),
    duration_minutes: ex.duration_minutes || 60,
    meeting_link: ex.meeting_link || "",
    notes: ex.notes || "",
  };
}

function scheduleToForm(s: Schedule): FormState {
  return {
    schedule_type: s.schedule_type,
    company: s.company || "",
    job_title: s.job_title || "",
    event_time_local: isoToLocalInput(s.event_time),
    duration_minutes: s.duration_minutes || 60,
    meeting_link: s.meeting_link || "",
    notes: s.notes || "",
  };
}

// ---- 主组件：日历视图 ----

export default function Schedules() {
  const { schedules, loading, error, loadSchedules, addSchedule, updateSchedule } =
    useScheduleStore();
  const [showCreate, setShowCreate] = useState(false);
  const [showAI, setShowAI] = useState(false);
  const [aiForm, setAiForm] = useState<FormState | null>(null);
  const [aiConf, setAiConf] = useState<ExtractedSchedule["confidence"] | null>(
    null
  );
  // 编辑中的日程
  const [editingSchedule, setEditingSchedule] = useState<Schedule | null>(null);

  // 当前显示的月份（默认今天所在月）
  const today = new Date();
  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth()); // 0-11

  // 选中的日期格（用于弹出当天日程列表）
  const [selectedCell, setSelectedCell] = useState<Cell | null>(null);

  useEffect(() => {
    void loadSchedules();
  }, [loadSchedules]);

  // 月份导航
  const goPrevMonth = () => {
    if (viewMonth === 0) {
      setViewMonth(11);
      setViewYear((y) => y - 1);
    } else {
      setViewMonth((m) => m - 1);
    }
  };
  const goNextMonth = () => {
    if (viewMonth === 11) {
      setViewMonth(0);
      setViewYear((y) => y + 1);
    } else {
      setViewMonth((m) => m + 1);
    }
  };
  const goToday = () => {
    setViewYear(today.getFullYear());
    setViewMonth(today.getMonth());
  };

  // 本月日程数（用于标题）
  const monthScheduleCount = useMemo(
    () =>
      schedules.filter((s) => {
        const d = new Date(s.event_time);
        return d.getFullYear() === viewYear && d.getMonth() === viewMonth;
      }).length,
    [schedules, viewYear, viewMonth]
  );

  const handleSubmit = async (req: CreateScheduleRequest) => {
    await addSchedule(req);
  };

  const handleUpdate = async (req: CreateScheduleRequest) => {
    if (!editingSchedule) return;
    const updateReq: UpdateScheduleRequest = {
      schedule_type: req.schedule_type,
      event_time: req.event_time,
      company: req.company,
      job_title: req.job_title,
      duration_minutes: req.duration_minutes,
      meeting_link: req.meeting_link,
      notes: req.notes,
    };
    await updateSchedule(editingSchedule.id, updateReq);
  };

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* 顶部操作栏 */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">日程日历</h2>
        <div className="flex gap-2">
          <button
            onClick={() => setShowAI(true)}
            className="rounded-lg bg-gradient-to-r from-primary to-primary-dark px-3 py-1.5 text-sm font-medium text-ink shadow-sm hover:opacity-90"
          >
            ✨ AI 智能建日程
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="rounded-lg bg-white border border-line px-3 py-1.5 text-sm font-medium text-text hover:bg-gray-50"
          >
            + 手动新建
          </button>
        </div>
      </div>

      {/* 自动化提示卡 */}
      <div className="rounded-xl border border-primary/30 bg-primary-soft/50 p-3 text-xs text-primary-ink">
        <div className="font-medium">💡 三种建日程方式，越往后越自动</div>
        <div className="mt-1 text-text-muted">
          ① 手动新建 — 自己填表；
          ② AI 智能建 — 粘贴邮件正文，AI 自动提取关键信息填表；
          ③ 邮件同步 — 已绑定的邮箱同步后自动生成待确认任务，一键确认即建日程。
        </div>
      </div>

      {/* 月份导航 */}
      <div className="flex items-center justify-between rounded-xl border border-line bg-white p-3">
        <button
          onClick={goPrevMonth}
          className="rounded-lg px-3 py-1.5 text-sm text-text-muted hover:bg-gray-100"
        >
          ← 上月
        </button>
        <div className="flex items-center gap-3">
          <span className="text-base font-semibold">
            {viewYear} 年 {viewMonth + 1} 月
          </span>
          <span className="text-xs text-text-muted">
            （本月 {monthScheduleCount} 个日程）
          </span>
          <button
            onClick={goToday}
            className="rounded-lg bg-primary-soft px-2 py-1 text-xs text-primary-ink hover:bg-primary/20"
          >
            今天
          </button>
        </div>
        <button
          onClick={goNextMonth}
          className="rounded-lg px-3 py-1.5 text-sm text-text-muted hover:bg-gray-100"
        >
          下月 →
        </button>
      </div>

      {/* 月历网格 */}
      {loading ? (
        <div className="rounded-xl border border-line bg-white p-8 text-center text-sm text-text-muted">
          加载中...
        </div>
      ) : (
        <MonthGrid
          year={viewYear}
          month={viewMonth}
          schedules={schedules}
          onSelectDay={(c) => setSelectedCell(c)}
        />
      )}

      {/* 图例 */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-white p-3 text-[11px] text-text-muted">
        <span className="font-medium text-text">图例：</span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-success" /> 面试
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-warning" /> 笔试
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-info" /> 测评
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-gray-500" /> 其他
        </span>
        <span className="ml-2 flex items-center gap-1">
          <span className="text-red-600">●</span> 法定节假日
        </span>
        <span className="flex items-center gap-1">
          <span className="text-amber-800">●</span> 传统节日
        </span>
        <span className="flex items-center gap-1">
          <span className="text-emerald-600">●</span> 节气
        </span>
      </div>

      {/* 当天日程弹窗 */}
      {selectedCell && (
        <DaySchedulesModal
          cell={selectedCell}
          onClose={() => setSelectedCell(null)}
          onEdit={(s) => {
            setEditingSchedule(s);
            setSelectedCell(null);
          }}
        />
      )}

      {/* AI 提取 / 新建 弹窗 */}
      {showAI && (
        <AIExtractModal
          onClose={() => setShowAI(false)}
          onExtracted={(ex) => {
            setAiForm(extractedToForm(ex));
            setAiConf(ex.confidence);
            setShowCreate(true);
          }}
        />
      )}
      {showCreate && (
        <ScheduleFormModal
          initial={aiForm ?? EMPTY_FORM}
          aiBadge={aiConf}
          title={aiForm ? "确认 AI 提取的日程" : "新建日程"}
          submitLabel={aiForm ? "确认创建" : "创建日程"}
          onClose={() => {
            setShowCreate(false);
            setAiForm(null);
            setAiConf(null);
          }}
          onSubmit={handleSubmit}
        />
      )}

      {/* 编辑日程弹窗 */}
      {editingSchedule && (
        <ScheduleFormModal
          initial={scheduleToForm(editingSchedule)}
          title="编辑日程"
          submitLabel="保存修改"
          onClose={() => setEditingSchedule(null)}
          onSubmit={handleUpdate}
        />
      )}
    </div>
  );
}
