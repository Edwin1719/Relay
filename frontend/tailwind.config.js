/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          base: '#0d1117',
          surface: '#161b22',
          elevated: '#1c2128',
          hover: '#21262d',
          border: '#30363d',
        },
        accent: {
          DEFAULT: '#58a6ff',
          dim: '#388bfd',
          muted: '#1f6feb',
        },
        fg: {
          DEFAULT: '#e6edf3',
          muted: '#8b949e',
          dim: '#6e7681',
        },
        success: '#3fb950',
        warning: '#d29922',
        danger: '#f85149',
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Cascadia Code"', 'Consolas', 'monospace'],
      },
      animation: {
        'pulse-dot': 'pulse-dot 1.4s infinite ease-in-out',
      },
      keyframes: {
        'pulse-dot': {
          '0%, 80%, 100%': { opacity: '0' },
          '40%': { opacity: '1' },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
