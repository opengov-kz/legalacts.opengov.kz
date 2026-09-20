import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: { page: "var(--surface-page)", card: "var(--surface-card)" },
        ink: { primary: "var(--ink-primary)", secondary: "var(--ink-secondary)", muted: "var(--ink-muted)" },
        gridline: "var(--gridline)",
        baseline: "var(--baseline)",
      },
    },
  },
  plugins: [],
};

export default config;
