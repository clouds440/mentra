/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: Object.fromEntries([
        'background', 'card', 'surface', 'input', 'border', 'border-strong',
        'border-hover', 'foreground', 'heading', 'body', 'muted', 'subtle',
        'hover', 'active', 'message', 'accent', 'accent-foreground', 'primary',
        'primary-hover', 'danger', 'overlay', 'shadow', 'popover',
      ].map((name) => [name, `rgb(var(--${name}) / <alpha-value>)`])),
    },
  },
  plugins: [],
};
