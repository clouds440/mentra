import { useState } from 'react';
import { Printer } from 'lucide-react';
import { Button } from '../ui';
import type { Assessment } from '../../types/assessments';

export function PrintPaperButton({ assessment }: { assessment: Assessment }) {
  const [busy,setBusy]=useState(false), [error,setError]=useState('');
  async function print() {
    if (busy) return; setBusy(true); setError('');
    try { const { printAssessment } = await import('./printAssessment'); await printAssessment(assessment); }
    catch { setError('Could not open print. Please try again.'); }
    finally { setBusy(false); }
  }
  return <span className="inline-flex flex-wrap items-center gap-2"><Button size="sm" variant="ghost" loading={busy} onClick={() => void print()}><Printer size={13} aria-hidden="true" />Print paper</Button>{error && <span role="alert" className="text-xs text-danger">{error}</span>}</span>;
}
