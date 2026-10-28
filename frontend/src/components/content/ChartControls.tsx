import { memo, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Button, Input, Select } from '../ui';
import type { ChartSpec } from '../../lib/chartSpec';

export const ChartControls = memo(function ChartControls({ spec, original, onEdit, onReset }: {
  spec: ChartSpec; original: ChartSpec; onEdit: (row: number, field: string, value: number) => boolean; onReset: () => void;
}) {
  const [row, setRow] = useState(0); const [field, setField] = useState(spec.series[0].dataKey);
  const fields = [...(spec.data.every(item => typeof item[spec.xKey] === 'number') ? [{ dataKey: spec.xKey, name: spec.xKey }] : []), ...spec.series];
  return <section aria-label="Chart controls" className="space-y-3 border-t border-border p-3">
    <div className="flex items-center justify-between gap-2"><p className="text-xs text-muted">Explore the values · local changes only</p><Button size="sm" variant="ghost" onClick={onReset}>Reset</Button></div>
    <div className="grid grid-cols-2 gap-3">
      <Select aria-label="Data point" value={row} onChange={event => setRow(Number(event.target.value))}>{spec.data.map((item, index) => <option key={index} value={index}>{String(item[spec.xKey])} (#{index + 1})</option>)}</Select>
      <Select aria-label="Chart value" value={field} onChange={event => setField(event.target.value)}>{fields.map(item => <option key={item.dataKey} value={item.dataKey}>{item.name}</option>)}</Select>
    </div>
    <ValueEditor key={`${row}:${field}`} spec={spec} original={original} row={row} field={field} onEdit={onEdit} />
  </section>;
});
function ValueEditor({ spec, original, row, field, onEdit }: { spec: ChartSpec; original: ChartSpec; row: number; field: string; onEdit: (row: number, field: string, value: number) => boolean }) {
  const value = spec.data[row][field]; const [text, setText] = useState(value === null ? '' : String(value));
  const [invalid, setInvalid] = useState(false); const frame = useRef(0);
  const pending = useRef<number>();
  useEffect(() => { setText(value === null ? '' : String(value)); setInvalid(false); }, [value]);
  useLayoutEffect(() => () => cancelAnimationFrame(frame.current), []);
  const nonnegative = field !== spec.xKey && ['PieChart', 'RadarChart'].includes(spec.type);
  const magnitude = Math.max(1, ...original.data.map(item => Math.abs(Number(item[field]) || 0)));
  const limit = Math.max(Math.min(1e12, magnitude * 2), Number(value) || 0);
  const min = nonnegative ? 0 : Math.min(original.data.every(item => Number(item[field]) >= 0) ? 0 : -limit, Number(value) || 0);
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
  return <div className="space-y-1"><div className="flex items-center gap-3">
    <input aria-label="Adjust selected value" type="range" className="min-w-0 flex-1 accent-accent" min={min} max={limit} step="any" value={Math.max(min, Math.min(limit, Number(value) || 0))} onChange={event => update(event.target.value, true)} />
    <Input aria-label="Selected value" type="number" step="any" min={nonnegative ? 0 : -1e12} max={1e12} value={text} aria-invalid={invalid} className="w-28 shrink-0" onChange={event => update(event.target.value)} />
  </div>{invalid && <p role="status" className="text-xs text-danger">Use a finite value within the chart’s range. Pie slices must have a positive total.</p>}</div>;
}
