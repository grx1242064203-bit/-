// 后台提醒轮询器：应用运行时每 60s 检查到期提醒，弹窗通知
import { useEffect, useRef } from "react";
import { useScheduleStore } from "../stores/scheduleStore";

const POLL_INTERVAL = 60_000; // 60 秒

export default function ReminderPoller() {
  const pollDueReminders = useScheduleStore((s) => s.pollDueReminders);
  const fireReminder = useScheduleStore((s) => s.fireReminder);
  const firedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      const reminders = await pollDueReminders();
      for (const r of reminders) {
        if (firedRef.current.has(r.id)) continue;
        firedRef.current.add(r.id);

        // 浏览器通知
        try {
          const title = `${r.company || ""} ${r.job_title || ""} ${
            r.schedule_type === "interview" ? "面试" : r.schedule_type === "written" ? "笔试" : "测评"
          }`;
          const body = `即将开始：${new Date(r.event_time).toLocaleString("zh-CN")}${
            r.meeting_link ? "\n链接：" + r.meeting_link : ""
          }`;

          if ("Notification" in window && Notification.permission === "granted") {
            new Notification(title, { body });
          } else if ("Notification" in window && Notification.permission !== "denied") {
            await Notification.requestPermission();
            if (Notification.permission === "granted") {
              new Notification(title, { body });
            }
          }
        } catch {
          // 通知失败静默
        }

        // 标记已触发
        void fireReminder(r.id);
      }
    };

    // 立即检查一次
    void check();
    const timer = setInterval(() => {
      if (!cancelled) void check();
    }, POLL_INTERVAL);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [pollDueReminders, fireReminder]);

  return null;
}
