import type { Assessment, AssessmentQuestion } from '../../types/assessments';
import { Clock3, FileText } from 'lucide-react';
import { MarkdownContent } from '../content/MarkdownContent';
import { PrintPaperButton } from './PrintPaperButton';
import { useState } from 'react';

export const showsAssessmentMarks = (assessment: Assessment) => !assessment.preferences?.result_style || assessment.preferences.result_style === 'marks';

export const questionLabel = (question: AssessmentQuestion, index: number) => `Question ${question.number ?? index + 1}${question.part ? question.part.split('.').map(part => ` (${part})`).join('') : ''}`;
export const questionKind = (question: AssessmentQuestion) => question.question_type === 'true_false' ? 'True or false' : question.answer_mode === 'multiple_choice' ? 'Select all that apply' : question.options?.length ? 'Multiple choice' : question.question_type ? question.question_type.replace(/_/g, ' ') : 'Written response';
export function selectedIds(question: AssessmentQuestion, answer = ''): string[] {
  if (question.answer_mode === 'multiple_choice') {
    try { const ids: unknown = JSON.parse(answer); return Array.isArray(ids) && ids.every(value => typeof value === 'string') ? ids : []; } catch { return []; }
  }
  return answer ? [answer] : [];
}
export function selectedAnswer(question: AssessmentQuestion, answer = '') {
  if (question.answer_mode === 'multiple_choice') return question.options?.filter(option => selectedIds(question, answer).includes(option.id)).map(option => option.label).join('\n\n') || answer;
  return question.options?.find(option => option.id === answer)?.label ?? answer;
}

export function PracticeNotice({ assessment }: { assessment: Assessment }) {
  const [expanded, setExpanded] = useState(false);
  const source = assessment.practice_source;
  if (!source) return null;
  return <aside className="space-y-2 rounded-lg border border-border bg-surface p-3" aria-label="Repeated practice">
    <p className="text-xs text-muted">This practice is based on previously graded questions. Results are saved as practice and do not count as a fresh independent demonstration.</p>
    {!!source.reference_questions.length && <details onToggle={event => setExpanded(event.currentTarget.open)}><summary className="cursor-pointer text-xs text-accent">Original paper context and reference questions</summary>{expanded && <div className="mt-3 space-y-3">
      <MarkdownContent content={source.instructions} />
      {source.reference_questions.map((question, index) => <div key={question.id} className="space-y-1 text-sm"><p className="font-medium">{questionLabel(question, index)}</p><MarkdownContent content={[question.context, question.prompt, ...(question.options?.map(option => `${option.id}: ${option.label}`) ?? [])].filter(Boolean).join('\n\n')} /></div>)}
    </div>}</details>}
  </aside>;
}

export function PaperHeader({ assessment, printMode = false }: { assessment: Assessment; printMode?: boolean }) {
  const paper = assessment.paper;
  if (!paper) return null;
  return <header className="space-y-3 rounded-lg border border-border-strong bg-surface p-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-accent"><FileText size={14} aria-hidden="true" />Mock examination</span>{paper.duration_minutes && <span className="flex items-center gap-1.5 text-xs text-muted"><Clock3 size={13} aria-hidden="true" />{paper.duration_minutes} minutes</span>}</div>
    <p className="text-sm font-medium text-heading">{paper.question_count} questions{showsAssessmentMarks(assessment) ? ` · ${paper.total_marks} marks` : ''}</p>
    {!printMode && <PrintPaperButton assessment={assessment} />}
    <p className="text-xs leading-5 text-muted">{paper.instructions}</p>
    <div className="grid gap-2 sm:grid-cols-3">{paper.sections.map((section, index) => <div key={`${index}-${section.title}`} className="rounded-md border border-border px-2.5 py-2"><p className="text-xs font-medium text-heading">{section.title}</p><p className="mt-1 text-[11px] text-muted">{section.question_count} questions{showsAssessmentMarks(assessment) && <> · {section.questions?.length ? section.questions.reduce((sum,q) => sum + q.parts.reduce((value,p) => value+p.marks,0),0) : section.question_count * section.part_marks.reduce((sum, mark) => sum + mark, 0)} marks</>}</p></div>)}</div>
  </header>;
}

export function AssessmentPaper({ assessment, printMode = false }: { assessment: Assessment; printMode?: boolean }) {
  return <div aria-label={assessment.paper ? 'Exam paper' : 'Assessment questions'} className="space-y-4">
    <PracticeNotice assessment={assessment} />
    <PaperHeader assessment={assessment} printMode={printMode} />
    {assessment.questions.map((question, index) => <section key={question.id} className="space-y-2">
      {question.section && question.section !== assessment.questions[index - 1]?.section && <h3 className="border-b border-border pb-2 pt-2 text-sm font-semibold text-heading">{question.section}</h3>}
      {!!question.context && (question.number !== assessment.questions[index-1]?.number || question.context !== assessment.questions[index-1]?.context) && <div className="rounded-lg border border-border bg-surface p-3"><MarkdownContent content={question.context} /></div>}
      <div className="flex items-center justify-between gap-3 text-xs"><h4 className="font-medium text-heading">{questionLabel(question, index)}</h4>{showsAssessmentMarks(assessment) && <span className="shrink-0 tabular-nums text-muted">[{question.marks} {question.marks === 1 ? 'mark' : 'marks'}]</span>}</div>
      <MarkdownContent content={question.prompt} />
      {!!question.options?.length && <ol className="grid gap-1 text-sm text-muted sm:grid-cols-2">{question.options.map((option, i) => <li key={option.id} className="flex gap-2"><span className="font-medium">{String.fromCharCode(65 + i)}.</span><MarkdownContent content={option.label} /></li>)}</ol>}
    </section>)}
  </div>;
}
