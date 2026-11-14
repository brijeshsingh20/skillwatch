/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        midnight: { 950: "#02030A", 900: "#05070F", 800: "#0A0F24" },
        cobalt: { DEFAULT: "#1F4BFF", 400: "#3B6BFF", 300: "#7DA2FF" },
        acid: "#C6FF00", // acid lime: highlights only
      },
      boxShadow: {
        glow: "0 10px 40px -12px rgba(31,75,255,0.45)",
        "glow-lime": "0 0 28px 2px rgba(198,255,0,0.40)",
      },
    },
  },
  plugins: [],
};