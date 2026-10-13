import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from './Button';

interface PaginationProps { page: number; pages: number; onChange: (page: number) => void; disabled?: boolean; label?: string }

export function Pagination({page, pages, onChange, disabled = false, label = 'Pages'}: PaginationProps) {
  if (pages <= 1) return null;
  const numbers = pages <= 7 ? Array.from({length:pages}, (_, i) => i + 1)
    : [...new Set([1, pages, ...Array.from({length:5}, (_, i) => Math.min(pages - 4, Math.max(1, page - 2)) + i)])].sort((a,b) => a-b);
  return <nav aria-label={label} className="flex flex-wrap items-center gap-1">
    <Button variant="ghost" size="sm" disabled={disabled || page <= 1} aria-label="Previous page" onClick={() => onChange(page - 1)}><ChevronLeft size={15} aria-hidden="true" /><span className="sr-only sm:not-sr-only">Previous</span></Button>
    {numbers.map((number, index) => <span key={number} className="contents">
      {index > 0 && number - numbers[index-1] > 1 && <span aria-hidden="true" className="px-1 text-subtle">…</span>}
      <Button variant="ghost" size="sm" disabled={disabled} aria-label={`Page ${number}`} aria-current={number === page ? 'page' : undefined}
        className={number === page ? 'bg-active text-accent' : 'text-muted'} onClick={() => onChange(number)}>{number}</Button>
    </span>)}
    <Button variant="ghost" size="sm" disabled={disabled || page >= pages} aria-label="Next page" onClick={() => onChange(page + 1)}><span className="sr-only sm:not-sr-only">Next</span><ChevronRight size={15} aria-hidden="true" /></Button>
  </nav>;
}
