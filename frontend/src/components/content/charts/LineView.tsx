import { Line, LineChart } from 'recharts';
import { annotations, axes, ChartSize, margin, motion, palette, type ChartProps } from './shared';
export default function LineView({ spec }: ChartProps) {
  return <ChartSize><LineChart data={spec.data} margin={margin} accessibilityLayer title={spec.title}>{axes(spec)}{annotations(spec)}{spec.series.map((item, i) => <Line key={item.dataKey} dataKey={item.dataKey} name={item.name} type="linear" stroke={palette[i]} strokeWidth={2} strokeDasharray={i ? `${i * 3} 3` : undefined} dot={spec.data.length <= 40} {...motion(spec)} />)}</LineChart></ChartSize>;
}
