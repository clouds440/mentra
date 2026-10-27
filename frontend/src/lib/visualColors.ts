export const visualColors = {
  blue: 'rgb(var(--primary))', purple: 'rgb(var(--syntax-keyword))',
  green: 'rgb(var(--success))', amber: 'rgb(var(--warning))',
  red: 'rgb(var(--danger))', neutral: 'rgb(var(--muted))',
} as const;
export type VisualColor = keyof typeof visualColors;
export const seriesColors = Object.keys(visualColors) as VisualColor[];
export function visualColor(value?: string): string | undefined {
  if (!value) return undefined;
  return Object.prototype.hasOwnProperty.call(visualColors, value) ? visualColors[value as VisualColor] : /^#[\da-fA-F]{6}$/.test(value) ? value : undefined;
}
