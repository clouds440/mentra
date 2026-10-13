import { useEffect, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { Button } from '../ui';
import { markdownPlainText } from '../../lib/markdownPlainText';

export function CopyResponse({ content, subject = 'response' }: { content: string; subject?: 'response' | 'message' }) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => { setCopied(false); setError(false); }, [content]);
  useEffect(() => { if (copied) { const timer = setTimeout(() => setCopied(false), 2000); return () => clearTimeout(timer); } }, [copied]);
  async function copy() {
    try { await navigator.clipboard.writeText(markdownPlainText(content)); setCopied(true); setError(false); }
    catch { setError(true); }
  }
  return <div className="mt-3 flex flex-wrap items-center gap-2">
    <Button size="sm" variant="ghost" aria-label={copied ? (subject === 'message' ? 'Message copied' : 'Response copied') : `Copy ${subject}`} onClick={() => void copy()}>
      {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}{copied ? 'Copied' : 'Copy'}
    </Button>
    {error && <span role="status" className="text-xs text-muted">Couldn’t copy. Please try again.</span>}
  </div>;
}
