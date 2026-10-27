// Validate actual configured-provider output against the exact frontend contract.
// Only repository TypeScript is compiled; model output is parsed as JSON data.
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const source = await readFile(new URL('../src/lib/chartSpec.ts', import.meta.url), 'utf8');
const compile = source => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } }).outputText;
const colorSource = compile(await readFile(new URL('../src/lib/visualColors.ts', import.meta.url), 'utf8'));
const colorModule = `data:text/javascript;base64,${Buffer.from(colorSource).toString('base64')}`;
const compiled = compile(source).replace("'./visualColors'", JSON.stringify(colorModule));
const { parseChartSpec } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const reports = JSON.parse(await readFile(new URL('../../backend/.cache/chat-ui-live.json', import.meta.url), 'utf8'));
const charts = reports.filter(report => report.chart_spec).map(report => ({ chart: parseChartSpec(JSON.stringify(report.chart_spec)), expected: report.chart_expected_values ?? [20, 30] }));
if (!charts.length || charts.some(({ chart }) => !chart)) throw new Error('Configured-provider output does not match the frontend chart contract');
for (const { chart, expected } of charts) {
  if (chart.type !== 'BarChart' || chart.data.map(row => row[chart.series[0].dataKey]).sort((a, b) => a - b).join(',') !== expected.join(',')) throw new Error('Configured chart changed supplied values');
}
console.log(`${charts.length} configured-provider chart validated with the frontend contract and exact supplied values.`);
