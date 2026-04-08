module.exports = {
  content: ["./app/frontend/**/*.{html,js}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Avenir Next", "Helvetica Neue", "sans-serif"],
      },
    },
  },
  plugins: [require("daisyui")],
  daisyui: {
    logs: false,
    themes: [
      {
        niwaki: {
          primary: "#2c6b4f",
          "primary-content": "#f6f4ed",
          secondary: "#8a6c45",
          "secondary-content": "#fffaf3",
          accent: "#5f8f7a",
          "accent-content": "#0f1713",
          neutral: "#25231f",
          "neutral-content": "#f5f1e8",
          "base-100": "#fffdf9",
          "base-200": "#f4f1ea",
          "base-300": "#e5ddd2",
          "base-content": "#1e1d1a",
          info: "#3c718f",
          success: "#2c6b4f",
          warning: "#8a5d07",
          error: "#b6543b",
          "--rounded-box": "1rem",
          "--rounded-btn": "0.9rem",
          "--rounded-badge": "1.9rem",
          "--animation-btn": "0.18s",
          "--border-btn": "1px",
          "--tab-border": "1px",
          "--tab-radius": "0.9rem",
        },
      },
    ],
  },
};
