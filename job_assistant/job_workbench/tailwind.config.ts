import type { Config } from "tailwindcss";

// 暖橙色主题：主色 #F97316，深石板 #0F172A，米白底 #FAFAF9，圆角 16px+。
// 颜色通过 CSS 变量注入（见 src/index.css），Tailwind 仅做 extend 映射。
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "var(--color-brand)",
          50: "var(--color-brand-50)",
          100: "var(--color-brand-100)",
          500: "var(--color-brand)",
          600: "var(--color-brand-600)",
          700: "var(--color-brand-700)",
        },
        slate: {
          deep: "var(--color-slate-deep)",
        },
        cream: "var(--color-cream)",
      },
      borderRadius: {
        card: "16px",
        xl: "16px",
        "2xl": "20px",
        "3xl": "24px",
      },
      boxShadow: {
        card: "0 8px 32px -12px rgba(15, 23, 42, 0.18)",
      },
      fontFamily: {
        sans: [
          "Inter",
          "PingFang SC",
          "Microsoft YaHei",
          "system-ui",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;
