import type { Config } from "tailwindcss";

// 求职搭子 · HR Dashboard 设计系统：深空蓝主色 + 暖橙强调。
// 颜色通过 CSS 变量注入（见 src/index.css），Tailwind 仅做 extend 映射。
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "var(--color-primary)",
          50: "var(--color-primary-50)",
          100: "var(--color-primary-100)",
          600: "var(--color-primary-600)",
        },
        accent: {
          DEFAULT: "var(--color-accent)",
          100: "var(--color-accent-100)",
          600: "var(--color-accent-600)",
        },
        success: "var(--color-success)",
        warning: "var(--color-warning)",
        danger: "var(--color-danger)",
        gray: {
          50: "var(--color-gray-50)",
          100: "var(--color-gray-100)",
          200: "var(--color-gray-200)",
          400: "var(--color-gray-400)",
          500: "var(--color-gray-500)",
          700: "var(--color-gray-700)",
          900: "var(--color-gray-900)",
        },
        sidebar: "var(--color-sidebar)",
        surface: "var(--color-surface)",
        // 向后兼容：旧代码使用的颜色名映射到新设计系统
        brand: {
          DEFAULT: "var(--color-accent)",
          50: "var(--color-accent-100)",
          100: "var(--color-accent-100)",
          500: "var(--color-accent)",
          600: "var(--color-accent-600)",
          700: "var(--color-accent-600)",
        },
        "slate-deep": "var(--color-gray-900)",
        cream: "var(--color-gray-50)",
        orange: {
          50: "var(--color-accent-100)",
          100: "var(--color-accent-100)",
          500: "var(--color-accent)",
          600: "var(--color-accent-600)",
          700: "var(--color-accent-600)",
        },
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
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
