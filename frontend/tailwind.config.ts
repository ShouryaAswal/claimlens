import type { Config } from "tailwindcss";

// ClaimLens design tokens
// Navy/slate foundation for a data-dense, trustworthy adjuster tool.
// Gold is the single accent reserved for "this needs a human" moments
// (forced-review banners, active selection) -- it never appears as
// decoration, only as attention. Risk colors are separate from the
// accent so risk semantics stay legible on their own.
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#0B1220",
          900: "#101A2E",
          800: "#16233D",
          700: "#1F2F4D",
          600: "#2D4266",
        },
        slate: {
          50: "#F7F8FA",
          100: "#EEF1F5",
          200: "#DFE4EB",
          300: "#C6CEDA",
          400: "#98A4B8",
          500: "#6B7A94",
          600: "#4E5C74",
          700: "#37435A",
          800: "#252E3F",
          900: "#161C28",
        },
        gold: {
          400: "#D9B24C",
          500: "#C99A3E",
          600: "#A97C2C",
          700: "#8A6323",
        },
        risk: {
          ok: "#0E9F6E",
          "ok-bg": "#E7F8F1",
          review: "#C77C0E",
          "review-bg": "#FDF2DE",
          high: "#D23B3B",
          "high-bg": "#FCE9E9",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "IBM Plex Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "monospace",
        ],
      },
      boxShadow: {
        panel: "0 1px 2px 0 rgb(16 26 46 / 0.06), 0 1px 3px 0 rgb(16 26 46 / 0.08)",
      },
      borderRadius: {
        md: "8px",
        lg: "10px",
      },
    },
  },
  plugins: [],
} satisfies Config;
