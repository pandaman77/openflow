/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // studio darkness — deep blue-green ink, not neutral black
        base: "#0b1416",
        surface: "#111c1f",
        raised: "#162428",
        line: "#1e3036",
        text: "#e9efec",
        subtext: "#7e928e",
        // voice is warm: amber carries all active/ready states
        amber: "#f2a35c",
        "amber-soft": "#f2a35c26",
        // recording is hot
        coral: "#e4626f",
        // ok/quiet-positive
        moss: "#8fb996",
      },
      fontFamily: {
        display: ['"Segoe UI Variable Display"', '"Segoe UI"', "system-ui", "sans-serif"],
        body: ['"Segoe UI Variable Text"', '"Segoe UI"', "system-ui", "sans-serif"],
        mono: ['"Cascadia Mono"', '"Cascadia Code"', "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
