// Verelo Tailwind preset (Tailwind 3.x). Load tokens/tokens.css first; every value here points at its CSS variable,
// so light/dark switching happens in CSS, not in Tailwind.
// Usage: tailwind.config.js -> module.exports = { presets: [require('./verelo-design-system/tokens/tailwind.preset.js')], content: [...] }
module.exports = {
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        'brand-navy': 'var(--brand-navy)',
        'brand-teal': 'var(--brand-teal)',
        'canvas': 'var(--canvas)',
        'surface': 'var(--surface)',
        'surface-sunken': 'var(--surface-sunken)',
        'brand-panel': 'var(--brand-panel)',
        'on-brand-panel': 'var(--on-brand-panel)',
        'border': 'var(--border)',
        'border-strong': 'var(--border-strong)',
        'ink': 'var(--ink)',
        'ink-muted': 'var(--ink-muted)',
        'accent': 'var(--accent)',
        'accent-strong': 'var(--accent-strong)',
        'accent-text': 'var(--accent-text)',
        'accent-soft': 'var(--accent-soft)',
        'on-accent': 'var(--on-accent)',
        'highlight': 'var(--highlight)',
        'recording': 'var(--recording)'
      },
      spacing: {
        '1': 'var(--space-1)',
        '2': 'var(--space-2)',
        '4': 'var(--space-4)',
        '6': 'var(--space-6)'
      },
      borderRadius: {
        'sm': 'var(--radius-sm)',
        'md': 'var(--radius-md)',
        'lg': 'var(--radius-lg)',
        'pill': 'var(--radius-pill)'
      },
      fontFamily: {
        'sans': ['var(--font-sans)'],
        'manrope': ['var(--font-manrope)'],
        'serif': ['var(--font-serif)'],
        'mono': ['var(--font-mono)']
      },
      fontSize: {
        'display': ['28px', { lineHeight: '34px', fontWeight: '700', letterSpacing: '-0.02em' }],
        'title': ['20px', { lineHeight: '28px', fontWeight: '700', letterSpacing: '-0.01em' }],
        'heading': ['15px', { lineHeight: '22px', fontWeight: '600' }],
        'body': ['14px', { lineHeight: '21px', fontWeight: '400' }],
        'small': ['12px', { lineHeight: '16px', fontWeight: '600' }],
        'quote': ['17px', { lineHeight: '26px', fontWeight: '400' }],
        'timestamp': ['12px', { lineHeight: '18px', fontWeight: '400' }]
      },
    },
  },
};
