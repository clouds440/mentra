import { useEffect, useRef, useState } from 'react';
import { downloadFile } from '../../services/files';
import type { SourceVisual } from '../../types/rag';

function SourceDiagram({ visual, archived }: { visual: SourceVisual; archived: boolean }) {
  const element = useRef<HTMLElement>(null);
  const [url, setUrl] = useState('');
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = '';
    setUrl(''); setError(false);
    async function load() {
      try {
        const file = await downloadFile(`/api/v1/rag/visuals/${encodeURIComponent(visual.id)}/source?include_archived=${archived}`, controller.signal);
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(file); setUrl(objectUrl);
      } catch { if (!controller.signal.aborted) setError(true); }
    }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { observer.disconnect(); void load(); }
    }, { rootMargin: '200px' });
    if (element.current) observer.observe(element.current);
    return () => { observer.disconnect(); controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [visual.id, archived]);
  return <figure ref={element} className="my-4 min-h-16 rounded-xl border border-border p-3">
    {url && <a href={url} target="_blank" rel="noreferrer" aria-label={`Open ${visual.caption}`}><img src={url} alt={visual.caption} loading="lazy" className="mx-auto max-h-[60dvh] max-w-full object-contain" /></a>}
    <figcaption className="mt-2 text-xs text-muted">{error ? 'This source diagram could not be loaded. Open the original file.' : visual.caption}</figcaption>
  </figure>;
}

export function SourceDiagrams({ visuals, archived }: { visuals?: SourceVisual[]; archived: boolean }) {
  return <>{visuals?.slice(0, 4).map(visual => <SourceDiagram key={visual.id} visual={visual} archived={archived} />)}</>;
}
