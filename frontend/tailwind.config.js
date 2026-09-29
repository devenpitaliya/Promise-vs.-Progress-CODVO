/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // Design tokens: use these names instead of raw hex values in components.
      colors: {
        brand: { DEFAULT: '#315BEF', hover: '#284FD8', soft: '#EEF3FF', ring: '#C7D7FE' },
        ink: '#17233B',
        body: '#334155',
        muted: '#64748B',
        subtle: '#94A3B8',
        line: { DEFAULT: '#E2E8F0', strong: '#CBD5E1' },
        canvas: '#F8FAFC',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
};
