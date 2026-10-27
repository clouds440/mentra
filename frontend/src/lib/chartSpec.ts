export const chartTypes = ['LineChart', 'BarChart', 'AreaChart', 'ComposedChart', 'PieChart', 'RadarChart', 'ScatterChart'] as const;
export type ChartType = typeof chartTypes[number];
export type ChartSeries = { dataKey: string; name: string; type: 'Line' | 'Bar' | 'Area' };
export type ChartSpec = { type: ChartType; title: string; description?: string; xKey: string; unit?: string; stacked: boolean; series: ChartSeries[]; data: Record<string, string | number | null>[] };
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const only = (value: Record<string, unknown>, keys: string[]) => Object.keys(value).every(key => keys.includes(key));
const text = (value: unknown, max: number): value is string => typeof value === 'string' && !!value.trim() && value.length <= max;
const key = (value: unknown): value is string => text(value, 48) && /^[A-Za-z][A-Za-z0-9_]*$/.test(value) && !['constructor', 'prototype', '__proto__'].includes(value);
const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 1e12;

/** A data-only Recharts contract. No JSX, callbacks, arbitrary props or resources. */
export function parseChartSpec(code: string): ChartSpec | null {
  if (code.length > 24000) return null;
  try {
    const value: unknown = JSON.parse(code);
    if (!record(value) || !only(value, ['type', 'title', 'description', 'xKey', 'unit', 'stacked', 'series', 'data'])) return null;
    if (!chartTypes.includes(value.type as ChartType) || !text(value.title, 120) || !key(value.xKey)) return null;
    if (value.description !== undefined && !text(value.description, 500) || value.unit !== undefined && !text(value.unit, 32) || value.stacked !== undefined && typeof value.stacked !== 'boolean') return null;
    if (!Array.isArray(value.series) || !value.series.length || value.series.length > 6 || !Array.isArray(value.data) || !value.data.length || value.data.length > 200) return null;
    const type = value.type as ChartType; const xKey = value.xKey;
    const series: ChartSeries[] = [];
    for (const item of value.series) {
      if (!record(item) || !only(item, ['dataKey', 'name', 'type']) || !key(item.dataKey) || item.dataKey === xKey || series.some(entry => entry.dataKey === item.dataKey)) return null;
      if (item.name !== undefined && !text(item.name, 80)) return null;
      if (item.type !== undefined && !['Line', 'Bar', 'Area'].includes(String(item.type))) return null;
      if (type !== 'ComposedChart' && item.type !== undefined || type === 'ComposedChart' && item.type === undefined) return null;
      series.push({ dataKey: item.dataKey, name: String(item.name ?? item.dataKey), type: (item.type ?? (type === 'BarChart' ? 'Bar' : type === 'AreaChart' ? 'Area' : 'Line')) as ChartSeries['type'] });
    }
    if (type === 'PieChart' && series.length !== 1 || value.stacked && !['BarChart', 'AreaChart', 'ComposedChart'].includes(type)) return null;
    if (['PieChart', 'RadarChart'].includes(type) && value.data.length > 24) return null;
    if (type === 'RadarChart' && value.data.length < 3) return null;
    const fields = [xKey, ...series.map(item => item.dataKey)];
    const data: ChartSpec['data'] = [];
    for (const row of value.data) {
      if (!record(row) || !only(row, fields)) return null;
      const category = row[xKey];
      if (type === 'ScatterChart' ? !number(category) : !text(category, 80) && !number(category)) return null;
      const clean: Record<string, string | number | null> = { [xKey]: category as string | number };
      for (const item of series) {
        const cell = row[item.dataKey];
        if (cell !== null && !number(cell)) return null;
        if (cell === null && ['PieChart', 'RadarChart', 'ScatterChart'].includes(type) || typeof cell === 'number' && cell < 0 && ['PieChart', 'RadarChart'].includes(type)) return null;
        clean[item.dataKey] = cell as number | null;
      }
      data.push(clean);
    }
    if (series.some(item => data.every(row => row[item.dataKey] === null))) return null;
    if (type === 'PieChart' && !data.some(row => Number(row[series[0].dataKey]) > 0)) return null;
    return { type, title: value.title.trim(), description: value.description as string | undefined, unit: value.unit as string | undefined, xKey, stacked: value.stacked === true, series, data };
  } catch { return null; }
}
