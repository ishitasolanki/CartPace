/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // A resource-allocation dashboard, not a diagnostic one -- teal for
        // the budget/pacing story, amber only for genuine warnings (budget
        // exhaustion, an unidentifiable certificate).
        ink: "#1a2332",
        accent: "#0f6466",
        warn: "#c9a227",
      },
    },
  },
  plugins: [],
};
