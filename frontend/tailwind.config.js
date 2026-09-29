/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ee",
          100: "#dce8de",
          200: "#c1d3c5",
          300: "#9fb9a7",
          400: "#769987",
          500: "#4f7a67",
          600: "#285d4e",
          700: "#1d4e42",
          800: "#173f36",
          900: "#12352e",
        },
      },
    },
  },
  plugins: [],
};
