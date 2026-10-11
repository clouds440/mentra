import { Skeleton } from '../components/ui/Skeleton';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { MaterialUpload } from '../components/library/MaterialUpload';
import { Button } from '../components/ui';
import { getCapabilities, listContexts, materialError } from '../services/rag';
import type { LearningContext, RAGCapabilities } from '../types/rag';

export function AddMaterialPage() {
  const navigate = useNavigate();
  const [contexts, setContexts] = useState<LearningContext[]>([]);
  const [capabilities, setCapabilities] = useState<RAGCapabilities>();
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const refresh = useCallback(() => setReload(value => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const [ctx, caps] = await Promise.all([listContexts(controller.signal), getCapabilities(controller.signal)]);
        if (!controller.signal.aborted) { setContexts(ctx); setCapabilities(caps); setError(''); }
      } catch (error) { if (!controller.signal.aborted) setError(materialError(error)); }
    }
    void load();
    return () => controller.abort();
  }, [reload]);

  return <div className="h-full overflow-y-auto"><section className="page-container">
    <Link to="/library" className="text-sm text-accent hover:underline">Back to Library</Link>
    <div><h1 className="page-title">Add material</h1><p className="mt-2 text-sm text-muted">Upload a source and choose its learning context.</p></div>
    {error && <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-danger">{error}<Button variant="secondary" onClick={refresh}>Try again</Button></div>}
    {!capabilities && !error && <Skeleton variant="form" />}
    {capabilities && <MaterialUpload contexts={contexts} capabilities={capabilities} onContextCreated={refresh}
      onAccepted={(_id, duplicate) => navigate(`/library?uploaded=${duplicate ? 'duplicate' : 'accepted'}`)} />}
  </section></div>;
}
