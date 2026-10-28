import type { ReactNode } from 'react';
import { Check } from 'lucide-react';
import { ProgressBar } from '../ui/ProgressBar';

/** Shared navigation for assessments and ungraded conversational question sets. */
export function QuestionProgress({ answered, index, disabled, onNavigate, label = 'Quiz', aside }: {
  answered: boolean[]; index: number; disabled: boolean; onNavigate: (index: number) => void;
  label?: string; aside?: ReactNode;
}) {
  const count = answered.filter(Boolean).length;
  return <>
    <div className="flex flex-wrap items-center justify-between gap-2"><p role="status" className="text-xs font-medium text-muted">Question {index + 1} of {answered.length} · {count} answered</p>{aside}</div>
    <ProgressBar label={`${label} progress`} value={count} max={answered.length} showValue={false} />
    <nav aria-label={`${label} questions`} className="flex flex-wrap gap-1.5">{answered.map((done, i) => <button key={i} type="button" aria-label={`Go to question ${i + 1}${done ? ', answered' : ''}`} aria-current={index === i ? 'step' : undefined} disabled={disabled} onClick={() => onNavigate(i)} className={`ui-button grid min-h-8 min-w-8 place-items-center rounded-md border px-1 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-accent ${index === i ? 'border-accent bg-accent/10 text-accent' : done ? 'border-border-strong bg-active text-heading' : 'border-border text-muted hover:bg-hover'}`}>{done && index !== i ? <Check size={13} aria-hidden="true" /> : i + 1}</button>)}</nav>
  </>;
}
