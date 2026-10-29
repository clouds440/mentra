import { finiteChartNumber, chartNumberLimit } from './chartEquation';
import { parseChartModel, calculateChartModel, modelUsesInput, type ChartModel } from './chartModel';
import { visualColor } from './visualColors';
export const chartTypes = ['LineChart', 'BarChart', 'AreaChart', 'ComposedChart', 'PieChart', 'RadarChart', 'ScatterChart'] as const;
export type ChartType = typeof chartTypes[number];
export type ChartSeries = { dataKey: string; name: string; type: 'Line' | 'Bar' | 'Area'; color?: string };
export type ChartSpec = { type: ChartType; title: string; description?: string; xKey: string; unit?: string; stacked: boolean; series: ChartSeries[]; data: Record<string, string | number | null>[]; colors?: string[]; enableControls?: boolean; model?: ChartModel; modelUnavailable?: boolean };
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const only = (value: Record<string, unknown>, keys: string[]) => Object.keys(value).every(key => keys.includes(key));
const text = (value: unknown, max: number): value is string => typeof value === 'string' && !!value.trim() && value.length <= max;
const key = (value: unknown): value is string => text(value, 48) && /^[A-Za-z][A-Za-z0-9_]*$/.test(value) && !['constructor', 'prototype', '__proto__'].includes(value);
const number = finiteChartNumber;

/** A data-only Recharts contract. No JSX, callbacks, arbitrary props or resources. */
export function parseChartSpec(code: string): ChartSpec | null {
  if (code.length > 24000) return null;
  try {
    const value: unknown = JSON.parse(code);
    if (!record(value) || !only(value, ['type', 'title', 'description', 'xKey', 'unit', 'stacked', 'series', 'data', 'colors', 'enableControls', 'model'])) return null;
    if (value.enableControls !== undefined && typeof value.enableControls !== 'boolean') return null;
    if (value.colors !== undefined && (!Array.isArray(value.colors) || !value.colors.length || value.colors.length > 24 || value.colors.some(color => typeof color !== 'string' || !visualColor(color)))) return null;
    if (!chartTypes.includes(value.type as ChartType) || !text(value.title, 120) || !key(value.xKey)) return null;
    if (value.description !== undefined && !text(value.description, 500) || value.unit !== undefined && !text(value.unit, 32) || value.stacked !== undefined && typeof value.stacked !== 'boolean') return null;
    if (!Array.isArray(value.series) || !value.series.length || value.series.length > 6 || !Array.isArray(value.data) || !value.data.length || value.data.length > 200) return null;
    const type = value.type as ChartType; const xKey = value.xKey;
    const series: ChartSeries[] = [];
    for (const item of value.series) {
      if (!record(item) || !only(item, ['dataKey', 'name', 'type', 'color']) || !key(item.dataKey) || item.dataKey === xKey || series.some(entry => entry.dataKey === item.dataKey)) return null;
      if (item.color !== undefined && (typeof item.color !== 'string' || !visualColor(item.color))) return null;
      if (item.name !== undefined && !text(item.name, 80)) return null;
      if (item.type !== undefined && !['Line', 'Bar', 'Area'].includes(String(item.type))) return null;
      if (type !== 'ComposedChart' && item.type !== undefined || type === 'ComposedChart' && item.type === undefined) return null;
      series.push({ dataKey: item.dataKey, name: String(item.name ?? item.dataKey), color: item.color as string | undefined, type: (item.type ?? (type === 'BarChart' ? 'Bar' : type === 'AreaChart' ? 'Area' : 'Line')) as ChartSeries['type'] });
    }
    if (type === 'PieChart' && series.length !== 1 || value.stacked && !['BarChart', 'AreaChart', 'ComposedChart'].includes(type)) return null;
    if (['PieChart', 'RadarChart'].includes(type) && value.data.length > 24) return null;
    if (type === 'RadarChart' && value.data.length < 3) return null;
    const chartFields = [xKey, ...series.map(item => item.dataKey)];
    const model = value.model === undefined ? undefined : parseChartModel(value.model, chartFields, series.map(item => item.dataKey));
    // A failed model must not discard otherwise usable supplied observations.
    // Only bounded, declared model fields may extend the base row contract.
    const rawInputs = record(value.model) && Array.isArray(value.model.inputs) && value.model.inputs.length <= 8
      ? value.model.inputs.filter(record).map(item => item.dataKey).filter(key) : [];
    const rawOutputs = record(value.model) && Array.isArray(value.model.equations) && value.model.equations.length <= 6
      ? value.model.equations.filter(record).map(item => item.dataKey).filter(key) : [];
    const fields = [...new Set([...chartFields, ...rawInputs, ...rawOutputs])];
    let modelInputsValid = true;
    const data: ChartSpec['data'] = [];
    for (const row of value.data) {
      if (!record(row) || !only(row, fields)) return null;
      const category = row[xKey];
      if (type === 'ScatterChart' ? !number(category) : !text(category, 80) && !number(category)) return null;
      const clean: Record<string, string | number | null> = { [xKey]: category as string | number };
      for (const item of series) {
        const cell = row[item.dataKey];
        if (cell !== null && !number(cell)) return null;
        clean[item.dataKey] = cell as number | null;
      }
      for (const input of model?.inputs ?? []) { const cell = row[input.dataKey]; if (!number(cell)) modelInputsValid = false; else clean[input.dataKey] = cell; }
      data.push(clean);
    }
    const calculated = model && modelInputsValid ? calculateChartModel(model, data) : undefined;
    const activeModel = model && calculated && validChartData(type, series, calculated) ? model : undefined;
    const modelUnavailable = value.model !== undefined && !activeModel;
    const displayed = activeModel ? calculated! : modelUnavailable ? data.map(row => Object.fromEntries(chartFields.map(field => [field, row[field]]))) : data;
    if (!activeModel && !validChartData(type, series, displayed)) return null;
    return { model: activeModel, modelUnavailable, type, title: value.title.trim(), description: value.description as string | undefined, unit: value.unit as string | undefined, colors: value.colors as string[] | undefined, xKey, stacked: value.stacked === true, enableControls: !modelUnavailable && (value.enableControls ?? !!activeModel), series, data: displayed };
  } catch { return null; }
}

function validChartData(type: ChartType, series: ChartSeries[], data: ChartSpec['data']) {
  return series.every(item => data.some(row => row[item.dataKey] !== null)) && data.every(row => series.every(item => row[item.dataKey] === null && !['PieChart', 'RadarChart', 'ScatterChart'].includes(type) || finiteChartNumber(row[item.dataKey]) && (!['PieChart', 'RadarChart'].includes(type) || Number(row[item.dataKey]) >= 0)))
    && (type !== 'PieChart' || data.some(row => Number(row[series[0].dataKey]) > 0));
}
/** Keep normal edits independent; equation outputs are read-only derived values. */
export function editChartValue(spec: ChartSpec, row: number, field: string, value: number): ChartSpec | null {
  if (!spec.enableControls || !finiteChartNumber(value)) return null;
  if (row === -1 && spec.model) {
    const parameter = spec.model.parameters.find(item => item.key === field);
    if (!parameter || value < parameter.min || value > parameter.max) return null;
    if (parameter.value === value) return spec;
    const model = { ...spec.model, parameters: spec.model.parameters.map(item => item.key === field ? { ...item, value } : item) };
    const data = calculateChartModel(model, spec.data);
    return data && validChartData(spec.type, spec.series, data) ? { ...spec, model, data } : null;
  }
  if (!spec.data[row] || spec.model && !modelUsesInput(spec.model, field)) return null;
  if (!spec.series.some(item => item.dataKey === field) && !spec.model?.inputs.some(item => item.dataKey === field) && !(field === spec.xKey && typeof spec.data[row][field] === 'number')) return null;
  if (spec.data[row][field] === value) return spec;
  let data = spec.data.map((item, index) => index === row ? { ...item, [field]: value } : item);
  if (spec.model) {
    const calculated = calculateChartModel(spec.model, [data[row]]); if (!calculated) return null;
    data = data.map((item, index) => index === row ? calculated[0] : item);
  }
  return validChartData(spec.type, spec.series, data) ? { ...spec, data } : null;
}
export { chartNumberLimit };

/** Copyable source uses public schema fields, never internal renderer type defaults. */
export function serializeChartSpec(spec: ChartSpec): string {
  const { modelUnavailable: _modelUnavailable, ...publicSpec } = spec;
  const value = { ...publicSpec, series: spec.series.map(({ type, ...item }) => spec.type === 'ComposedChart' ? { ...item, type } : item),
    data: spec.model ? spec.data.map(row => ({ ...row, ...Object.fromEntries(spec.model!.equations.map(item => [item.dataKey, null])) })) : spec.data };
  const readable = JSON.stringify(value, null, 2);
  return readable.length <= 24000 ? readable : JSON.stringify(value);
}
