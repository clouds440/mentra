import { compileEquation, equationIdentifier, finiteChartNumber, type CompiledEquation } from './chartEquation';
export type ChartParameter = { key: string; label: string; value: number; min: number; max: number; step?: number; unit?: string };
export type ChartInput = { dataKey: string; label: string; min?: number; max?: number; unit?: string };
export type ChartEquation = { dataKey: string; expression: string };
export type ChartModel = { kind: 'illustrative' | 'established'; note: string; parameters: ChartParameter[]; inputs: ChartInput[]; equations: ChartEquation[] };
type Row = Record<string, string | number | null>;
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const only = (value: Record<string, unknown>, keys: string[]) => Object.keys(value).every(key => keys.includes(key));
const text = (value: unknown, max: number): value is string => typeof value === 'string' && !!value.trim() && value.length <= max;
const compiled = new WeakMap<ChartEquation[], { key: string; program: CompiledEquation }[]>();
export function parseChartModel(raw: unknown, fields: string[], series: string[]): ChartModel | null {
  try {
    if (!record(raw) || !only(raw, ['kind', 'note', 'parameters', 'inputs', 'equations']) || !['illustrative', 'established'].includes(String(raw.kind)) || !text(raw.note, 400)) return null;
    if (raw.parameters !== undefined && (!Array.isArray(raw.parameters) || raw.parameters.length > 8) || !Array.isArray(raw.equations) || !raw.equations.length || raw.equations.length > 6) return null;
    const inputs: ChartInput[] = [];
    if (raw.inputs !== undefined && (!Array.isArray(raw.inputs) || raw.inputs.length > 8)) return null;
    for (const item of raw.inputs as unknown[] ?? []) {
      if (!record(item) || !only(item, ['dataKey', 'label', 'min', 'max', 'unit']) || !equationIdentifier(item.dataKey) || inputs.some(input => input.dataKey === item.dataKey) || !text(item.label, 80)) return null;
      if (item.min !== undefined && !finiteChartNumber(item.min) || item.max !== undefined && !finiteChartNumber(item.max) || typeof item.min === 'number' && typeof item.max === 'number' && item.min >= item.max || item.unit !== undefined && !text(item.unit, 32)) return null;
      inputs.push({ dataKey: item.dataKey, label: item.label, min: item.min as number | undefined, max: item.max as number | undefined, unit: item.unit as string | undefined });
    }
    fields = [...fields, ...inputs.map(item => item.dataKey)];
    const parameters: ChartParameter[] = [];
    for (const item of raw.parameters as unknown[] ?? []) {
      if (!record(item) || !only(item, ['key', 'label', 'value', 'min', 'max', 'step', 'unit']) || !equationIdentifier(item.key) || fields.includes(item.key) || parameters.some(parameter => parameter.key === item.key)) return null;
      if (!text(item.label, 80) || !finiteChartNumber(item.value) || !finiteChartNumber(item.min) || !finiteChartNumber(item.max) || item.min >= item.max || item.value < item.min || item.value > item.max) return null;
      if (item.step !== undefined && (!finiteChartNumber(item.step) || item.step <= 0 || item.step > item.max - item.min) || item.unit !== undefined && !text(item.unit, 32)) return null;
      parameters.push({ key: item.key, label: item.label, value: item.value, min: item.min, max: item.max, step: item.step as number | undefined, unit: item.unit as string | undefined });
    }
    const equations: ChartEquation[] = [];
    for (const item of raw.equations) {
      if (!record(item) || !only(item, ['dataKey', 'expression']) || !equationIdentifier(item.dataKey) || fields.includes(item.dataKey) && !series.includes(item.dataKey) || parameters.some(parameter => parameter.key === item.dataKey) || !text(item.expression, 240) || equations.some(equation => equation.dataKey === item.dataKey)) return null;
      equations.push({ dataKey: item.dataKey, expression: item.expression });
    }
    const outputs = new Set(equations.map(item => item.dataKey));
    if (inputs.some(input => outputs.has(input.dataKey))) return null;
    const available = new Set([...fields.filter(key => !outputs.has(key)), ...parameters.map(item => item.key)]);
    const waiting = equations.map(item => ({ key: item.dataKey, program: compileEquation(item.expression) }));
    // An input called e/pi must not silently evaluate as a mathematical constant.
    if (waiting.some(item => fields.some(field => item.program.constants.has(field)))) return null;
    // Every helper must contribute to a plotted result. Otherwise a control may
    // appear to work while only changing an invisible intermediate calculation.
    const useful = new Set(equations.filter(item => series.includes(item.dataKey)).map(item => item.dataKey));
    if (!useful.size) return null;
    for (let index = 0; index < equations.length; index++) {
      for (const item of waiting) if (useful.has(item.key)) for (const dependency of item.program.references) if (outputs.has(dependency)) useful.add(dependency);
    }
    if (useful.size !== equations.length) return null;
    if ([...parameters.map(item => item.key), ...inputs.map(item => item.dataKey)].some(key => !waiting.some(item => item.program.references.has(key)))) return null;
    const ordered: typeof waiting = [];
    while (waiting.length) {
      const index = waiting.findIndex(item => [...item.program.references].every(key => available.has(key)));
      if (index < 0) return null; // Unknown variables, self references and cycles.
      const [item] = waiting.splice(index, 1); ordered.push(item); available.add(item.key);
    }
    compiled.set(equations, ordered);
    return { kind: raw.kind as ChartModel['kind'], note: raw.note, parameters, inputs, equations };
  } catch { return null; }
}
/** Transactional calculation: callers publish only complete, valid data arrays. */
export function calculateChartModel(model: ChartModel, data: Row[]): Row[] | null {
  const programs = compiled.get(model.equations);
  if (!programs) return null;
  try {
    return data.map(row => {
      for (const input of model.inputs) { const value = row[input.dataKey]; if (!finiteChartNumber(value) || input.min !== undefined && value < input.min || input.max !== undefined && value > input.max) throw new Error('Row input is outside its bounds'); }
      const scope = new Map(model.parameters.map(parameter => [parameter.key, parameter.value]));
      for (const [key, value] of Object.entries(row)) if (typeof value === 'number') scope.set(key, value);
      const next = { ...row };
      for (const { key, program } of programs) { const value = program.calculate(scope); scope.set(key, value); next[key] = value; }
      return next;
    });
  } catch { return null; }
}
export function modelUsesInput(model: ChartModel, key: string): boolean {
  return !model.equations.some(item => item.dataKey === key) && !model.parameters.some(item => item.key === key)
    && (compiled.get(model.equations)?.some(item => item.program.references.has(key)) ?? false);
}
export function modelSummary(model: ChartModel): string {
  return `${model.kind === 'illustrative' ? 'Illustrative model' : 'Equation model'}: ${model.note} ${model.equations.map(item => `${item.dataKey} = ${item.expression}`).join('; ')}${model.parameters.length ? '. ' + model.parameters.map(item => `${item.label}${item.label.toLowerCase() !== item.key.toLowerCase() ? ' (' + item.key + ')' : ''} = ${item.value}${item.unit ? ' ' + item.unit : ''}`).join(', ') : ''}${model.inputs.length ? '. Inputs: ' + model.inputs.map(item => `${item.dataKey}: ${item.label}${item.unit ? ' (' + item.unit + ')' : ''}`).join(', ') : ''}`;
}
