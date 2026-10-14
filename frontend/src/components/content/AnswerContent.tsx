import { MarkdownContent } from './MarkdownContent';

export function AnswerContent({content}:{content:string}) {
  return <div role="group" aria-label="Your answer" className="min-w-0 space-y-2 rounded-lg border border-accent/40 bg-accent/10 p-3 text-sm">
    <span className="inline-flex rounded border border-accent/25 bg-card px-1.5 py-0.5 text-[11px] font-semibold text-accent">Your answer</span>
    <MarkdownContent content={content || 'Not answered'} />
  </div>;
}
