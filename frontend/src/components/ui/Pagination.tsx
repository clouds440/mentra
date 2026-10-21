import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from './Button';

interface PaginationProps { page: number; pages: number; onChange: (page: number) => void; disabled?: boolean; label?: string }

export function Pagination({page, pages, onChange, disabled = false, label = 'Pages'}: PaginationProps) {
  if (pages <= 1) return null;
  const numbers = pages <= 7 ? Array.from({length:pages}, (_, i) => i + 1)
    : [...new Set([1, pages, ...Array.from({length:5}, (_, i) => Math.min(pages - 4, Math.max(1, page - 2)) + i)])].sort((a,b) => a-b);
  const control = 'h-7 min-h-7 min-w-7 px-2 py-0 text-xs tabular-nums';
  return <nav aria-label={label} className="pagination flex flex-wrap items-center gap-1">
    <Button variant="ghost" size="sm" className={control} disabled={disabled || page <= 1} aria-label="Previous page" title="Previous page" onClick={() => onChange(page - 1)}><ChevronLeft size={14} strokeWidth={1.5} aria-hidden="true" /></Button>
    {numbers.map((number, index) => <span key={number} className="contents">
      {index > 0 && number - numbers[index-1] > 1 && <span aria-hidden="true" className="px-1 text-subtle">…</span>}
      <Button variant="ghost" size="sm" disabled={disabled} aria-label={`Page ${number}`} aria-current={number === page ? 'page' : undefined}
        className={`${control} ${number === page ? 'bg-active text-accent' : 'text-muted'}`} onClick={() => onChange(number)}>{number}</Button>
    </span>)}
    <Button variant="ghost" size="sm" className={control} disabled={disabled || page >= pages} aria-label="Next page" title="Next page" onClick={() => onChange(page + 1)}><ChevronRight size={14} strokeWidth={1.5} aria-hidden="true" /></Button>
  </nav>;
}
