// 日程与提醒视图
import { useEffect } from "react";
import { useScheduleStore } from "../stores/scheduleStore";
import type { Schedule, ScheduleType } from "../api/schedules";

const TYPE_LABEL: Record<ScheduleType, string> = {
  assessment: "测评",
  written: "笔试",
  interview: "面试",
};

const TYPE_COLOR: Record<ScheduleType, string> = {
  assessment: "border-l-info bg-info-soft",
  written: "border-l-warning bg-warning-soft",
  interview: "border-l-success bg-success-soft",
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

function ScheduleCard({ schedule }: { schedule: Schedule }) {
  const removeSchedule = useScheduleStore((s) => s.removeSchedule);

  const handleDelete = () => {
    if (confirm("确定删除此日程？删除后关联提醒也会清除。")) {
      void removeSchedule(schedule.id);
    }
  };

  return (
    <div className={`rounded-xl border-l-4 p-4 shadow-sm ${TYPE_COLOR[schedule.schedule_type]}`}>
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="mb-1 flex items-center gap-2">
            <span className="text-xs font-medium text-text-muted">
              {TYPE_LABEL[schedule.schedule_type]}
            </span>
            <span className="text-sm font-semibold text-text">
              {schedule.company || "未知公司"}
            </span>
            {schedule.job_title && (
              <span className="text-sm text-text-muted">· {schedule.job_title}</span>
            )}
          </div>
          <div className="text-sm text-text">⏰ {formatTime(schedule.event_time)}</div>
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
          {schedule.reminders?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {schedule.reminders.map((r) => (
                <span
                  key={r.id}
                  className={`rounded-full px-2 py-0.5 text-[10px] ${
                    r.fired
                      ? "bg-gray-200 text-gray-500 line-through"
                      : "bg-primary-soft text-primary-dark"
                  }`}
                >
                  ⏰ {formatTime(r.remind_at)}
                  {r.fired ? " 已提醒" : ""}
                </span>
              ))}
            </div>
          )}
          {!schedule.verified_at && (
            <span className="mt-1 inline-block text-[10px] text-amber-600">
              ⚠️ 未验证
            </span>
          )}
        </div>
        <button
          onClick={handleDelete}
          className="rounded-lg bg-red-50 px-2 py-1 text-xs text-red-500 hover:bg-red-100"
        >
          删除
        </button>
      </div>
    </div>
  );
}

export default function Schedules() {
  const { schedules, loading, error, loadSchedules } = useScheduleStore();

  useEffect(() => {
    void loadSchedules();
  }, [loadSchedules]);

  const upcoming = schedules.filter(
    (s) => new Date(s.event_time).getTime() >= Date.now()
  );
  const past = schedules.filter(
    (s) => new Date(s.event_time).getTime() < Date.now()
  );

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600">{error}</div>
      )}

      <section className="rounded-2xl border border-line bg-white/60 p-5 backdrop-blur">
        <h2 className="mb-4 text-base font-semibold">
          即将到来 <span className="text-sm text-text-muted">({upcoming.length})</span>
        </h2>
        {loading ? (
          <p className="py-8 text-center text-sm text-text-muted">加载中...</p>
        ) : upcoming.length === 0 ? (
          <p className="py-8 text-center text-sm text-text-muted">暂无即将到来的日程</p>
        ) : (
          <div className="space-y-3">
            {upcoming.map((s) => (
              <ScheduleCard key={s.id} schedule={s} />
            ))}
          </div>
        )}
      </section>

      {past.length > 0 && (
        <section className="rounded-2xl border border-line bg-white/60 p-5 backdrop-blur">
          <h2 className="mb-4 text-base font-semibold text-text-muted">
            已过期 <span className="text-sm">({past.length})</span>
          </h2>
          <div className="space-y-3 opacity-60">
            {past.map((s) => (
              <ScheduleCard key={s.id} schedule={s} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
