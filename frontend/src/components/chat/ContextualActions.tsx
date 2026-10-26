import { useState } from 'react';
import { ClipboardCheck, X } from 'lucide-react';
import { Button, IconButton } from '../ui';
import type { ChatMessageData } from '../../types/chat';
import { chatStore, useConversation } from '../../stores/chatStore';

type ContextAction = { kind: 'practice_sources'; documentIds: string[] };

function actionFor(message: ChatMessageData): ContextAction | null {
  if (message.assessment_cards?.length || message.interactions?.length) return null;
  const sources = message.sources?.filter(source => !source.include_archived && message.citations?.includes(source.token)) ?? [];
  const documentIds = [...new Set(sources.map(source => source.document_id))];
  return documentIds.length ? { kind: 'practice_sources', documentIds } : null;
}

/** One optional action from current validated references, with no extra reads/model. */
export function ContextualActions({ message, conversationId }: { message: ChatMessageData; conversationId: string }) {
  const view = useConversation(conversationId);
  const [dismissed, setDismissed] = useState(false);
  const [started, setStarted] = useState(false);
  const action = actionFor(message);
  if (!action || dismissed || started || view.busy) return null;
  async function invoke() {
    if (!action || view.busy) return;
    setStarted(true);
    await chatStore.send(conversationId, 'Give me a short quiz grounded only in the selected study material.',
      { mode: 'SOURCE_SPECIFIC', document_ids: action.documentIds, context_ids: [] });
  }
  return <div className="mt-3 flex items-center gap-1" aria-label="Suggested next step">
    <Button variant="secondary" size="sm" onClick={() => void invoke()}><ClipboardCheck size={14} aria-hidden="true" />Practice this material</Button>
    <IconButton aria-label="Dismiss suggestion" title="Dismiss suggestion" onClick={() => setDismissed(true)}><X size={14} aria-hidden="true" /></IconButton>
  </div>;
}
