import { Component, Suspense, useEffect, useRef, useState, type ReactNode } from 'react';
import { CodeBlock } from './CodeBlock';

type Props = { code: string; kind: 'diagram' | 'chart'; children: ReactNode };
class VisualBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <div className="my-4"><p role="status" className="text-sm text-muted">This {this.props.kind} could not be loaded. Its source is available below.</p><CodeBlock code={this.props.code} language={this.props.kind === 'diagram' ? 'mermaid' : 'json'} /></div> : this.props.children;
  }
}
const waiting = new Map<Element, () => void>();
let observer: IntersectionObserver | undefined;
function observe(element: HTMLElement, ready: () => void) {
  if (!('IntersectionObserver' in window)) { ready(); return () => {}; }
  observer ??= new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) { const notify = waiting.get(entry.target); waiting.delete(entry.target); observer?.unobserve(entry.target); notify?.(); }
    if (!waiting.size) { observer?.disconnect(); observer = undefined; }
  }, { rootMargin: '300px' });
  waiting.set(element, ready); observer.observe(element);
  return () => { waiting.delete(element); observer?.unobserve(element); if (!waiting.size) { observer?.disconnect(); observer = undefined; } };
}
/** Shared viewport gate: surrounding text never waits for a chart/diagram chunk. */
export function DeferredVisual({ code, kind, children }: Props) {
  const ref = useRef<HTMLDivElement>(null); const [visible, setVisible] = useState(false);
  useEffect(() => { if (ref.current && !visible) return observe(ref.current, () => setVisible(true)); }, [visible]);
  const placeholder = <div className={`${kind === 'diagram' ? 'mermaid-placeholder' : 'chart-placeholder'} my-4 rounded-panel border border-border p-4 text-sm text-muted`} role="status">{kind === 'diagram' ? 'Diagram' : 'Chart'}</div>;
  return <div ref={ref} data-visual-kind={kind}>{visible ? <VisualBoundary key={`${kind}:${code}`} code={code} kind={kind}><Suspense fallback={placeholder}>{children}</Suspense></VisualBoundary> : placeholder}</div>;
}
