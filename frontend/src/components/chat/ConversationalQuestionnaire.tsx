import { useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import type { InputFieldDefinition, InteractionCardData, InteractionDraft, InteractionSubmission, QuestionAnswer } from '../../types/interactions';
import { isChoice } from '../../types/interactions';
import { chatStore, useConversationField, usePendingInteraction } from '../../stores/chatStore';
import { ChoiceOptions } from '../interactions/ChoiceOptions';
import { fieldError, InteractionField } from '../interactions/InteractionField';
import { QuestionProgress } from '../assessments/QuestionProgress';
import { useQuestionNavigation } from '../assessments/useQuestionNavigation';
import { Button } from '../ui';

type InputCard = Exclude<InteractionCardData, { kind: 'value_bars' }>;
interface Entry {
  key: string; source: InputCard; child?: string; question: string;
  options?: Extract<InteractionCardData, { kind: 'single_choice' | 'multiple_choice' }>['options'];
  multiple: boolean; fields: InputFieldDefinition[]; initial: QuestionAnswer;
}
const draft = (value: QuestionAnswer): InteractionDraft => ({ selected: value.selected ?? [], optionInputs: value.option_inputs ?? {}, values: value.values ?? {} });
function entries(cards: InputCard[]): Entry[] {
  return cards.flatMap<Entry>(card => card.kind === 'questionnaire' ? card.questions.map(q => ({
    key: `${card.id}:${q.id}`, source: card, child: q.id, question: q.question, initial: card.answers?.[q.id] ?? {},
    multiple: q.kind === 'multiple_choice', options: 'options' in q ? q.options : undefined,
    fields: 'options' in q ? [] : [{ id: 'answer', label: 'Your answer', kind: q.kind, required: q.required, max_length: q.max_length }],
  })) : [{ key: card.id, source: card, question: card.question, initial: isChoice(card) ? { selected: card.selected, option_inputs: card.option_inputs } : { values: card.values },
    multiple: card.kind === 'multiple_choice', options: isChoice(card) ? card.options : undefined, fields: isChoice(card) ? [] : card.fields }]);
}
function fieldsFor(entry: Entry, value: InteractionDraft): InputFieldDefinition[] {
  return entry.options ? entry.options.filter(option => value.selected.includes(option.id) && option.input).map(option => ({ id: option.id, ...option.input! })) : entry.fields;
}
function valid(entry: Entry, value: InteractionDraft) {
  return (!entry.options || (value.selected.length > 0 && (entry.multiple || value.selected.length === 1) && value.selected.every(id => entry.options!.some(option => option.id === id))))
    && fieldsFor(entry, value).every(field => !fieldError(field, (entry.options ? value.optionInputs : value.values)[field.id] ?? ''));
}

/** All answers use one durable chat transaction; no assessment/attempt is started. */
export function ConversationalQuestionnaire({ cards, messageId, conversationId }: { cards: InputCard[]; messageId: string; conversationId: string }) {
  const questions = entries(cards);
  const done = cards.every(card => !!card.submitted_turn_id);
  const busy = useConversationField(done ? '' : conversationId, 'busy');
  const error = useConversationField(done ? '' : conversationId, 'error');
  const pending = usePendingInteraction(done ? '' : conversationId);
  const uncertain = !busy && pending?.message_id === messageId;
  const blocked = busy || uncertain;
  const keyFor = (entry: Entry) => `${conversationId}:${messageId}:${entry.key}`;
  const [drafts, setDrafts] = useState<Record<string, InteractionDraft>>(() => Object.fromEntries(questions.map(q => [q.key, chatStore.interactionDraft(keyFor(q)) ?? draft(q.initial)])));
  const { index, setIndex, direction } = useQuestionNavigation(() => Math.max(0, questions.findIndex(q => !q.source.submitted_turn_id)));
  const activeIndex = Math.min(index, questions.length - 1);
  const current = questions[activeIndex];
  const submissions = pending?.message_id === messageId ? [pending, ...(pending.additional_responses ?? [])] : [];
  function valueFor(entry: Entry) {
    if (entry.source.submitted_turn_id) return draft(entry.initial);
    const recovery = submissions.find(item => item.interaction_id === entry.source.id);
    return recovery ? draft(entry.child ? recovery.answers?.[entry.child] ?? {} : recovery) : drafts[entry.key] ?? draft(entry.initial);
  }
  const currentValue = valueFor(current);
  const currentDone = !!current.source.submitted_turn_id;
  const fields = fieldsFor(current, currentValue);
  const answered = questions.map(q => !!q.source.submitted_turn_id || valid(q, valueFor(q)));
  const allAnswered = answered.every(Boolean);
  useEffect(() => { for (const entry of questions) if (entry.source.submitted_turn_id) chatStore.saveInteractionDraft(keyFor(entry), null); });
  function update(next: InteractionDraft) {
    setDrafts(previous => ({ ...previous, [current.key]: next }));
    chatStore.saveInteractionDraft(keyFor(current), next);
  }
  async function submit() {
    if (busy || done) return;
    if (uncertain) { await chatStore.send(conversationId, '', chatStore.conversation(conversationId)?.selection ?? { mode: 'STANDARD' }, true); return; }
    if (!allAnswered) { setIndex(answered.indexOf(false)); return; }
    const answers = new Map<string, InteractionSubmission>();
    for (const entry of questions.filter(q => !q.source.submitted_turn_id)) {
      const value = valueFor(entry);
      const active = Object.fromEntries(fieldsFor(entry, value).map(field => [field.id, (entry.options ? value.optionInputs : value.values)[field.id] ?? '']));
      const answer: QuestionAnswer = entry.options ? { selected: value.selected, option_inputs: active } : { values: active };
      if (entry.child) {
        const parent = answers.get(entry.source.id) ?? { interaction_id: entry.source.id, answers: {} };
        parent.answers![entry.child] = answer; answers.set(entry.source.id, parent);
      } else answers.set(entry.source.id, { interaction_id: entry.source.id, ...answer });
    }
    const [first, ...additional] = [...answers.values()];
    if (!first) return;
    await chatStore.send(conversationId, 'My answers to these questions.', chatStore.conversation(conversationId)?.selection ?? { mode: 'STANDARD' }, false, [],
      { ...first, message_id: messageId, ...(additional.length ? { additional_responses: additional } : {}) });
  }
  return <section aria-label="Conversation questions" className="chat-interaction my-4 space-y-4 rounded-panel border border-border p-4">
    <h3 className="font-medium text-heading">{cards.length === 1 ? cards[0].question : 'A few questions for you'}</h3>
    <QuestionProgress answered={answered} index={activeIndex} disabled={blocked} onNavigate={setIndex} label="Conversation" />
    <div key={current.key} data-navigation={direction} className="question-transition space-y-3 rounded-lg border border-border-strong bg-surface p-3 sm:p-4">
      {current.options ? <ChoiceOptions kind={current.multiple ? 'multiple_choice' : 'single_choice'} question={current.question} options={current.options} selected={currentValue.selected} disabled={blocked || currentDone}
        onChange={selected => update({ ...currentValue, selected })} renderAfter={option => {
          const field = fields.find(item => item.id === option.id);
          return field ? <div className="mt-2 pl-6"><InteractionField field={field} value={currentValue.optionInputs[field.id] ?? ''} disabled={blocked || currentDone} onChange={value => update({ ...currentValue, optionInputs: { ...currentValue.optionInputs, [field.id]: value } })} /></div> : null;
        }} /> : <><p className="font-medium text-heading">{current.question}</p>{fields.map(field => <InteractionField key={field.id} field={field} value={currentValue.values[field.id] ?? ''} disabled={blocked || currentDone} onChange={value => update({ ...currentValue, values: { ...currentValue.values, [field.id]: value } })} />)}</>}
    </div>
    {done ? <p role="status" className="text-sm text-muted">All answers submitted.</p> : <p className="text-xs text-muted">{uncertain ? 'Submission is unconfirmed. Retry sends the same complete answer.' : 'Your answers stay here until you submit them together.'}</p>}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    <div className="flex flex-wrap gap-2">
      <Button size="sm" variant="secondary" disabled={blocked || activeIndex === 0} onClick={() => setIndex(activeIndex - 1)}><ArrowLeft size={13} aria-hidden="true" />Back</Button>
      {activeIndex < questions.length - 1 && <Button size="sm" variant="secondary" disabled={blocked} onClick={() => setIndex(activeIndex + 1)}>Next<ArrowRight size={13} aria-hidden="true" /></Button>}
      {!done && <Button size="sm" disabled={busy || (!uncertain && !allAnswered)} loading={busy} onClick={() => void submit()}>{uncertain ? 'Retry all answers' : 'Submit all answers'}</Button>}
    </div>
  </section>;
}
