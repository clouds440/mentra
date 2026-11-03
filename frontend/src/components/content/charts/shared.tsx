import { AnimationControllerProvider, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis, type AnimationController } from 'recharts';
import type { ReactElement } from 'react';
import type { ChartSpec } from '../../../lib/chartSpec';
import { chartTick } from './format';
import { visualColor } from '../../../lib/visualColors';

export type ChartProps = { spec: ChartSpec; xName?: string };
export const palette = ['rgb(var(--primary))', 'rgb(var(--success))', 'rgb(var(--warning))', 'rgb(var(--danger))', 'rgb(var(--syntax-keyword))', 'rgb(var(--muted))'];
export function plotColor(spec: ChartSpec, index: number, series = true) {
  return visualColor(series ? spec.series[index]?.color : undefined) ?? visualColor(spec.colors?.[index % spec.colors.length]) ?? palette[index % palette.length];
}
export const margin = { top: 14, right: 12, bottom: 4, left: 0 };

const tick = { fill: 'rgb(var(--muted))', fontSize: 11 };
const tooltipStyle = { backgroundColor: 'rgb(var(--popover))', border: '1px solid rgb(var(--border))', borderRadius: 10, boxShadow: '0 4px 18px rgb(0 0 0 / .10)', color: 'rgb(var(--foreground))' };
// Prime zero-delay transitions with one display step, not preparatory frames.
// Otherwise per-frame input can cancel every transition before it visibly moves.
// Recharts owns interpolation and resumes from its latest visible geometry.
const chartAnimation: AnimationController = (clock, animation, publish) => {
  let cancel: (() => void) | undefined;
  let stopped = false;
  function step(now: number) {
    if (stopped) return;
    let wait = animation.tick(now);
    if (animation.getState() === 'pending' && wait === 0) wait = animation.tick(now);
    if (animation.getState() === 'active') {
      publish(animation.getInterpolated());
      if (animation.getProgress() === 1) { animation.complete(); return; }
    }
    if (animation.getState() !== 'completed') cancel = clock.setTimeout(step, wait);
  }
  const now = performance.now();
  const firstFrame = now - 1000 / 60;
  const delay = animation.tick(firstFrame);
  if (animation.getState() === 'pending' && delay === 0) animation.tick(firstFrame);
  step(now);
  return () => { stopped = true; cancel?.(); };
};
export function ChartSize({ children }: { children: ReactElement }) {
  return <AnimationControllerProvider value={chartAnimation}><ResponsiveContainer width="100%" height="100%" minWidth={0} debounce={60}>{children}</ResponsiveContainer></AnimationControllerProvider>;
}
// Return actual Recharts children so its child discovery remains intact.
export function axes(spec: ChartSpec, scatter = false, xName?: string) {
  const numericX = scatter || ['LineChart', 'AreaChart', 'ComposedChart'].includes(spec.type)
    && !spec.series.some(item => item.type === 'Bar') && spec.data.every(row => typeof row[spec.xKey] === 'number');
  return [<CartesianGrid key="grid" stroke="rgb(var(--border) / .62)" vertical={false} />,
    <XAxis key="x" dataKey={scatter ? 'x' : spec.xKey} name={xName} type={numericX ? 'number' : 'category'} domain={numericX ? ['dataMin', 'dataMax'] : undefined} tick={tick} tickFormatter={value => { const label = chartTick(value); return label.length > 18 ? label.slice(0, 17) + '…' : label; }} tickLine={false} axisLine={{ stroke: 'rgb(var(--border))' }} minTickGap={22} />,
    <YAxis key="y" dataKey={scatter ? 'y' : undefined} name={scatter ? spec.series.length === 1 ? spec.series[0].name : 'Value' : undefined} tick={tick} tickFormatter={chartTick} tickLine={false} axisLine={false} width={52} domain={['LineChart', 'ScatterChart'].includes(spec.type) ? ['auto', 'auto'] : [0, 'auto']} />];
}
export function motion(spec: ChartSpec) {
  return { isAnimationActive: spec.data.length * spec.series.length <= 120 ? 'auto' as const : false as const,
    animationDuration: spec.enableControls ? 100 : 250, animationEasing: spec.enableControls ? 'linear' as const : 'ease' as const, animationBegin: 0 };
}
export function annotations(spec: ChartSpec) {
  return [<Tooltip key="tooltip" isAnimationActive={false} formatter={(value, _name, item) => `${value}${spec.unit && !(spec.type === 'ScatterChart' && item.dataKey === 'x') ? ` ${spec.unit}` : ''}`} contentStyle={tooltipStyle} labelStyle={{ color: 'rgb(var(--foreground))' }} itemStyle={{ color: 'rgb(var(--foreground))' }} />,
    <Legend key="legend" iconType="circle" iconSize={7} wrapperStyle={{ fontSize: 12, paddingTop: 4, lineHeight: 1.5 }} formatter={value => <span className="text-foreground">{value}</span>} />,
  ];
}
