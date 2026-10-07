import {
  BookOpenText,
  ClipboardCheck,
  Lightbulb,
  Sparkles,
} from 'lucide-react';
import mentraLogo from '../../assets/mentra-logo.png';
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
        className="mb-6 grid h-12 w-12 place-items-center"
      >
        <img alt="" className="h-12 w-12 object-contain" src={mentraLogo} />
      </div>
      <p className="text-sm font-medium tracking-wide text-accent/90">Mentra</p>
      <h1 className="mt-3 text-2xl font-medium tracking-tight text-foreground sm:text-3xl">
        What are we learning today?
      </h1>
      <p className="mt-3 max-w-md text-sm leading-6 text-subtle">
        Start with a question, or choose a prompt to find your next step.
      </p>
      <div className="mt-8 flex max-w-xl flex-wrap justify-center gap-2">
        {suggestions.map(({ label, prompt, icon: Icon }) => (
          <Button
            className="gap-2 rounded-full border-border px-3.5 text-xs font-normal text-body hover:border-border-strong hover:text-foreground"
            key={label}
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
