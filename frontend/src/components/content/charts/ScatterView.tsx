import { Scatter, ScatterChart } from 'recharts';
import { useMemo } from 'react';
import { annotations, axes, ChartSize, margin, motion, plotColor, type ChartProps } from './shared';
export default function ScatterView({ spec, xName }: ChartProps) {
  const data = useMemo(() => spec.series.map(item => spec.data.map(row => ({ x: row[spec.xKey], y: row[item.dataKey] }))), [spec]);
  return <ChartSize><ScatterChart margin={margin} accessibilityLayer title={spec.title}>{axes(spec, true, xName)}{annotations(spec)}{spec.series.map((item, i) => <Scatter key={item.dataKey} name={item.name} data={data[i]} fill={plotColor(spec, i)} {...motion(spec)} />)}</ScatterChart></ChartSize>;
}
