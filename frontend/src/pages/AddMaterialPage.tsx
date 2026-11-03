import { PageShell } from '../components/workspace/PageShell';
import { buttonStyles } from '../components/ui/Button';
import { ArrowLeft, FilePlus2 } from 'lucide-react';
import { WorkspaceHeader } from '../components/workspace/WorkspaceHeader';
import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { MaterialUpload, MaterialUploadSkeleton } from '../components/library/MaterialUpload';
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

  return <PageShell className="library-page">
    <Link to="/library" className={buttonStyles({ variant: 'ghost', size: 'sm', className: 'w-fit -ml-2 text-muted' })}><ArrowLeft size={15} aria-hidden="true" />Back to Library</Link>
    <WorkspaceHeader title="Add material" description="Your notes, books and ideas. Turn a source into something you can study with Mentra." icon={FilePlus2} />
    {error && <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-danger">{error}<Button variant="secondary" onClick={refresh}>Try again</Button></div>}
    {!capabilities && !error && <MaterialUploadSkeleton />}
    {capabilities && <MaterialUpload contexts={contexts} capabilities={capabilities} onContextCreated={refresh}
      onAccepted={(_id, duplicate) => navigate(`/library?uploaded=${duplicate ? 'duplicate' : 'accepted'}`)} />}
  </PageShell>;
}
