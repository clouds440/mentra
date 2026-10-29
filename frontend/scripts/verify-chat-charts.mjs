// Validate actual configured-provider output against the exact frontend contract.
// Only repository TypeScript is compiled; model output is parsed as JSON data.
import { readFile } from 'node:fs/promises';
import { moduleUrl } from './chart-test-module.mjs';
const specModule = await moduleUrl('chartSpec');
const { parseChartSpec } = await import(specModule);
const reports = JSON.parse(await readFile(new URL('../../backend/.cache/chat-ui-live.json', import.meta.url), 'utf8'));
const charts = reports.filter(report => report.chart_spec).map(report => ({ chart: parseChartSpec(JSON.stringify(report.chart_spec)), expected: report.chart_expected_values ?? [20, 30], types: report.chart_expected_types ?? ['BarChart'] }));
if (!charts.length || charts.some(({ chart }) => !chart)) throw new Error('Configured-provider output does not match the frontend chart contract');
for (const { chart, expected, types } of charts) {
  if (!types.includes(chart.type) || chart.data.map(row => row[chart.series[0].dataKey]).sort((a, b) => a - b).join(',') !== expected.join(',')) throw new Error('Configured chart changed supplied values');
}
console.log(`${charts.length} configured-provider chart validated with the frontend contract and exact supplied values.`);
