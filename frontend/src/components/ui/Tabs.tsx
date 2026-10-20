import { useLayoutEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export interface TabOption<T extends string> { value: T; label: string; id: string; panel: string; disabled?: boolean }
export function Tabs<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: TabOption<T>[]; onChange: (value: T) => void }) {
  const root = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ left: false, right: false });
  const optionKey = options.map(option => `${option.id}:${option.label}`).join('|');
  function measure() {
    const node = root.current;
    if (!node) return;
    const left = node.scrollLeft > 1, right = node.scrollWidth - node.clientWidth - node.scrollLeft > 1;
    setEdges(previous => previous.left === left && previous.right === right ? previous : { left, right });
  }
  function revealSelected() {
    const node = root.current, selected = node?.querySelector<HTMLElement>('[aria-selected=true]');
    if (!node || !selected) return;
    const viewport = node.getBoundingClientRect(), tab = selected.getBoundingClientRect();
    const left = viewport.left + (node.scrollLeft > 1 ? 36 : 4);
    const right = viewport.right - (node.scrollWidth - node.clientWidth - node.scrollLeft > 1 ? 36 : 4);
    if (tab.left < left) node.scrollLeft += tab.left - left;
    else if (tab.right > right) node.scrollLeft += tab.right - right;
    measure();
  }
  useLayoutEffect(() => {
    const node = root.current;
    if (!node) return;
    const observer = new ResizeObserver(revealSelected);
    observer.observe(node);
    node.querySelectorAll('[role=tab]').forEach(tab => observer.observe(tab));
    revealSelected();
    return () => observer.disconnect();
  }, [value, optionKey]);
  function scroll(direction: number) {
    const node = root.current;
    if (!node) return;
    node.scrollBy({ left: direction * Math.max(120, node.clientWidth * .7), behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
  }
  return <div className="workspace-tabs">
    <div ref={root} role="tablist" aria-label={label} className="workspace-tabs-track" onScroll={measure} onKeyDown={event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      const enabled = options.filter(option => !option.disabled);
      if (!enabled.length) return;
      const current = enabled.findIndex(option => option.id === (event.target as HTMLElement).id);
      if (current < 0) return;
      event.preventDefault();
      const next = event.key === 'Home' ? enabled[0] : event.key === 'End' ? enabled[enabled.length - 1] : enabled[(current + (event.key === 'ArrowRight' ? 1 : enabled.length - 1)) % enabled.length];
      onChange(next.value);
      root.current?.querySelector<HTMLButtonElement>(`[id="${CSS.escape(next.id)}"]`)?.focus({ preventScroll: true });
    }}>{options.map(option => <button key={option.value} type="button" role="tab" id={option.id} aria-controls={option.panel} aria-selected={value === option.value} tabIndex={value === option.value ? 0 : -1} disabled={option.disabled} onClick={() => onChange(option.value)}>{option.label}</button>)}</div>
    {edges.left && <div className="workspace-tabs-edge workspace-tabs-edge-left"><button type="button" tabIndex={-1} className="workspace-tabs-scroll" aria-label={`Scroll ${label.toLowerCase()} left`} onClick={() => scroll(-1)}><ChevronLeft size={16} aria-hidden="true" /></button></div>}
    {edges.right && <div className="workspace-tabs-edge workspace-tabs-edge-right"><button type="button" tabIndex={-1} className="workspace-tabs-scroll" aria-label={`Scroll ${label.toLowerCase()} right`} onClick={() => scroll(1)}><ChevronRight size={16} aria-hidden="true" /></button></div>}
  </div>;
}
