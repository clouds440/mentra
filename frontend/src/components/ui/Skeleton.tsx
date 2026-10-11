import { cn } from '../../utils/cn';
import { Spinner } from './Spinner';

type Shape = 'bar' | 'text' | 'card' | 'button' | 'table' | 'list' | 'chat' | 'form';
export function Skeleton({ variant = 'text', rows = 3, columns = 4, className }: { variant?: Shape; rows?: number; columns?: number; className?: string }) {
  const bar = (width = 'w-full', height = 'h-3') => <div className={cn('rounded-md bg-border', width, height)} />;
  const lines = <div className="space-y-3">{Array.from({ length: rows }, (_, i) => <div key={i}>{bar(i === rows - 1 ? 'w-2/3' : 'w-full')}</div>)}</div>;
  return <div role="status" aria-label="Loading" className={cn('w-full animate-pulse motion-reduce:animate-none', className)}><div aria-hidden="true">
    {variant === 'bar' ? bar() : variant === 'button' ? bar('w-28', 'h-10') : variant === 'text' ? lines
      : variant === 'table' ? <div className="overflow-hidden rounded-xl border border-border">{Array.from({ length: rows + 1 }, (_, i) => <div key={i} className="flex gap-5 border-b border-border p-4 last:border-0">{Array.from({ length: columns }, (_, j) => <div key={j} className="min-w-0 flex-1">{bar()}</div>)}</div>)}</div>
      : variant === 'list' ? <div className="space-y-4">{Array.from({ length: rows }, (_, i) => <div key={i} className="space-y-3 py-2">{bar('w-3/4')}{bar('w-1/2', 'h-2')}</div>)}</div>
      : variant === 'chat' ? <div className="mx-auto max-w-3xl space-y-8 p-5">{Array.from({ length: rows }, (_, i) => <div key={i} className={cn('rounded-2xl border border-border p-5', i % 2 === 0 ? 'ml-auto w-2/3' : 'w-5/6')}>{lines}</div>)}</div>
      : variant === 'form' ? <div className="space-y-5 rounded-xl border border-border p-5">{Array.from({ length: rows }, (_, i) => <div key={i} className="space-y-2">{bar('w-24')}{bar('w-full', 'h-10')}</div>)}{bar('w-28', 'h-10')}</div>
      : <div className="space-y-4">{Array.from({ length: rows }, (_, i) => <div key={i} className="space-y-4 rounded-xl border border-border p-5">{bar('w-1/3', 'h-4')}{lines}{bar('w-24', 'h-9')}</div>)}</div>}
  </div></div>;
}

export function PageLoader({ className }: { className?: string }) {
  return <div className={cn('grid h-full min-h-40 w-full place-items-center text-muted', className)}><Spinner className="h-5 w-5" /></div>;
}
