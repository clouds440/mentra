import { MarkdownContent } from '../content/MarkdownContent';

/** Shared, bounded rich preview for saved results, chat results and mistakes. */
export function QuestionCardPreview({ content, secondary = false }: { content: string; secondary?: boolean }) {
  return <div className={`question-card-preview min-w-0 overflow-hidden break-words ${secondary ? 'h-8 text-xs leading-4 text-muted' : 'h-10 text-sm font-medium leading-5 text-heading'}`}>
    <MarkdownContent content={content} preview />
  </div>;
}
