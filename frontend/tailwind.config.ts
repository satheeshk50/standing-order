import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0b0e14",
        panel: "#141922",
        edge: "#232b39",
      },
    },
  },
  plugins: [],
} satisfies Config;
