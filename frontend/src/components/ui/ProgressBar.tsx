import { cn } from '../../utils/cn';
import { visualColor, type VisualColor } from '../../lib/visualColors';
const numberFormat = new Intl.NumberFormat(undefined, { maximumSignificantDigits: 12 });
const scientificFormat = new Intl.NumberFormat(undefined, { notation: 'scientific', maximumSignificantDigits: 6 });

export function valueText(value: number, max: number, unit = '') {
  const format = (number: number) => (Math.abs(number) >= 1e9 || number !== 0 && Math.abs(number) < 1e-4 ? scientificFormat : numberFormat).format(number);
  return `${format(value)} / ${format(max)}${unit ? ` ${unit}` : ''} · ${format(value / max * 100)}%`;
}

/** Static numbers and domain-owned progress share a visual, never a data source. */
export function ProgressBar({ label, value, max, unit, mode = 'progress', showValue = true, className, color, accessibleLabel }: {
  label: string; value?: number; max?: number; unit?: string; mode?: 'progress' | 'meter'; showValue?: boolean; className?: string; color?: VisualColor; accessibleLabel?: string;
}) {
  const known = value != null && max != null && Number.isFinite(value) && Number.isFinite(max) && max > 0 && value >= 0 && value <= max;
  if (!known && mode === 'meter') return null;
  const description = known ? valueText(value!, max!, unit) : 'In progress';
  return <div className={cn('value-bar space-y-1.5', className)}>
    {showValue && <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm"><span className="font-medium text-heading">{label}</span><span className="tabular-nums text-muted">{description}</span></div>}
    <div role={mode === 'meter' ? 'meter' : 'progressbar'} aria-label={accessibleLabel ?? label} aria-valuemin={0} aria-valuemax={known ? max : undefined} aria-valuenow={known ? value : undefined} aria-valuetext={description} className="h-1.5 overflow-hidden rounded-full bg-border">
      <div className={cn('h-full rounded-full bg-accent transition-[width] duration-150 motion-reduce:transition-none', !known && 'w-1/3')} style={{ width: known ? `${value! / max! * 100}%` : undefined, backgroundColor: visualColor(color) }} />
    </div>
  </div>;
}
