import type { AssessmentQuestion } from '../../types/assessments';

/** Saved target labels describe coverage; they never imply whole-topic mastery. */
export function LearningTargetLabels({ question }: { question: AssessmentQuestion }) {
  return <LearningTargetGroups targets={question.learning_targets ?? []} />;
}

/** Shared by per-question coverage and the completed assessment summary. */
export function LearningTargetGroups({ targets, stacked = false }: {
  targets: NonNullable<AssessmentQuestion['learning_targets']>;
  stacked?: boolean;
}) {
  if (!targets.length) return null;
  const groups = new Map<string, { name?: string; skills: typeof targets }>();
  for (const target of targets) {
    const key = target.topic_id || target.topic_name || '';
    const group = groups.get(key) ?? { name: target.topic_name, skills: [] };
    group.name ??= target.topic_name;
    if (!group.skills.some(skill => skill.subskill_id === target.subskill_id)) group.skills.push(target);
    groups.set(key, group);
  }
  return <ul aria-label="Skills practised" className="space-y-1 text-xs text-muted">{Array.from(groups, ([key, group]) => <li key={key}>
    {group.name && <div dir="auto" className="font-medium">{group.name}</div>}
    <ul className={stacked ? 'mt-1 list-disc space-y-1 ps-4' : 'flex flex-wrap gap-x-3 gap-y-1'}>{group.skills.map(skill => <li dir="auto" key={skill.subskill_id}>{skill.subskill_name}</li>)}</ul>
  </li>)}</ul>;
}
