/** @type {import('tailwindcss').Config} */
// 工作台视觉系统 design tokens：色板 / 字体 / 阴影 / 圆角 / 缓动函数
// 仅用于 MainBoard 与未来新页面；既有 style.css / fixed-rules.css 保持原状
export default {
  content: [
    './index.html',
    './src/**/*.{vue,ts,tsx,js}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-sans)'],
        mono: ['var(--font-mono)'],
      },
      colors: {
        canvas: '#F6F8FC',
        card: '#FFFFFF',
        subtle: '#F3F7FF',
        ink: {
          900: '#0F172A',
          700: '#475569',
          500: '#94A3B8',
          300: '#CBD5E1',
        },
        line: '#E5EAF3',
        accent: {
          DEFAULT: '#0F62FE',
          soft: '#EAF2FF',
          light: '#F3F7FF',
          ink: '#004EEB',
        },
        success: { DEFAULT: '#12B76A', soft: '#E8F8F0' },
        warning: { DEFAULT: '#FF7A1A', soft: '#FFF1E8' },
        danger: { DEFAULT: '#EF4444', soft: '#FEECEC' },
      },
      boxShadow: {
        'card-1': '0 12px 32px rgba(15, 23, 42, .06)',
        'card-2': '0 16px 40px rgba(15, 23, 42, .10)',
        button: '0 8px 18px rgba(15, 98, 254, .22)',
      },
      borderRadius: {
        field: '8px',
        card: '18px',
        panel: '24px',
      },
      transitionTimingFunction: {
        premium: 'cubic-bezier(.2, 0, 0, 1)',
      },
    },
  },
  // 关闭 Preflight 重置：避免与 Element Plus / 既有 4000+ 行 CSS 冲突
  // 我们只需要 utility 类，不需要 Tailwind 重置浏览器默认样式
  corePlugins: {
    preflight: false,
  },
  plugins: [],
}
