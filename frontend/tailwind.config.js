/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      borderRadius: { control: 'var(--radius-control)', panel: 'var(--radius-panel)' },
      boxShadow: { panel: '0 2px 8px rgb(var(--shadow) / .04)', overlay: '0 12px 36px rgb(var(--shadow) / .14)' },
      colors: Object.fromEntries([
        'background', 'card', 'surface', 'input', 'border', 'border-strong',
        'border-hover', 'foreground', 'heading', 'body', 'muted', 'subtle',
        'hover', 'active', 'message', 'accent', 'accent-foreground', 'primary',
        'primary-hover', 'danger', 'overlay', 'shadow', 'popover', 'success', 'warning',
      ].map((name) => [name, `rgb(var(--${name}) / <alpha-value>)`])),
    },
  },
  plugins: [],
};
