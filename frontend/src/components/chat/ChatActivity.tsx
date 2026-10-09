import { useEffect, useState } from 'react';
import { apiEvents } from '../../services/api';
import { chatStore } from '../../stores/chatStore';
import { ThinkingIndicator } from './ChatMessage';

interface Activity {
  schema_version: 1; conversation_id: string; turn_id: string; attempt: number;
  sequence: number; step_id: string; user_message: string; tool_name: string | null;
  status: 'planned' | 'running' | 'completed' | 'failed' | 'waiting';
  token_delta?: string | null; token_reset?: boolean;
}

function valid(value: unknown): value is Activity {
  if (!value || typeof value !== 'object') return false;
  const v = value as Partial<Activity>;
  return v.schema_version === 1 && Number.isInteger(v.sequence) && typeof v.user_message === 'string'
    && v.user_message.length <= 240 && typeof v.step_id === 'string' && typeof v.attempt === 'number'
    && (v.tool_name === null || typeof v.tool_name === 'string')
    && (v.token_delta === undefined || v.token_delta === null || typeof v.token_delta === 'string' && v.token_delta.length <= 2000);
}

export function ChatActivity({ conversationId, turnId, attempt }: { conversationId: string; turnId?: string; attempt?: number }) {
  const [steps, setSteps] = useState<Activity[]>([]);
  const [preview, setPreview] = useState('');
  useEffect(() => {
    setSteps([]);
    setPreview('');
    if (!turnId || !attempt) return;
    const controller = new AbortController();
    let cursor = 0, timer: ReturnType<typeof setTimeout> | undefined, terminal = false;
    async function connect() {
      try {
        await apiEvents(`/api/v1/conversations/${conversationId}/turns/${turnId}/events?attempt=${attempt}&after=${cursor}`, controller.signal, (name, data) => {
          if (controller.signal.aborted) return;
          if (name === 'terminal' || name === 'unavailable') {
            terminal = true; void chatStore.open(conversationId, true); return;
          }
          if (name === 'reset') { terminal = true; void chatStore.open(conversationId, true); return; }
          if (name !== 'activity' || !valid(data) || data.conversation_id !== conversationId
              || data.turn_id !== turnId || data.attempt !== attempt || data.sequence <= cursor) return;
          cursor = data.sequence;
          if (data.token_reset) setPreview('');
          else if (data.token_delta) setPreview(previous => (previous + data.token_delta).slice(0, 60_000));
          setSteps(previous => [...previous.filter(step => step.step_id !== data.step_id), data].slice(-16));
        });
      } catch { /* Existing canonical status polling remains available during connection failures. */ }
      if (!controller.signal.aborted && !terminal) timer = setTimeout(() => void connect(), 2000);
    }
    void connect();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [conversationId, turnId, attempt]);
  const current = steps[steps.length - 1];
  return <div>
    <ThinkingIndicator label={current?.user_message ?? 'Planning your request'} />
    {preview && <p aria-label="Response in progress" aria-busy="true" className="ml-11 mt-3 whitespace-pre-wrap text-sm text-body">{preview}</p>}
    {!!steps.length && <details className="ml-11 mt-2 text-xs text-muted">
      <summary className="cursor-pointer">Activity{current?.tool_name ? ` · ${current.tool_name}` : ''}</summary>
      <ol className="mt-2 space-y-1">{steps.map(step => <li key={step.step_id}>
        {step.user_message}{step.tool_name && <span className="text-subtle"> · {step.tool_name}</span>}
        <span className="text-subtle"> — {step.status}</span>
      </li>)}</ol>
    </details>}
  </div>;
}
