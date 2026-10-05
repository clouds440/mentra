import {
  BookOpenText,
  ClipboardCheck,
  Lightbulb,
  Sparkles,
} from 'lucide-react';
import { Button } from '../ui';

const suggestions = [
  { label: 'Explain a concept', prompt: 'Help me understand a concept: ', icon: Lightbulb },
  { label: 'Quiz me', prompt: 'Quiz me on ', icon: ClipboardCheck },
  { label: 'Study my material', prompt: 'Help me study ', icon: BookOpenText },
  { label: 'Prepare for an exam', prompt: 'Help me prepare for an exam on ', icon: Sparkles },
];

interface ChatEmptyStateProps {
  onChooseSuggestion: (prompt: string) => void;
}

export function ChatEmptyState({ onChooseSuggestion }: ChatEmptyStateProps) {
  return (
    <section className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center px-4 pb-10 text-center">
      <div
        aria-hidden="true"
        className="mb-6 grid h-12 w-12 place-items-center rounded-2xl border border-sky-200/15 bg-sky-200/[0.06] text-sky-200"
      >
        <Sparkles size={20} strokeWidth={1.7} />
      </div>
      <p className="text-sm font-medium tracking-wide text-sky-200/90">Mentra</p>
      <h1 className="mt-3 text-2xl font-medium tracking-tight text-slate-100 sm:text-3xl">
        What are we learning today?
      </h1>
      <p className="mt-3 max-w-md text-sm leading-6 text-slate-500">
        Start with a question, or choose a prompt to find your next step.
      </p>
      <div className="mt-8 flex max-w-xl flex-wrap justify-center gap-2">
        {suggestions.map(({ label, prompt, icon: Icon }) => (
          <Button
            className="gap-2 rounded-full border-white/[0.09] px-3.5 text-xs font-normal text-slate-300 hover:border-white/15 hover:text-white"
            key={label}
            onClick={() => onChooseSuggestion(prompt)}
            size="sm"
            variant="secondary"
          >
            <Icon aria-hidden="true" className="text-sky-200/80" size={14} />
            {label}
          </Button>
        ))}
      </div>
    </section>
  );
}
