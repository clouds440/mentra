import { CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { ReactElement } from 'react';
import type { ChartSpec } from '../../../lib/chartSpec';
import { visualColor } from '../../../lib/visualColors';

export type ChartProps = { spec: ChartSpec; xName?: string };
export const palette = ['rgb(var(--primary))', 'rgb(var(--success))', 'rgb(var(--warning))', 'rgb(var(--danger))', 'rgb(var(--syntax-keyword))', 'rgb(var(--muted))'];
export function plotColor(spec: ChartSpec, index: number, series = true) {
  return visualColor(series ? spec.series[index]?.color : undefined) ?? visualColor(spec.colors?.[index % spec.colors.length]) ?? palette[index % palette.length];
}
export const margin = { top: 16, right: 20, bottom: 8, left: 0 };
const tick = { fill: 'rgb(var(--muted))', fontSize: 12 };
const tooltipStyle = { backgroundColor: 'rgb(var(--popover))', border: '1px solid rgb(var(--border))', borderRadius: 8, color: 'rgb(var(--foreground))' };
export function ChartSize({ children }: { children: ReactElement }) {
  return <ResponsiveContainer width="100%" height="100%" minWidth={0} debounce={60}>{children}</ResponsiveContainer>;
}
// Return actual Recharts children so its child discovery remains intact.
export function axes(spec: ChartSpec, scatter = false, xName?: string) {
  return [<CartesianGrid key="grid" stroke="rgb(var(--border))" strokeDasharray="3 3" vertical={false} />,
    <XAxis key="x" dataKey={scatter ? 'x' : spec.xKey} name={xName} type={scatter ? 'number' : 'category'} tick={tick} tickLine={false} axisLine={{ stroke: 'rgb(var(--border))' }} minTickGap={20} />,
    <YAxis key="y" dataKey={scatter ? 'y' : undefined} name={scatter ? spec.series.length === 1 ? spec.series[0].name : 'Value' : undefined} tick={tick} tickLine={false} axisLine={false} width={58} domain={['LineChart', 'ScatterChart'].includes(spec.type) ? ['auto', 'auto'] : [0, 'auto']} />];
}
export function motion(spec: ChartSpec) {
  return { isAnimationActive: spec.data.length * spec.series.length <= 120 ? 'auto' as const : false as const, animationDuration: 250, animationBegin: 0 };
}
export function annotations(spec: ChartSpec) {
  return [<Tooltip key="tooltip" isAnimationActive={false} formatter={(value, _name, item) => `${value}${spec.unit && !(spec.type === 'ScatterChart' && item.dataKey === 'x') ? ` ${spec.unit}` : ''}`} contentStyle={tooltipStyle} labelStyle={{ color: 'rgb(var(--foreground))' }} itemStyle={{ color: 'rgb(var(--foreground))' }} />,
    <Legend key="legend" wrapperStyle={{ fontSize: 12 }} formatter={value => <span className="text-foreground">{value}</span>} />,
  ];
}
