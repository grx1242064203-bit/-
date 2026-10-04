// 网申自动填写工具推荐页
import { openExternalUrl } from "../utils/link";

const NOWCODER_INTRO_URL = "https://www.nowcoder.com/my/resume-plugin-intro";
const NOWCODER_CHROME_URL =
  "https://chromewebstore.google.com/detail/牛客网申助手-免费ai网申自动/djdbmjmjjimlgojgmjcnjkljnhnnplhf";
const NOWCODER_TUTORIAL_URL = "https://www.nowcoder.com/discuss/1606946";

export default function AutoFill() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      {/* 顶部说明 */}
      <div className="glass-soft rounded-2xl p-6">
        <h2 className="text-lg font-semibold text-text">为什么需要网申自动填写工具？</h2>
        <p className="mt-2 text-sm leading-relaxed text-text-muted">
          每家公司的投递官网都要重新填一遍简历信息（教育经历、实习经历、项目经历……），重复劳动耗时又容易出错。
          我们<span className="font-medium text-text">不重复造轮子</span>，推荐使用成熟的浏览器插件自动填表，
          我们负责<span className="font-medium text-text">岗位发现、进度追踪、邮件同步、日程提醒</span>，形成完整闭环。
        </p>
      </div>

      {/* 推荐工具卡片 */}
      <div className="glass-strong rounded-2xl border border-primary/20 p-6 shadow-md">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-2xl">🐂</span>
              <h3 className="text-xl font-bold text-text">牛客网申助手</h3>
              <span className="rounded-full bg-success-soft px-2 py-0.5 text-xs font-medium text-success">
                推荐 · 免费
              </span>
            </div>
            <p className="mt-1 text-sm text-text-muted">
              免费 AI 网申自动填写工具，支持 Chrome / Edge 浏览器，智能识别 90%+ 国内招聘官网表单。
            </p>
          </div>
          <button
            type="button"
            onClick={() => openExternalUrl(NOWCODER_INTRO_URL)}
            className="shrink-0 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-ink transition hover:bg-primary-light"
          >
            官网介绍
          </button>
        </div>

        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          {/* 优点 */}
          <div className="rounded-xl bg-success-soft/40 p-4">
            <div className="mb-2 text-sm font-semibold text-success">✅ 优点</div>
            <ul className="space-y-1.5 text-sm text-text">
              <li>· 免费，无内购</li>
              <li>· 支持 Moka / 北森 / 飞书招聘等主流系统</li>
              <li>· 自带简历解析（传 PDF 自动填）</li>
              <li>· 一次录入，所有官网通用</li>
            </ul>
          </div>
          {/* 局限 */}
          <div className="rounded-xl bg-warning-soft/40 p-4">
            <div className="mb-2 text-sm font-semibold text-warning">⚠️ 局限</div>
            <ul className="space-y-1.5 text-sm text-text">
              <li>· 不填开放性问题（自我介绍、为什么选我们）</li>
              <li>· 不追踪投递进度</li>
              <li>· 一份数据投所有岗位，无法定制</li>
              <li>· 极少数自建系统可能识别不全</li>
            </ul>
          </div>
        </div>

        {/* 安装 */}
        <div className="mt-5 rounded-xl border border-dashed border-text-muted/30 p-4">
          <div className="mb-2 text-sm font-semibold text-text">🔧 安装</div>
          <p className="text-sm text-text-muted">
            适合国内校招 / 社招，直接从 Chrome 应用商店或 Edge 加载项安装：
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => openExternalUrl(NOWCODER_CHROME_URL)}
              className="rounded-lg bg-ink px-3 py-1.5 text-xs text-white transition hover:opacity-90"
            >
              Chrome 应用商店
            </button>
            <button
              type="button"
              onClick={() => openExternalUrl(NOWCODER_INTRO_URL)}
              className="rounded-lg bg-white/60 px-3 py-1.5 text-xs text-text transition hover:bg-white"
            >
              查看更多安装方式
            </button>
          </div>
        </div>

        {/* 使用教程 */}
        <div className="mt-5 rounded-xl bg-info-soft/30 p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="text-sm font-semibold text-text">📖 使用教程（3 步）</div>
            <button
              type="button"
              onClick={() => openExternalUrl(NOWCODER_TUTORIAL_URL)}
              className="text-xs text-primary-dark underline-offset-2 hover:underline"
            >
              官方图文教程 →
            </button>
          </div>
          <ol className="space-y-3 text-sm text-text">
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-ink">
                1
              </span>
              <div>
                <div className="font-medium">安装插件并登录牛客账号</div>
                <div className="text-text-muted">
                  安装后点击浏览器右上角插件图标，用牛客账号登录（没有账号需先注册）。
                </div>
              </div>
            </li>
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-ink">
                2
              </span>
              <div>
                <div className="font-medium">填写或导入简历信息</div>
                <div className="text-text-muted">
                  在插件里填写基础信息、教育经历、实习经历、项目经历、技能等；
                  也可以直接上传 PDF 简历，插件自动解析填充。
                </div>
              </div>
            </li>
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-ink">
                3
              </span>
              <div>
                <div className="font-medium">打开投递页面，一键填表</div>
                <div className="text-text-muted">
                  在我们的「岗位列表」点击 📮 投递按钮，会自动打开公司投递页面，
                  插件识别到表单后点击「一键填写」即可，最后手动检查并提交。
                </div>
              </div>
            </li>
          </ol>
        </div>
      </div>

      {/* 与 Offer搭子 的配合 */}
      <div className="glass-soft rounded-2xl p-6">
        <h3 className="text-lg font-semibold text-text">🔗 与 Offer搭子 配合使用</h3>
        <div className="mt-4 space-y-3">
          <div className="flex gap-3">
            <span className="text-xl">📍</span>
            <div className="text-sm text-text">
              <span className="font-medium">岗位列表</span>
              浏览并收藏感兴趣的岗位，点击 📮 投递后自动打开投递链接。
            </div>
          </div>
          <div className="flex gap-3">
            <span className="text-xl">⚡</span>
            <div className="text-sm text-text">
              <span className="font-medium">牛客插件</span>
              在打开的投递页面自动填表，提交后关闭页面。
            </div>
          </div>
          <div className="flex gap-3">
            <span className="text-xl">📧</span>
            <div className="text-sm text-text">
              <span className="font-medium">邮件同步</span>
              测评 / 笔试 / 面试邀请邮件会被自动识别，待你确认后更新投递阶段并创建日程提醒。
            </div>
          </div>
          <div className="flex gap-3">
            <span className="text-xl">📋</span>
            <div className="text-sm text-text">
              <span className="font-medium">投递控制台</span>
              查看所有投递进度（收藏 → 投递 → 测评 → 面试 → offer），一目了然。
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
