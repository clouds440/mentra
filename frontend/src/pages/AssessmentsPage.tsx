import { ClipboardCheck } from 'lucide-react';
import { WorkspacePlaceholder } from './WorkspacePlaceholder';

const assessmentAreas = ['Quizzes', 'Mock exams', 'Assessment history'];

export function AssessmentsPage() {
  return (
    <WorkspacePlaceholder
      description="A place to practice what you’re learning and see how your understanding develops."
      emptyDescription="Assessments you create with Mentra will appear here. Nothing is scheduled or being tracked yet."
      emptyTitle="Your practice space is ready when you are."
      eyebrow="Practice and reflect"
      icon={<ClipboardCheck aria-hidden="true" size={19} strokeWidth={1.7} />}
      title="Assessments"
    >
      <ul aria-label="Assessment areas" className="mt-8 flex flex-wrap gap-2">
        {assessmentAreas.map((area) => (
          <li
            className="rounded-lg border border-white/[0.07] px-3 py-2 text-xs text-slate-400"
            key={area}
          >
            {area}
          </li>
        ))}
      </ul>
    </WorkspacePlaceholder>
  );
}
