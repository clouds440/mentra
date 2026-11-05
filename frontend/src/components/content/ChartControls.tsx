import { modelUsesInput } from '../../lib/chartModel';
import { SlidersHorizontal, Hash } from 'lucide-react';
import { ViewToggle } from '../ui/ViewToggle';
import { memo, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Button, Input, Select } from '../ui';
import { chartTick } from './charts/format';
import { chartNumberLimit, type ChartSpec } from '../../lib/chartSpec';

export const ChartControls = memo(function ChartControls({ spec, original, onEdit, onReset, mode, onModeChange, selection, onSelectionChange }: {
  selection: { row: number; field?: string }; onSelectionChange: (selection: { row: number; field?: string }) => void;
  mode: 'slider' | 'number'; onModeChange: (mode: 'slider' | 'number') => void;
  spec: ChartSpec; original: ChartSpec; onEdit: (row: number, field: string, value: number) => boolean; onReset: () => void;
}) {
  const row = Math.min(selection.row, spec.data.length - 1);
  const derived = new Set(spec.model?.equations.map(item => item.dataKey));
  const rowFields = [...(spec.data.every(item => typeof item[spec.xKey] === 'number') ? [{ dataKey: spec.xKey, name: spec.xKey }] : []), ...spec.series.filter(item => !derived.has(item.dataKey)),
    ...(spec.model?.inputs.map(item => ({ dataKey: item.dataKey, name: `${item.label}${item.unit ? ' (' + item.unit + ')' : ''}` })) ?? [])];
  const inputs = [...new Map(rowFields.map(item => [item.dataKey, item])).values()].filter(item => !spec.model || modelUsesInput(spec.model, item.dataKey));
  const fields = [...(spec.model?.parameters.map(item => ({ dataKey: item.key, name: `${item.label}${item.unit ? ' (' + item.unit + ')' : ''}` })) ?? []), ...inputs];
  const defaultField = spec.model?.parameters[0]?.key ?? spec.model?.inputs[0]?.dataKey ?? inputs.find(item => item.dataKey !== spec.xKey)?.dataKey ?? fields[0]?.dataKey ?? '';
  const field = fields.some(item => item.dataKey === selection.field) ? selection.field! : defaultField;
  const parameter = spec.model?.parameters.find(item => item.key === field);
  if (!fields.length) return null;
  return <section aria-label="Chart controls" className="chart-controls">
    <div className="chart-control-header">
      <div><p className="chart-control-title">Explore the chart</p><p className="chart-control-hint">{parameter ? 'Changes apply to every data point.' : spec.model ? 'Linked values update for the selected point.' : 'Changes apply to the selected point.'}</p></div>
      <div className="visual-actions">
        <ViewToggle label="Chart input mode" view={mode} onChange={onModeChange} showLabels options={[{ value: 'slider', label: 'Slider', Icon: SlidersHorizontal }, { value: 'number', label: 'Number', Icon: Hash }]} />
        <Button size="sm" variant="ghost" onClick={onReset}>Reset</Button>
      </div>
    </div>
    {(fields.length > 1 || (!parameter && spec.data.length > 1)) && <div className="chart-control-fields">
      {fields.length > 1 ? <label><span>Variable</span><Select aria-label="Chart value" value={field} onChange={event => onSelectionChange({ row, field: event.target.value })}>{fields.map(item => <option key={item.dataKey} value={item.dataKey}>{item.name}</option>)}</Select></label> : null}
      {!parameter && spec.data.length > 1 && <label><span>Data point</span><Select aria-label="Data point" value={row} onChange={event => onSelectionChange({ row: Number(event.target.value), field })}>{spec.data.map((item, index) => <option key={index} value={index}>{String(item[spec.xKey])} (#{index + 1})</option>)}</Select></label>}
    </div>}
    {fields.length === 1 && <p className="chart-control-variable">{fields[0].name}</p>}
    <ValueEditor key={(parameter ? -1 : row) + ':' + field} spec={spec} original={original} row={parameter ? -1 : row} field={field} onEdit={onEdit} mode={mode} />
  </section>;
});
function ValueEditor({ spec, original, row, field, onEdit, mode }: { mode: 'slider' | 'number'; spec: ChartSpec; original: ChartSpec; row: number; field: string; onEdit: (row: number, field: string, value: number) => boolean }) {
  const parameter = row === -1 ? spec.model?.parameters.find(item => item.key === field) : undefined;
  const rowInput = row >= 0 ? spec.model?.inputs.find(item => item.dataKey === field) : undefined;
  const value = parameter?.value ?? spec.data[row]?.[field]; const [text, setText] = useState(value === null ? '' : String(value));
  const [invalid, setInvalid] = useState(false); const frame = useRef(0);
  const pending = useRef<number>(undefined);
  useEffect(() => { setText(value === null ? '' : String(value)); setInvalid(false); }, [value]);
  useLayoutEffect(() => () => cancelAnimationFrame(frame.current), []);
  useLayoutEffect(() => { if (mode === 'slider') { setText(value === null ? '' : String(value)); setInvalid(false); } if (mode === 'number' && frame.current) { cancelAnimationFrame(frame.current); frame.current = 0; if (pending.current !== undefined) setInvalid(!onEdit(row, field, pending.current)); pending.current = undefined; } }, [mode]);
  const nonnegative = !rowInput && !parameter && field !== spec.xKey && ['PieChart', 'RadarChart'].includes(spec.type);
  const magnitude = Math.max(1, ...original.data.map(item => Math.abs(Number(item[field]) || 0)));
  const limit = parameter?.max ?? rowInput?.max ?? Math.max(Math.min(chartNumberLimit, magnitude * 2), Number(value) || 0);
  const min = parameter?.min ?? rowInput?.min ?? (nonnegative ? 0 : Math.min(original.data.every(item => Number(item[field]) >= 0) ? 0 : -limit, Number(value) || 0));
  function flush() {
    if (!frame.current) return;
    cancelAnimationFrame(frame.current); frame.current = 0;
    if (pending.current !== undefined) { setInvalid(!onEdit(row, field, pending.current)); pending.current = undefined; }
  }
  function update(next: string, slider = false) {
    setText(next);
    if (!next.trim() || !Number.isFinite(Number(next))) { setInvalid(true); return; }
    if (slider) {
      pending.current = Number(next);
      if (!frame.current) frame.current = requestAnimationFrame(() => { frame.current = 0; if (pending.current !== undefined) setInvalid(!onEdit(row, field, pending.current)); });
    } else {
      cancelAnimationFrame(frame.current); frame.current = 0; pending.current = undefined;
      setInvalid(!onEdit(row, field, Number(next)));
    }
  }
  return <div className="chart-value-editor"><div className="chart-value-row">
    {mode === 'slider' && <><input aria-label="Adjust selected value" type="range" className="chart-slider min-w-0 flex-1" min={min} max={limit} step={parameter?.step ?? 'any'} aria-invalid={invalid} value={Math.max(min, Math.min(limit, Number(text) || 0))} onChange={event => update(event.target.value, true)} onPointerUp={flush} onKeyUp={flush} onBlur={flush} /><output aria-live="off" className="chart-value-readout" aria-label="Current value">{text}</output></>}
    {mode === 'number' && <Input aria-label="Selected value" type="number" step={parameter?.step ?? 'any'} min={parameter?.min ?? rowInput?.min ?? (nonnegative ? 0 : -chartNumberLimit)} max={parameter?.max ?? rowInput?.max ?? chartNumberLimit} value={text} aria-invalid={invalid} className="chart-number-input" onChange={event => update(event.target.value)} />}
  </div>{mode === 'slider' && <div className="chart-range-labels" aria-hidden="true"><span>{chartTick(min)}</span><span>{chartTick(limit)}</span></div>}{invalid && <p role="status" className="text-xs text-danger">This value is outside the chart or equation domain. The last valid graph is preserved.</p>}</div>;
}
