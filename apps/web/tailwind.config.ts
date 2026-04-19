import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        "bg-soft": "var(--bg-soft)",
        "bg-muted": "var(--bg-muted)",
        "bg-tinted": "var(--bg-tinted)",
        fg1: "var(--fg1)",
        fg2: "var(--fg2)",
        fg3: "var(--fg3)",
        primary: "var(--primary)",
        "primary-hover": "var(--primary-hover)",
        "primary-pressed": "var(--primary-pressed)",
        "primary-soft": "var(--primary-soft)",
        accent: "var(--accent)",
        border: "var(--border)",
        success: "var(--ai-success)",
        warning: "var(--ai-warning)",
        danger: "var(--ai-danger)",
        "teal-900": "var(--ai-teal-900)",
        "teal-700": "var(--ai-teal-700)",
        "teal-600": "var(--ai-teal-600)",
        "teal-400": "var(--ai-teal-400)",
        "teal-200": "var(--ai-teal-200)",
        "teal-100": "var(--ai-teal-100)",
        "teal-50": "var(--ai-teal-50)",
      },
      fontFamily: {
        display: "var(--font-display)",
        sans: "var(--font-sans)",
        serif: "var(--font-serif)",
        subtext: "var(--font-subtext)",
        mono: "var(--font-mono)",
      },
      fontSize: {
        "display-xl": ["clamp(2.25rem, 4vw, 3.75rem)", { lineHeight: "1.15" }],
        "display-lg": ["clamp(1.875rem, 3vw, 2.75rem)", { lineHeight: "1.15" }],
      },
      borderRadius: {
        xs: "var(--radius-xs)",
        sm: "var(--radius-sm)",
        DEFAULT: "var(--radius)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        card: "var(--radius-xl)",
        pill: "var(--radius-pill)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        glow: "var(--shadow-glow)",
        "glow-strong": "var(--shadow-glow-strong)",
      },
      transitionTimingFunction: {
        ease: "var(--ease-out)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(10px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-teal": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.7", transform: "scale(1.15)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
      },
      animation: {
        "fade-in": "fade-in 500ms var(--ease-out)",
        "pulse-teal": "pulse-teal 2s ease-in-out infinite",
        float: "float 3s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
