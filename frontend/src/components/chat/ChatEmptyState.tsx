import {
  BookOpenText,
  ClipboardCheck,
  Lightbulb,
  Sparkles,
} from 'lucide-react';
import { MentraLogo } from '../brand/MentraLogo';
import { Button } from '../ui';

const suggestions = [
  { label: 'Explain a concept', prompt: 'Help me understand a concept. Ask me which topic to explore.', icon: Lightbulb },
  { label: 'Quiz me', prompt: 'Give me a short quiz to practice what I am learning.', icon: ClipboardCheck },
  { label: 'Study my material', prompt: 'study-material', icon: BookOpenText },
  { label: 'Prepare for an exam', prompt: 'Help me prepare for an exam. Use what we know, and ask only for any essential missing details.', icon: Sparkles },
];

interface ChatEmptyStateProps {
  onChooseSuggestion: (prompt: string) => void;
  disabled?: boolean;
}

export function ChatEmptyState({ onChooseSuggestion, disabled }: ChatEmptyStateProps) {
  return (
    <section className="mx-auto flex min-h-full w-full max-w-2xl flex-col items-center justify-center px-4 pb-6 pt-16 text-center sm:pb-10">
      <div
        aria-hidden="true"
        className="mb-6 grid h-12 w-12 place-items-center"
      >
        <MentraLogo className="h-12 w-12" />
      </div>
      <p className="text-sm font-medium tracking-wide text-accent/90">Mentra</p>
      <h1 className="mt-3 text-2xl font-medium tracking-tight text-foreground sm:text-3xl">
        What are we learning today?
      </h1>
      <p className="mt-3 max-w-md text-sm leading-6 text-subtle">
        Ask naturally, or choose where to begin.
      </p>
      <div className="mt-8 grid w-full max-w-lg grid-cols-1 gap-2 sm:grid-cols-2">
        {suggestions.map(({ label, prompt, icon: Icon }) => (
          <Button
            className="h-auto min-h-12 justify-start gap-3 rounded-panel border-border bg-card px-4 py-3 text-sm font-normal text-body hover:border-border-strong hover:text-foreground"
            key={label}
            disabled={disabled}
            onClick={() => onChooseSuggestion(prompt)}
            size="sm"
            variant="secondary"
          >
            <Icon aria-hidden="true" className="text-accent/80" size={14} />
            {label}
          </Button>
        ))}
      </div>
    </section>
  );
}
