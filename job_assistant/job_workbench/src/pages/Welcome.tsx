// 新用户引导页:登录后未上传简历时展示。
// 三步引导:产品介绍 → 上传简历 → 跳 Jobs 看推荐。
// 上传成功后自动跳 /;配额超限时显示友好提示 + "去岗位列表浏览"按钮。
// 用户选"稍后再说"会标记 onboarding_completed,下次不再被引导。
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ResumeUploader from "../components/ResumeUploader";
import { useResumeStore } from "../stores/resumeStore";

const ONBOARDING_KEY = "onboarding_completed";

function markOnboardingDone() {
  try {
    localStorage.setItem(ONBOARDING_KEY, "1");
  } catch {
    /* 静默 */
  }
}

export default function Welcome() {
  const navigate = useNavigate();
  const phase = useResumeStore((s) => s.phase);
  const activeResume = useResumeStore((s) => s.activeResume);
  const error = useResumeStore((s) => s.error);
  const [step, setStep] = useState<0 | 1 | 2>(0);

  // 简历上传完成(phase=done 且 activeResume 有值)→ 自动跳岗位列表
  if (phase === "done" && activeResume) {
    markOnboardingDone();
    navigate("/", { replace: true });
  }

  // 检测配额超限错误
  const isQuotaError =
    !!error && (error.includes("配额") || error.includes("上限"));

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 py-6 animate-fade-in">
      {/* 步骤指示器 */}
      <div className="flex items-center justify-center gap-2 text-xs">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={`h-1.5 w-8 rounded-full transition ${
              step >= i ? "bg-primary" : "bg-white/40"
            }`}
          />
        ))}
      </div>

      {step === 0 && (
        <div className="glass rounded-2xl p-8 text-center shadow-sm">
          <div className="text-5xl">👋</div>
          <h1 className="mt-4 text-2xl font-bold text-text">欢迎使用 Offer搭子</h1>
          <p className="mt-2 text-sm text-text-muted">
            你的 27 届校招工作台:看岗位 · 管投递 · 写简历 · 收面试
          </p>

          <div className="mt-6 grid grid-cols-3 gap-3 text-xs">
            <div className="rounded-xl bg-white/40 p-3">
              <div className="text-2xl">💼</div>
              <div className="mt-1 font-medium text-text">岗位列表</div>
              <div className="text-text-faint">每日同步秋招岗位</div>
            </div>
            <div className="rounded-xl bg-white/40 p-3">
              <div className="text-2xl">🎯</div>
              <div className="mt-1 font-medium text-text">AI 推荐</div>
              <div className="text-text-faint">按简历匹配评分</div>
            </div>
            <div className="rounded-xl bg-white/40 p-3">
              <div className="text-2xl">📋</div>
              <div className="mt-1 font-medium text-text">投递看板</div>
              <div className="text-text-faint">拖拽追踪进度</div>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setStep(1)}
            className="mt-6 rounded-pill bg-primary px-6 py-2 text-sm font-semibold text-ink hover:bg-primary-dark"
          >
            开始使用 →
          </button>
        </div>
      )}

      {step === 1 && (
        <div className="glass rounded-2xl p-6 shadow-sm">
          <h2 className="text-lg font-bold text-text">第 1 步:上传简历</h2>
          <p className="mt-1 text-sm text-text-muted">
            上传简历后,AI 才能为你匹配最合适的岗位。支持 PDF / 图片 / 文本格式。
          </p>

          <div className="mt-4">
            <ResumeUploader />
          </div>

          {/* 配额超限友好提示 */}
          {isQuotaError && (
            <div className="mt-4 rounded-xl bg-info-soft/50 p-4 text-sm text-info-dark">
              <div className="font-medium">📌 今日 AI 解析配额已用完</div>
              <p className="mt-1 text-xs text-info-dark/80">
                你可以先去「岗位列表」浏览全部秋招岗位,明日 0 点配额重置后再上传简历解析。
              </p>
              <button
                type="button"
                onClick={() => {
                  markOnboardingDone();
                  navigate("/", { replace: true });
                }}
                className="mt-3 rounded-pill bg-info px-4 py-1.5 text-xs font-semibold text-white hover:bg-info-dark"
              >
                去岗位列表浏览 →
              </button>
            </div>
          )}

          <div className="mt-4 flex justify-between text-xs">
            <button
              type="button"
              onClick={() => setStep(0)}
              className="text-text-muted hover:text-text"
            >
              ← 上一步
            </button>
            <button
              type="button"
              onClick={() => setStep(2)}
              className="text-text-muted hover:text-text"
            >
              稍后再说 →
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="glass rounded-2xl p-6 shadow-sm text-center">
          <div className="text-4xl">🚀</div>
          <h2 className="mt-3 text-lg font-bold text-text">准备就绪</h2>
          <p className="mt-1 text-sm text-text-muted">
            你可以稍后在「简历解析」上传简历。现在先去「岗位列表」浏览全部秋招岗位。
          </p>
          <button
            type="button"
            onClick={() => {
              markOnboardingDone();
              navigate("/", { replace: true });
            }}
            className="mt-4 rounded-pill bg-primary px-6 py-2 text-sm font-semibold text-ink hover:bg-primary-dark"
          >
            去看岗位 →
          </button>
        </div>
      )}
    </div>
  );
}
