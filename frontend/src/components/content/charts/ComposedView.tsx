import { Area, Bar, ComposedChart, Line } from 'recharts';
import { annotations, axes, ChartSize, margin, motion, palette, type ChartProps } from './shared';
export default function ComposedView({ spec }: ChartProps) {
  return <ChartSize><ComposedChart data={spec.data} margin={margin} accessibilityLayer title={spec.title}>{axes(spec)}{annotations(spec)}{spec.series.map((item, i) => {
    const common = { dataKey: item.dataKey, name: item.name, stroke: palette[i], ...motion(spec) };
    if (item.type === 'Line') return <Line key={item.dataKey} {...common} type="linear" strokeWidth={2} dot={spec.data.length <= 40} />;
    if (item.type === 'Area') return <Area key={item.dataKey} {...common} type="linear" fill={palette[i]} fillOpacity={0.2} stackId={spec.stacked ? 'values' : undefined} dot={spec.data.length <= 40} />;
    return <Bar key={item.dataKey} {...common} fill={palette[i]} stackId={spec.stacked ? 'values' : undefined} maxBarSize={64} />;
  })}</ComposedChart></ChartSize>;
}
