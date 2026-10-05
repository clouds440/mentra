import { Compass } from 'lucide-react';
import { WorkspacePlaceholder } from './WorkspacePlaceholder';

export function ProgressPage() {
  return (
    <WorkspacePlaceholder
      description="A clear picture of what you’re learning, shaped over time."
      emptyDescription="As you learn with Mentra, this space can reflect your strengths, the ideas you’re exploring, and where you may want to spend more time."
      emptyTitle="Your learning profile starts with you."
      eyebrow="Your learning journey"
      icon={<Compass aria-hidden="true" size={19} strokeWidth={1.7} />}
      title="Progress"
    />
  );
}
