import { memo, useEffect, useState } from 'react';
import { isChoice, type InteractionCardData, type InteractionDraft } from '../../types/interactions';
import { chatStore, useConversationField, usePendingInteraction } from '../../stores/chatStore';
import { ChoiceOptions } from '../interactions/ChoiceOptions';
import { fieldError, InteractionField } from '../interactions/InteractionField';
import { ValueBars } from '../interactions/ValueBars';
import { Button } from '../ui';

/** Existing durable choice adapter also owns text/forms; static bars never submit. */
export const ChoiceCard = memo(function ChoiceCard({ card: stored, messageId, conversationId }: { card: InteractionCardData; messageId: string; conversationId: string }) {
  if (!['single_choice', 'multiple_choice', 'text_input', 'form', 'value_bars'].includes(stored.kind)) return <p className="my-4 text-sm text-muted">This interactive item is not supported by this version. You can reply in the chat instead.</p>;
  if (stored.kind === 'value_bars') return <section className="my-4 space-y-4 rounded-panel border border-border p-4" aria-label={stored.question}>
    <h3 className="font-medium text-heading">{stored.question}</h3>
    <ValueBars bars={stored.bars} />
  </section>;
  return <AnswerCard key={stored.id} stored={stored} messageId={messageId} conversationId={conversationId} />;
});
ChoiceCard.displayName = 'ChoiceCard';

function AnswerCard({ stored, messageId, conversationId }: { stored: Exclude<InteractionCardData, { kind: 'value_bars' }>; messageId: string; conversationId: string }) {
  const done = !!stored.submitted_turn_id;
  // Completed cards subscribe to no conversation updates. Active forms listen
  // only to the two fields they actually use, not every history/status update.
  const busy = useConversationField(done ? '' : conversationId, 'busy');
  const error = useConversationField(done ? '' : conversationId, 'error');
  const pending = usePendingInteraction(done ? '' : conversationId);
  const uncertain = !busy && pending?.interaction_id === stored.id;
  const disabled = done || busy || uncertain;
  const draftKey = `${conversationId}:${messageId}:${stored.id}`;
  const [draft, setDraft] = useState<InteractionDraft>(() => chatStore.interactionDraft(draftKey) ?? {
    selected: isChoice(stored) ? stored.selected : [], optionInputs: isChoice(stored) ? stored.option_inputs ?? {} : {}, values: !isChoice(stored) ? stored.values ?? {} : {},
  });
  const [focus, setFocus] = useState('');
  useEffect(() => { if (done) chatStore.saveInteractionDraft(draftKey, null); }, [done, draftKey]);
  function update(next: InteractionDraft) { setDraft(next); chatStore.saveInteractionDraft(draftKey, next); }
  const recovering = !done && pending?.interaction_id === stored.id;
  const selected = done && isChoice(stored) ? stored.selected : recovering ? pending.selected ?? [] : draft.selected;
  const values = done && !isChoice(stored) ? stored.values ?? {} : recovering ? pending.values ?? {} : draft.values;
  const optionInputs = done && isChoice(stored) ? stored.option_inputs ?? {} : recovering ? pending.option_inputs ?? {} : draft.optionInputs;
  const fields = isChoice(stored) ? stored.options.filter(option => selected.includes(option.id) && option.input).map(option => ({ id: option.id, ...option.input! })) : stored.fields;
  const answers = isChoice(stored) ? optionInputs : values;
  const valid = (!isChoice(stored) || selected.length > 0) && fields.every(field => !fieldError(field, answers[field.id] ?? ''));
  async function submit() {
    if (done || busy) return;
    if (uncertain) {
      await chatStore.send(conversationId, '', chatStore.conversation(conversationId)?.selection ?? { mode: 'STANDARD' }, true);
      return;
    }
    if (!valid) return;
    const active = Object.fromEntries(fields.map(field => [field.id, answers[field.id] ?? '']));
    const labels = isChoice(stored) ? stored.options.filter(option => selected.includes(option.id)).map(option => `${option.id}: ${option.label}${option.input ? ` — ${option.input.label}: ${active[option.id]}` : ''}`) : stored.fields.map(field => `${field.label}: ${field.kind === 'select' ? field.options?.find(option => option.id === active[field.id])?.label ?? '' : active[field.id]}`);
    const content = `${stored.question}\n${isChoice(stored) ? 'Selected: ' : ''}${labels.join(isChoice(stored) ? '; ' : '\n')}`;
    await chatStore.send(conversationId, content, chatStore.conversation(conversationId)?.selection ?? { mode: 'STANDARD', context_ids: [], document_ids: [] }, false, [],
      { message_id: messageId, interaction_id: stored.id, ...(isChoice(stored) ? { selected, option_inputs: active } : { values: active }) });
  }
  return <section className="chat-interaction my-4 space-y-3 rounded-panel border border-border p-4" aria-label={isChoice(stored) ? 'Interactive question' : 'Interactive form'}>
    <form className="space-y-3" onSubmit={event => { event.preventDefault(); void submit(); }}>
      {isChoice(stored) ? <ChoiceOptions kind={stored.kind} question={stored.question} options={stored.options} selected={selected} disabled={disabled}
        onChange={next => { setFocus(next.find(id => !selected.includes(id)) ?? ''); update({ ...draft, selected: next }); }}
        renderAfter={option => {
          const field = fields.find(item => item.id === option.id);
          return field ? <div className="mt-2 pl-6"><InteractionField field={field} value={optionInputs[field.id] ?? ''} disabled={disabled} autoFocus={focus === field.id} onChange={value => update({ ...draft, optionInputs: { ...draft.optionInputs, [field.id]: value } })} /></div> : null;
        }} /> : <><h3 className="font-medium text-heading">{stored.question}</h3>{fields.map(field => <InteractionField key={field.id} field={field} value={values[field.id] ?? ''} disabled={disabled} onChange={value => update({ ...draft, values: { ...draft.values, [field.id]: value } })} />)}</>}
      {uncertain && <p role="status" className="text-sm text-muted">Submission is unconfirmed. Retrying sends your original answer.</p>}
      {done ? <p role="status" className="text-sm text-muted">{isChoice(stored) ? 'Selection submitted.' : 'Answer submitted.'}</p> : <Button type="submit" disabled={busy || (!uncertain && !valid)} loading={busy}>{busy ? 'Sending…' : uncertain ? 'Retry original answer' : isChoice(stored) ? 'Submit selection' : 'Submit answer'}</Button>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    </form>
  </section>;
}
