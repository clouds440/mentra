import { Bar, BarChart } from 'recharts';
import { annotations, axes, ChartSize, margin, motion, palette, type ChartProps } from './shared';
export default function BarView({ spec }: ChartProps) {
  return <ChartSize><BarChart data={spec.data} margin={margin} accessibilityLayer title={spec.title}>{axes(spec)}{annotations(spec)}{spec.series.map((item, i) => <Bar key={item.dataKey} dataKey={item.dataKey} name={item.name} fill={palette[i]} stackId={spec.stacked ? 'values' : undefined} maxBarSize={64} {...motion(spec)} />)}</BarChart></ChartSize>;
}
