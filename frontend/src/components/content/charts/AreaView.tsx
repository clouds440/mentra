import { Area, AreaChart } from 'recharts';
import { annotations, axes, ChartSize, margin, motion, plotColor, type ChartProps } from './shared';
export default function AreaView({ spec }: ChartProps) {
  return <ChartSize><AreaChart data={spec.data} margin={margin} accessibilityLayer title={spec.title}>{axes(spec)}{annotations(spec)}{spec.series.map((item, i) => <Area key={item.dataKey} dataKey={item.dataKey} name={item.name} type="linear" stroke={plotColor(spec, i)} fill={plotColor(spec, i)} fillOpacity={0.2} dot={spec.data.length <= 40} stackId={spec.stacked ? 'values' : undefined} {...motion(spec)} />)}</AreaChart></ChartSize>;
}
