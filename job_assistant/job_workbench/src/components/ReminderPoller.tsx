// 后台提醒轮询器：应用运行时每 60s 检查两类到期提醒,弹浏览器通知
// 1. 日程提醒(面试/笔试/测评)——来自 scheduleStore.pollDueReminders
// 2. 岗位截止提醒(3 天内截止的已收藏/已投递岗位)——来自 appStore.applications
import { useEffect, useRef } from "react";
import { useScheduleStore } from "../stores/scheduleStore";
import { useAppStore } from "../stores/appStore";

const POLL_INTERVAL = 60_000; // 60 秒
const DEADLINE_WARN_DAYS = 3; // 3 天内截止视为即将截止

// 计算距今天数(d-0=今天,d<0 已截止)
function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const target = new Date(iso.slice(0, 10) + "T23:59:59");
  if (Number.isNaN(target.getTime())) return null;
  const now = new Date();
  return Math.ceil(
    (target.getTime() - now.getTime()) / (24 * 60 * 60 * 1000)
  );
}

// 请求浏览器通知权限(懒,首次有提醒时才请求)
async function ensureNotificationPermission(): Promise<boolean> {
  if (!("Notification" in window)) return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  const result = await Notification.requestPermission();
  return result === "granted";
}

async function fireNotification(title: string, body: string) {
  const ok = await ensureNotificationPermission();
  if (!ok) return;
  try {
    new Notification(title, { body });
  } catch {
    // 通知失败静默
  }
}

export default function ReminderPoller() {
  const pollDueReminders = useScheduleStore((s) => s.pollDueReminders);
  const fireReminder = useScheduleStore((s) => s.fireReminder);
  const applications = useAppStore((s) => s.applications);
  const loadApplications = useAppStore((s) => s.loadApplications);
  const firedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;

    const checkSchedules = async () => {
      const reminders = await pollDueReminders();
      for (const r of reminders) {
        if (firedRef.current.has(`sch-${r.id}`)) continue;
        firedRef.current.add(`sch-${r.id}`);
        const title = `${r.company || ""} ${r.job_title || ""} ${
          r.schedule_type === "interview"
            ? "面试"
            : r.schedule_type === "written"
            ? "笔试"
            : "测评"
        }`;
        const body = `即将开始:${new Date(r.event_time).toLocaleString("zh-CN")}${
          r.meeting_link ? "\n链接:" + r.meeting_link : ""
        }`;
        void fireNotification(title, body);
        void fireReminder(r.id);
      }
    };

    const checkDeadlines = async () => {
      // 拉取最新投递记录(包含 deadline 字段)
      await loadApplications();
      for (const app of applications) {
        if (!app.deadline) continue;
        const d = daysUntil(app.deadline);
        if (d === null || d < 0 || d > DEADLINE_WARN_DAYS) continue;
        const key = `dl-${app.id}-${app.deadline}`;
        if (firedRef.current.has(key)) continue;
        firedRef.current.add(key);
        const title = `⏰ ${app.company_name || ""} ${d === 0 ? "今日截止" : `${d}天后截止`}`;
        const body = `${app.job_title || ""} ${app.deadline}\n投递状态:${
          app.status === "favorite" ? "已收藏未投递" : "已投递"
        }`;
        void fireNotification(title, body);
      }
    };

    const check = async () => {
      try {
        await Promise.all([checkSchedules(), checkDeadlines()]);
      } catch {
        // 静默
      }
    };

    void check();
    const timer = setInterval(() => {
      if (!cancelled) void check();
    }, POLL_INTERVAL);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [pollDueReminders, fireReminder, applications, loadApplications]);

  return null;
}
