import type { ReactNode } from 'react';

/** Shared navigation for assessments and ungraded conversational question sets. */
export function QuestionProgress({ answered, index, disabled, onNavigate, label = 'Quiz', aside }: {
  answered: boolean[]; index: number; disabled: boolean; onNavigate: (index: number) => void;
  label?: string; aside?: ReactNode;
}) {
  const count = answered.filter(Boolean).length;
  return <div className="space-y-1">
    <div className="flex flex-wrap items-center justify-between gap-2"><p role="status" className="m-0 text-xs font-medium text-muted">Question {index + 1} of {answered.length} · {count} answered</p>{aside}</div>
    <nav aria-label={`${label} questions`} className="assessment-steps flex gap-1 overflow-x-auto">{answered.map((done, i) => <button key={i} type="button" title={`Question ${i+1}`} aria-label={`Go to question ${i + 1}${done ? ', answered' : ''}`} aria-current={index === i ? 'step' : undefined} disabled={disabled} onClick={() => onNavigate(i)} className="ui-button min-h-8 min-w-6 flex-1 rounded-control px-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"><span aria-hidden="true" className={`block h-1 w-full rounded-full transition-colors ${index===i ? 'bg-accent' : done ? 'bg-accent/45' : 'bg-border-strong'}`} /></button>)}</nav>
  </div>;
}
