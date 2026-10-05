import type { Config } from "tailwindcss";

// Offer搭子 · Crextio 风格设计系统：暖奶油黄主色 + 白卡片 + 大圆角。
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 主色：暖奶油黄
        primary: {
          DEFAULT: "var(--color-primary)",
          dark: "var(--color-primary-dark)",
          ink: "var(--color-primary-ink)",  // 浅黄底上的深字色（对比度 WCAG AA+）
          light: "var(--color-primary-light)",
          soft: "var(--color-primary-soft)",
        },
        // 深色（导航激活、深色卡片）
        ink: {
          DEFAULT: "var(--color-ink)",
          soft: "var(--color-ink-soft)",
        },
        // 语义色
        success: {
          DEFAULT: "var(--color-success)",
          dark: "var(--color-success-dark)",
          soft: "var(--color-success-soft)",
        },
        warning: {
          DEFAULT: "var(--color-warning)",
          dark: "var(--color-warning-dark)",
          soft: "var(--color-warning-soft)",
        },
        danger: {
          DEFAULT: "var(--color-danger)",
          soft: "var(--color-danger-soft)",
        },
        info: {
          DEFAULT: "var(--color-info)",
          dark: "var(--color-info-dark)",
          soft: "var(--color-info-soft)",
        },
        // 文本色阶
        text: {
          DEFAULT: "var(--color-text)",
          muted: "var(--color-text-muted)",
          faint: "var(--color-text-faint)",
        },
        // 边框
        border: {
          DEFAULT: "var(--color-border)",
          strong: "var(--color-border-strong)",
        },
        line: "var(--color-line)",
        // 表面
        surface: {
          DEFAULT: "var(--color-surface)",
          soft: "var(--color-surface-soft)",
        },
        bg: "var(--color-bg)",

        // —— 向后兼容：旧代码里用到的颜色名，映射到新主题 ——
        // 旧 primary(深空蓝) 不再使用；保留别名指向新主色以避免编译失败
        accent: {
          DEFAULT: "var(--color-primary)",
          100: "var(--color-primary-soft)",
          600: "var(--color-primary-dark)",
        },
        brand: {
          DEFAULT: "var(--color-primary)",
          50: "var(--color-primary-soft)",
          100: "var(--color-primary-soft)",
          500: "var(--color-primary)",
          600: "var(--color-primary-dark)",
          700: "var(--color-primary-dark)",
        },
        orange: {
          50: "var(--color-primary-soft)",
          100: "var(--color-primary-soft)",
          500: "var(--color-primary)",
          600: "var(--color-primary-dark)",
          700: "var(--color-primary-dark)",
        },
        gray: {
          50: "var(--color-surface-soft)",
          100: "var(--color-line)",
          200: "var(--color-border)",
          300: "var(--color-border-strong)",
          400: "var(--color-text-faint)",
          500: "var(--color-text-muted)",
          600: "var(--color-text-muted)",
          700: "var(--color-text)",
          900: "var(--color-text)",
        },
        sidebar: "var(--color-surface)",
        "slate-deep": "var(--color-text)",
        cream: "var(--color-surface-soft)",
        // slate 系列全部映射到暖灰色阶，保证旧组件一致渲染
        slate: {
          50: "var(--color-surface-soft)",
          100: "var(--color-line)",
          200: "var(--color-border)",
          300: "var(--color-border-strong)",
          400: "var(--color-text-faint)",
          500: "var(--color-text-muted)",
          600: "var(--color-text-muted)",
          700: "var(--color-text)",
          deep: "var(--color-text)",
        },
      },
      borderRadius: {
        xs: "var(--radius-xs)",
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        pill: "var(--radius-pill)",
        card: "var(--radius-lg)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        card: "var(--shadow-md)",
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "PingFang SC",
          "Hiragino Sans GB",
          "Microsoft YaHei",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;
