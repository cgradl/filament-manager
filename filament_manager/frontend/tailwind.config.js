/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: 'rgb(var(--fm-surface) / <alpha-value>)',
          2: 'rgb(var(--fm-surface-2) / <alpha-value>)',
          3: 'rgb(var(--fm-surface-3) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--fm-accent) / <alpha-value>)',
          hover: 'rgb(var(--fm-accent-hover) / <alpha-value>)',
        },
      },
    },
  },
  plugins: [],
}
