import { ArrowUpRight, BookOpenText, ClipboardCheck, Lightbulb, Sparkles } from 'lucide-react';
import { m, useReducedMotion } from '../ui/Motion';

const suggestions = [
  { label: 'Explain a concept', detail: 'Make the complex click', prompt: 'Help me understand a concept. Ask me which topic to explore.', icon: Lightbulb },
  { label: 'Quiz me', detail: 'Find out what you know', prompt: 'Give me a short quiz to practice what I am learning.', icon: ClipboardCheck },
  { label: 'Study my material', detail: 'Start with your own sources', prompt: 'study-material', icon: BookOpenText },
  { label: 'Prepare for an exam', detail: 'Build confidence, step by step', prompt: 'Help me prepare for an exam. Use what we know, and ask only for any essential missing details.', icon: Sparkles },
];

interface ChatEmptyStateProps {
  onChooseSuggestion: (prompt: string) => void;
  disabled?: boolean;
}

export function ChatEmptyState({ onChooseSuggestion, disabled }: ChatEmptyStateProps) {
  const reducedMotion = useReducedMotion();
  return <section className="chat-welcome">
    <m.div className="chat-welcome-intro" initial={reducedMotion ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: .22 }}>
      <p className="welcome-eyebrow"><span aria-hidden="true" />A little curiosity goes a long way</p>
      <h1>What are we<br /><span>learning today?</span></h1>
      <p className="welcome-description">Room to think. A guide when you need one.<br className="hidden sm:block" /> Follow your curiosity, one conversation at a time.</p>
    </m.div>
    <div className="welcome-suggestions" aria-label="Ways to start learning">
      {suggestions.map(({ label, detail, prompt, icon: Icon }, index) => <m.button
        className="welcome-suggestion" key={label} type="button" disabled={disabled} aria-label={label}
        onClick={() => onChooseSuggestion(prompt)}
        initial={reducedMotion ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: .2, delay: reducedMotion ? 0 : index * .035 }}
      ><span className="suggestion-icon"><Icon size={19} strokeWidth={1.65} aria-hidden="true" /></span>
        <span className="suggestion-copy"><span>{label}</span><small>{detail}</small></span>
        <ArrowUpRight size={16} className="suggestion-arrow" aria-hidden="true" />
      </m.button>)}
    </div>
  </section>;
}
