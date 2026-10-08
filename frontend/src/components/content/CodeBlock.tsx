import { memo, useEffect, useId, useMemo, useState } from 'react';
import { Check, Copy, FileCode2, WrapText } from 'lucide-react';
import { Button } from '../ui';
import { resolveLanguage } from '../../lib/codeLanguages';
import { highlightCode } from '../../lib/highlightCode';

export const CodeBlock = memo(function CodeBlock({ code, language, filename }: { code: string; language?: string; filename?: string }) {
  const { id, label } = resolveLanguage(language);
  const labelId = useId();
  const [highlight, setHighlight] = useState<{ code: string; id: string; html: string }>();
  const [wrap, setWrap] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const lines = useMemo(() => code.split('\n').length, [code]);
  useEffect(() => {
    let active = true;
    const request = highlightCode(code, id);
    void request.result.then(html => { if (active && html !== null) setHighlight({ code, id, html }); });
    return () => { active = false; request.cancel(); };
  }, [code, id]);
  useEffect(() => { setCopied(false); setCopyError(false); }, [code]);
  useEffect(() => { if (copied) { const timer = setTimeout(() => setCopied(false), 2000); return () => clearTimeout(timer); } }, [copied]);
  async function copy() {
    try { await navigator.clipboard.writeText(code); setCopied(true); setCopyError(false); }
    catch { setCopyError(true); }
  }
  const html = highlight?.code === code && highlight.id === id ? highlight.html : null;
  return <figure className="code-block" data-language={id}>
    <figcaption className="code-toolbar">
      <div className="code-identity"><FileCode2 size={15} aria-hidden="true" /><span id={labelId} className="code-language">{label}</span>{filename && <span className="code-filename" title={filename}>{filename}</span>}<span className="code-line-count">{lines} {lines === 1 ? 'line' : 'lines'}</span></div>
      <div className="code-actions">
        <Button variant="ghost" size="sm" className="code-action" aria-label="Wrap code lines" aria-pressed={wrap} title="Wrap lines" onClick={() => setWrap(value => !value)}><WrapText size={16} aria-hidden="true" /></Button>
        <Button variant="ghost" size="sm" className="code-action code-copy" aria-label={copied ? 'Code copied' : 'Copy code'} onClick={() => void copy()}>{copied ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}<span>{copied ? 'Copied' : 'Copy'}</span></Button>
      </div>
    </figcaption>
    <div className={`code-scroll${wrap ? ' code-wrapped' : ''}`} tabIndex={0} role="region" aria-labelledby={labelId}>
      <div className="code-layout">
        {!wrap && lines <= 2000 && <div className="code-gutter" aria-hidden="true">{Array.from({ length: lines }, (_, index) => <span key={index}>{index + 1}</span>)}</div>}
        <pre className="code-pre">{html !== null ? <code className={`language-${id}`} dangerouslySetInnerHTML={{ __html: html }} /> : <code className={`language-${id}`}>{code}</code>}</pre>
      </div>
    </div>
    <span className={copyError ? 'code-copy-error' : 'sr-only'} role="status">{copyError ? 'Could not copy. Select the code and copy it manually.' : copied ? 'Code copied to clipboard.' : ''}</span>
  </figure>;
});
