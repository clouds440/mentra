import { Pie, PieChart } from 'recharts';
import { useMemo } from 'react';
import { annotations, ChartSize, motion, plotColor, type ChartProps } from './shared';
export default function PieView({ spec }: ChartProps) {
  const data = useMemo(() => spec.data.map((row, i) => ({ name: row[spec.xKey], value: row[spec.series[0].dataKey], fill: plotColor(spec, i, false) })), [spec]);
  return <ChartSize><PieChart accessibilityLayer title={spec.title}>{annotations(spec)}<Pie data={data} dataKey="value" nameKey="name" outerRadius="75%" {...motion(spec)} /></PieChart></ChartSize>;
}
