import { modelSummary } from '../../lib/chartModel';
import { Component, lazy, memo, Suspense, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { Button, Dialog } from '../ui';
import { CodeBlock } from './CodeBlock';
import { parseChartSpec, editChartValue, serializeChartSpec, type ChartSpec } from '../../lib/chartSpec';
import { cacheChart, readChart, diagramCacheGeneration } from '../../lib/richContentCache';
const ChartControls = lazy(() => import('./ChartControls').then(module => ({ default: module.ChartControls })));

// Import only the selected family; no Recharts implementation is in this module.
const renderers = {
  LineChart: lazy(() => import('./charts/LineView')),
  BarChart: lazy(() => import('./charts/BarView')),
  AreaChart: lazy(() => import('./charts/AreaView')),
  ComposedChart: lazy(() => import('./charts/ComposedView')),
  PieChart: lazy(() => import('./charts/PieView')),
  RadarChart: lazy(() => import('./charts/RadarView')),
  ScatterChart: lazy(() => import('./charts/ScatterView')),
};
class ChartBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <p role="status" className="p-4 text-sm text-muted">This chart could not be displayed. Its data and source are still available.</p> : this.props.children; }
}
const ChartCanvas = memo(function ChartCanvas({ spec }: { spec: ChartSpec }) {
  const Renderer = renderers[spec.type];
  // Recharts may spread row fields into shape props. Keep original field names
  // for source/tables, but pass only app-owned field names into chart internals.
  const plot = useMemo<ChartSpec>(() => ({ ...spec, xKey: 'category',
    series: spec.series.map((item, i) => ({ ...item, dataKey: `series${i}` })),
    data: spec.data.map(row => Object.fromEntries([['category', row[spec.xKey]], ...spec.series.map((item, i) => [`series${i}`, row[item.dataKey]])])),
  }), [spec]);
  return <div className="chart-plot"><ChartBoundary key={spec.type}><Suspense fallback={<p role="status" className="p-4 text-sm text-muted">Preparing chart…</p>}><Renderer spec={plot} xName={spec.xKey} /></Suspense></ChartBoundary></div>;
});
ChartCanvas.displayName = 'ChartCanvas';
const ChartDataTable = memo(function ChartDataTable({ spec }: { spec: ChartSpec }) {
  const rowInputs = spec.model?.inputs ?? [];
  const columns = [{ dataKey: spec.xKey, name: rowInputs.find(item => item.dataKey === spec.xKey)?.label ?? spec.xKey, unit: rowInputs.find(item => item.dataKey === spec.xKey)?.unit },
    ...rowInputs.filter(item => item.dataKey !== spec.xKey && !spec.series.some(series => series.dataKey === item.dataKey)).map(item => ({ dataKey: item.dataKey, name: item.label, unit: item.unit })),
    ...spec.series.map(item => ({ ...item, unit: rowInputs.find(input => input.dataKey === item.dataKey)?.unit ?? spec.unit }))];
  return <div className="markdown-table-scroll p-3"><table><caption className="sr-only">{spec.title} - exact data{spec.unit ? ` (${spec.unit})` : ''}</caption><thead><tr>{columns.map(item => <th key={item.dataKey} scope="col">{item.name}{item.unit ? ` (${item.unit})` : ''}</th>)}</tr></thead><tbody>{spec.data.map((row, i) => <tr key={i}>{columns.map((item, column) => column === 0 ? <th key={item.dataKey} scope="row">{row[item.dataKey]}</th> : <td key={item.dataKey}>{row[item.dataKey] === null ? '—' : String(row[item.dataKey])}</td>)}</tr>)}</tbody></table></div>;
});
function RechartsFigureContent({ code }: { code: string }) {
  const titleId = useId();
  const figureRef = useRef<HTMLElement>(null); const viewerRef = useRef<HTMLDialogElement>(null);
  const [downloading, setDownloading] = useState<'svg' | 'png'>(); const [downloadError, setDownloadError] = useState(false);
  const original = useMemo(() => {
    const cached = readChart(code);
    if (cached !== undefined) return cached;
    const parsed = parseChartSpec(code); cacheChart(code, parsed); return parsed;
  }, [code]);
  const [edited, setEdited] = useState<{ original: ChartSpec; value: ChartSpec }>();
  const [reset, setReset] = useState(0);
  const [controlSelection, setControlSelection] = useState<{ row: number; field?: string }>({ row: 0 });
  const [controlMode, setControlMode] = useState<'slider' | 'number'>('slider');
  const spec = edited?.original === original ? edited.value : original;
  const current = useRef(spec); current.current = spec;
  function edit(row: number, field: string, value: number) {
    if (!original || !current.current) return false;
    const next = editChartValue(current.current, row, field, value);
    if (!next) return false;
    if (next !== current.current) { current.current = next; setEdited({ original, value: next }); }
    return true;
  }
  const controls = spec?.enableControls && original ? <Suspense fallback={null}><ChartControls key={`${code}:${reset}`} spec={spec} original={original} mode={controlMode} onModeChange={setControlMode} selection={controlSelection} onSelectionChange={setControlSelection} onEdit={edit} onReset={() => { current.current = original; setEdited(undefined); setControlSelection({ row: 0 }); setReset(value => value + 1); }} /></Suspense> : null;
  const [source, setSource] = useState(false); const [data, setData] = useState(false); const [expanded, setExpanded] = useState(false);
  const background = useRef(spec); if (!expanded) background.current = spec;
  async function download(format: 'svg' | 'png') {
    if (!spec || downloading) return;
    const generation = diagramCacheGeneration();
    setDownloading(format); setDownloadError(false); setSource(false);
    try {
      const [{ exportChart }, { downloadVisual }] = await Promise.all([import('./chartExport'), import('../../lib/visualExport')]);
      const container = expanded ? viewerRef.current : figureRef.current;
      if (!container) throw new Error('Chart unavailable');
      const exported = await exportChart(container, spec);
      if (generation !== diagramCacheGeneration()) return;
      await downloadVisual(exported, format, spec.title);
    } catch { setDownloadError(true); } finally { setDownloading(undefined); }
  }
  if (!spec) return <div className="my-4"><p role="status" className="text-sm text-muted">This chart has unsupported or invalid data. Its source is available below.</p><CodeBlock code={code} language="json" /></div>;
  const display = expanded && background.current ? background.current : spec;
  const downloads = <><Button size="sm" variant="ghost" disabled={!!downloading} loading={downloading === 'svg'} onClick={() => void download('svg')}>Download SVG</Button><Button size="sm" variant="ghost" disabled={!!downloading} loading={downloading === 'png'} onClick={() => void download('png')}>Download PNG</Button></>;
  return <figure ref={figureRef} className="recharts-figure my-4 min-w-0 overflow-hidden rounded-panel border border-border bg-card" aria-labelledby={titleId}>
    <figcaption className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2"><span id={titleId} className="text-sm font-medium text-heading">{spec.title}</span><span className="flex flex-wrap gap-1">
      <Button size="sm" variant="ghost" aria-pressed={data} onClick={() => setData(value => !value)}>{data ? 'Hide data' : 'View data'}</Button>
      <Button size="sm" variant="ghost" aria-pressed={source} onClick={() => setSource(value => !value)}>{source ? 'Show chart' : 'View source'}</Button>
      <Button size="sm" variant="ghost" onClick={() => setExpanded(true)}>Expand</Button>
      {downloads}
    </span></figcaption>
    {(spec.description || spec.unit) && <p className="px-3 pt-3 text-sm text-muted">{spec.description}{spec.description && spec.unit ? ' ' : ''}{spec.unit ? `Values in ${spec.unit}.` : ''}</p>}
    {spec.model && <details className="mx-3 mt-3 rounded-control border border-border px-3 py-2 text-xs text-muted"><summary className="ui-disclosure cursor-pointer font-medium">{spec.model.kind === 'illustrative' ? 'Illustrative equation model' : 'Equation model'}</summary><p className="mt-2 break-words leading-5">{modelSummary(spec.model)}</p></details>}
    {downloadError && <p role="status" className="px-3 pt-3 text-sm text-muted">Could not download this chart. Try again once it has loaded.</p>}
    {source ? <CodeBlock code={display !== original || display.model ? serializeChartSpec(display) : code} language="json" /> : <ChartCanvas spec={display} />}
    {!expanded && controls}
    {data && <ChartDataTable spec={display} />}
    {expanded && <Dialog ref={viewerRef} open className="visual-fullscreen" aria-label={`Expanded chart: ${spec.title}`} onDismiss={() => setExpanded(false)}><div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-2"><span className="text-sm font-medium text-heading">{spec.title}{spec.unit ? ` (${spec.unit})` : ''}</span><span className="flex flex-wrap items-center gap-1">{downloads}<Button variant="ghost" onClick={() => setExpanded(false)}>Close</Button></span></div><ChartCanvas spec={spec} />{spec.model && <details className="mx-3 rounded-control border border-border px-3 py-2 text-xs text-muted"><summary className="ui-disclosure cursor-pointer">Equation and assumptions</summary><p className="mt-2 break-words">{modelSummary(spec.model)}</p></details>}{controls}</Dialog>}
  </figure>;
}
RechartsFigureContent.displayName = 'RechartsFigure';
export const RechartsFigure = memo(RechartsFigureContent);
RechartsFigure.displayName = 'RechartsFigure';
