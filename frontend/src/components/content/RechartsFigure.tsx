import { Component, lazy, memo, Suspense, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { Button, Dialog } from '../ui';
import { CodeBlock } from './CodeBlock';
import { parseChartSpec, type ChartSpec } from '../../lib/chartSpec';
import { cacheChart, readChart, diagramCacheGeneration } from '../../lib/richContentCache';

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
function RechartsFigureContent({ code }: { code: string }) {
  const titleId = useId();
  const figureRef = useRef<HTMLElement>(null); const viewerRef = useRef<HTMLDialogElement>(null);
  const [downloading, setDownloading] = useState<'svg' | 'png'>(); const [downloadError, setDownloadError] = useState(false);
  const spec = useMemo(() => {
    const cached = readChart(code);
    if (cached !== undefined) return cached;
    const parsed = parseChartSpec(code); cacheChart(code, parsed); return parsed;
  }, [code]);
  const [source, setSource] = useState(false); const [data, setData] = useState(false); const [expanded, setExpanded] = useState(false);
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
  const downloads = <><Button size="sm" variant="ghost" disabled={!!downloading} loading={downloading === 'svg'} onClick={() => void download('svg')}>Download SVG</Button><Button size="sm" variant="ghost" disabled={!!downloading} loading={downloading === 'png'} onClick={() => void download('png')}>Download PNG</Button></>;
  return <figure ref={figureRef} className="recharts-figure my-4 min-w-0 overflow-hidden rounded-panel border border-border bg-card" aria-labelledby={titleId}>
    <figcaption className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2"><span id={titleId} className="text-sm font-medium text-heading">{spec.title}</span><span className="flex flex-wrap gap-1">
      <Button size="sm" variant="ghost" aria-pressed={data} onClick={() => setData(value => !value)}>{data ? 'Hide data' : 'View data'}</Button>
      <Button size="sm" variant="ghost" aria-pressed={source} onClick={() => setSource(value => !value)}>{source ? 'Show chart' : 'View source'}</Button>
      <Button size="sm" variant="ghost" onClick={() => setExpanded(true)}>Expand</Button>
      {downloads}
    </span></figcaption>
    {(spec.description || spec.unit) && <p className="px-3 pt-3 text-sm text-muted">{spec.description}{spec.description && spec.unit ? ' ' : ''}{spec.unit ? `Values in ${spec.unit}.` : ''}</p>}
    {downloadError && <p role="status" className="px-3 pt-3 text-sm text-muted">Could not download this chart. Try again once it has loaded.</p>}
    {source ? <CodeBlock code={code} language="json" /> : <ChartCanvas spec={spec} />}
    {data && <div className="markdown-table-scroll p-3"><table><caption className="sr-only">{spec.title} — exact data{spec.unit ? ` (${spec.unit})` : ''}</caption><thead><tr><th scope="col">{spec.xKey}</th>{spec.series.map(item => <th key={item.dataKey} scope="col">{item.name}{spec.unit ? ` (${spec.unit})` : ''}</th>)}</tr></thead><tbody>{spec.data.map((row, i) => <tr key={i}><th scope="row">{row[spec.xKey]}</th>{spec.series.map(item => <td key={item.dataKey}>{row[item.dataKey] === null ? '—' : String(row[item.dataKey])}</td>)}</tr>)}</tbody></table></div>}
    {expanded && <Dialog ref={viewerRef} open className="visual-fullscreen" aria-label={`Expanded chart: ${spec.title}`} onDismiss={() => setExpanded(false)}><div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-2"><span className="text-sm font-medium text-heading">{spec.title}{spec.unit ? ` (${spec.unit})` : ''}</span><span className="flex flex-wrap items-center gap-1">{downloads}<Button variant="ghost" onClick={() => setExpanded(false)}>Close</Button></span></div><ChartCanvas spec={spec} /></Dialog>}
  </figure>;
}
RechartsFigureContent.displayName = 'RechartsFigure';
export const RechartsFigure = memo(RechartsFigureContent);
RechartsFigure.displayName = 'RechartsFigure';
