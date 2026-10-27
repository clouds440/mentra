import { memo, useLayoutEffect, useRef, type ReactNode } from 'react';
import { useResolvedTheme } from '../theme/resolvedTheme';

function rgb(hex: string) { return [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16)); }
function luminance(values: number[]) { return values.map(value => { const x = value / 255; return x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4; }).reduce((sum, value, i) => sum + value * [.2126, .7152, .0722][i], 0); }
export function readableColor(hex: string, background: number[]): string {
  const source = rgb(hex); const back = luminance(background);
  const target = back > .179 ? 0 : 255;
  for (let step = 0; step <= 20; step++) {
    const candidate = source.map(value => Math.round(value + (target - value) * step / 20));
    const light = luminance(candidate);
    if ((Math.max(light, back) + .05) / (Math.min(light, back) + .05) >= 4.5) return `rgb(${candidate.join(',')})`;
  }
  return target ? '#ffffff' : '#000000';
}

export const ColorText = memo(function ColorText({ tone, hex, children }: { tone?: string; hex?: string; children?: ReactNode }) {
  if (hex) return <CustomColorText hex={hex}>{children}</CustomColorText>;
  const token = ['success', 'warning', 'danger'].includes(tone ?? '') ? tone : 'accent';
  return <span className="rich-color" style={{ color: `rgb(var(--rich-${token}))` }}>{children}</span>;
});

function CustomColorText({ hex, children }: { hex: string; children?: ReactNode }) {
  const ref = useRef<HTMLSpanElement>(null);
  const theme = useResolvedTheme();
  useLayoutEffect(() => {
    if (!/^#[\da-fA-F]{6}$/.test(hex) || !ref.current) return;
    const element = ref.current;
    function apply() {
      let parent: HTMLElement | null = element;
      let background = [255, 255, 255];
      while (parent) {
        const raw = getComputedStyle(parent).backgroundColor;
        const channels = raw.match(/[\d.]+/g)?.map(Number);
        if (channels && channels.length >= 3 && (channels.length < 4 || channels[3] === 1)) { background = channels.slice(0, 3); break; }
        parent = parent.parentElement;
      }
      element.style.color = readableColor(hex, background);
    }
    apply();
  }, [hex, theme]);
  return <span ref={ref} className="rich-color">{children}</span>;
}
