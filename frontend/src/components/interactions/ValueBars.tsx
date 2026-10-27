import { memo, useMemo } from 'react';
import type { ValueBarData } from '../../types/interactions';
import { seriesColors, type VisualColor } from '../../lib/visualColors';
import { ProgressBar } from '../ui/ProgressBar';

function comparisons(bars: ValueBarData[]) {
  if (bars.every(bar => bar.group && bar.series)) return bars;
  // Backward-compatible presentation for clearly rectangular saved comparisons.
  // Keep original data/labels/receipts intact; never infer arbitrary partial sets.
  const parsed = bars.map(bar => { const match = /^(.{1,80}?)\s+[—–]\s+(.{1,80})$/.exec(bar.label); return match ? { ...bar, series: match[1], group: match[2] } : null; });
  if (parsed.some(bar => !bar)) return bars;
  const candidate = parsed as ValueBarData[];
  const series = new Set(candidate.map(bar => bar.series));
  const groups = new Set(candidate.map(bar => bar.group));
  if (series.size < 2 || series.size > 4 || groups.size * series.size !== bars.length) return bars;
  for (const group of groups) {
    const rows = candidate.filter(bar => bar.group === group);
    if (new Set(rows.map(bar => bar.series)).size !== series.size || rows.some(bar => bar.max !== rows[0].max || (bar.unit ?? '') !== (rows[0].unit ?? ''))) return bars;
  }
  return candidate;
}
export const ValueBars = memo(function ValueBars({ bars }: { bars: ValueBarData[] }) {
  const layout = useMemo(() => {
    const normalized = comparisons(bars); const colors = new Map<string, VisualColor>();
    for (const bar of normalized) if (bar.series && !colors.has(bar.series)) colors.set(bar.series, seriesColors[colors.size % seriesColors.length]);
    for (const bar of normalized) if (bar.series && bar.color) colors.set(bar.series, bar.color);
    const groups = new Map<string, ValueBarData[]>();
    normalized.forEach((bar, i) => { const key = bar.group || `single-${i}`; const group = groups.get(key) ?? []; group.push(bar); groups.set(key, group); });
    return { groups: [...groups.values()], colors };
  }, [bars]);
  return <>{layout.groups.map((group, i) => <div key={i} role={group[0].group ? 'group' : undefined} aria-label={group[0].group || undefined}>
    {group[0].group && <h4 className="mb-2 text-sm font-medium text-heading">{group[0].group}</h4>}
    <div className={group[0].group && group.length > 1 ? 'grid grid-cols-2 gap-4' : 'space-y-4'}>{group.map((bar, j) => <div key={j} className="min-w-0"><ProgressBar label={bar.series || bar.label} accessibleLabel={bar.group ? `${bar.series} — ${bar.group}` : bar.label} value={bar.value} max={bar.max} unit={bar.unit} color={bar.series ? layout.colors.get(bar.series) : bar.color ?? undefined} mode="meter" />{bar.note && <p className="mt-1 text-xs text-muted">{bar.note}</p>}</div>)}</div>
  </div>)}</>;
});
