import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart } from 'recharts';
import { annotations, ChartSize, motion, palette, type ChartProps } from './shared';
export default function RadarView({ spec }: ChartProps) {
  return <ChartSize><RadarChart data={spec.data} accessibilityLayer title={spec.title} outerRadius="70%"><PolarGrid stroke="rgb(var(--border))" /><PolarAngleAxis dataKey={spec.xKey} tick={{ fill: 'rgb(var(--muted))', fontSize: 12 }} /><PolarRadiusAxis tick={{ fill: 'rgb(var(--muted))', fontSize: 11 }} />{annotations(spec)}{spec.series.map((item, i) => <Radar key={item.dataKey} dataKey={item.dataKey} name={item.name} stroke={palette[i]} fill={palette[i]} fillOpacity={0.15} {...motion(spec)} />)}</RadarChart></ChartSize>;
}
