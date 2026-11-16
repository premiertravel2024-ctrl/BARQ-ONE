/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['Inter','Cairo','system-ui','sans-serif'], code: ['JetBrains Mono','monospace'] },
      colors: {
        base:'var(--bg-base)',surface:'var(--bg-surface)',elevated:'var(--bg-elevated)',
        primary:'var(--text-primary)',secondary:'var(--text-secondary)',muted:'var(--text-muted)',
        stroke:'var(--border-color)',accent:'rgb(var(--accent-rgb) / <alpha-value>)',success:'rgb(var(--success-rgb) / <alpha-value>)',warning:'rgb(var(--warning-rgb) / <alpha-value>)',danger:'rgb(var(--danger-rgb) / <alpha-value>)'
      },
      borderRadius:{sm:'8px',DEFAULT:'12px',lg:'16px',xl:'24px'},
      boxShadow:{soft:'var(--shadow-soft)',float:'var(--shadow-float)'}
    }
  },plugins:[]
};
