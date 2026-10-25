import { useEffect, useRef, useState } from 'react';
import { Printer, Download } from 'lucide-react';
import { apiBlob, ApiError } from '../../services/api';
import { Button } from '../ui';
import type { Assessment } from '../../types/assessments';

export function PrintPaperButton({ assessment }: { assessment: Assessment }) {
  const [busy,setBusy]=useState(false), [error,setError]=useState('');
  const active = useRef<AbortController>();
  const [downloading, setDownloading] = useState(false);
  useEffect(() => () => active.current?.abort(), []);
  async function download() {
    if (downloading) return;
    const controller = new AbortController(); active.current = controller;
    setDownloading(true); setError('');
    try {
      const blob = await apiBlob(`/api/v1/assessments/${encodeURIComponent(assessment.id)}/paper.pdf`, controller.signal);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob), link = document.createElement('a');
      link.href = url; link.download = `${assessment.title.replace(/[\\/:*?"<>|]/g, '-').slice(0,100) || 'assessment'}-question-paper.pdf`;
      document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof ApiError ? reason.message : 'Could not download the question paper. Try again.'); }
    finally { if (!controller.signal.aborted) setDownloading(false); }
  }
  async function print() {
    if (busy) return; setBusy(true); setError('');
    try { const { printAssessment } = await import('./printAssessment'); await printAssessment(assessment); }
    catch { setError('Could not open print. Please try again.'); }
    finally { setBusy(false); }
  }
  return <span className="inline-flex flex-wrap items-center gap-2"><Button size="sm" variant="secondary" loading={downloading} onClick={() => void download()}><Download size={14} aria-hidden="true" />Download question paper PDF</Button><Button size="sm" variant="ghost" loading={busy} onClick={() => void print()}><Printer size={13} aria-hidden="true" />Print paper</Button>{error && <span role="alert" className="text-xs text-danger">{error}</span>}</span>;
}
