import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        line: "var(--line)",
        ink: "var(--text-primary)",
        "ink-2": "var(--text-secondary)",
        "ink-3": "var(--text-muted)",
        accent: "var(--accent)",
        "accent-ink": "var(--accent-ink)",
      },
    },
  },
  plugins: [],
};
export default config;
