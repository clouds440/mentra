import { useEffect, useState } from 'react';
import type { ChoiceCardData } from '../../types/interactions';
import { chatStore, useConversation } from '../../stores/chatStore';
import { ChoiceOptions } from '../interactions/ChoiceOptions';
import { Button } from '../ui';

export function ChoiceCard({ card, messageId, conversationId }: { card: ChoiceCardData; messageId: string; conversationId: string }) {
  const view = useConversation(conversationId);
  const stored = view.messages.find(message => message.id === messageId)?.interactions?.find(item => item.id === card.id) ?? card;
  const [selected, setSelected] = useState(stored.selected);
  useEffect(() => setSelected(stored.selected), [stored.selected]);
  const done = !!stored.submitted_turn_id;
  async function submit() {
    const options = stored.options.filter(option => selected.includes(option.id));
    const content = `${stored.question}\nSelected: ${options.map(option => `${option.id}: ${option.label}`).join('; ')}`;
    await chatStore.send(conversationId, content, chatStore.conversation(conversationId)?.selection ?? { mode: 'STANDARD', context_ids: [], document_ids: [] }, false, [],
      { message_id: messageId, interaction_id: stored.id, selected });
  }
  return <section className="my-4 space-y-3 rounded-xl border border-border p-4" aria-label="Interactive question">
    <ChoiceOptions kind={stored.kind} question={stored.question} options={stored.options}
      selected={done ? stored.selected : selected} disabled={done || view.busy} onChange={setSelected} />
    {done ? <p role="status" className="text-sm text-muted">Selection submitted.</p> : <Button disabled={view.busy || !selected.length} onClick={() => void submit()}>{view.busy ? 'Sending…' : 'Submit selection'}</Button>}
    {view.error && <p role="alert" className="text-sm text-danger">{view.error}</p>}
  </section>;
}
