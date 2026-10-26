import { lazy, Suspense, useEffect, useState } from 'react';
import type { AssessmentReference } from './AssessmentPreview';
import { Skeleton } from '../ui/Skeleton';
const AssessmentPreview = lazy(() => import('./AssessmentPreview').then(module => ({ default: module.AssessmentPreview })));
import { apiEvents } from '../../services/api';
import { chatStore } from '../../stores/chatStore';
import { ThinkingIndicator } from './ChatMessage';
import { WebsiteIcon, safeWebsite } from '../webSearch/WebsiteIcon';
import type { WebsiteIdentity } from '../../types/webSearch';
import { useActivityFeedback } from './useActivityFeedback';
import { activityLabel } from './activityLabels';

interface Activity {
  schema_version: 1; conversation_id: string; turn_id: string; attempt: number;
  sequence: number; step_id: string; user_message: string; tool_name: string | null;
  status: 'planned' | 'running' | 'completed' | 'failed' | 'waiting' | 'retry_wait' | 'degraded' | 'cancelled';
  token_delta?: string | null; token_reset?: boolean;
  tool_attempt?: number | null; max_attempts?: number | null; error_code?: string | null;
  websites?: WebsiteIdentity[];
  assessment_card?: AssessmentReference | null;
}

function valid(value: unknown): value is Activity {
  if (!value || typeof value !== 'object') return false;
  const v = value as Partial<Activity>;
  return v.schema_version === 1 && Number.isInteger(v.sequence) && (v.sequence ?? 0) > 0 && typeof v.user_message === 'string'
    && v.user_message.length <= 240 && typeof v.step_id === 'string' && typeof v.attempt === 'number'
    && (v.tool_name === null || typeof v.tool_name === 'string')
    && ['planned', 'running', 'completed', 'failed', 'waiting', 'retry_wait', 'degraded', 'cancelled'].includes(v.status ?? '')
    && (v.tool_attempt == null || Number.isInteger(v.tool_attempt) && v.tool_attempt >= 1 && v.tool_attempt <= 3)
    && (v.max_attempts == null || Number.isInteger(v.max_attempts) && v.max_attempts >= 1 && v.max_attempts <= 3)
    && (v.error_code == null || typeof v.error_code === 'string' && v.error_code.length <= 100)
    && (v.websites == null || Array.isArray(v.websites) && v.websites.length <= 5 && v.websites.every(site =>
      site && typeof site.domain === 'string' && typeof site.favicon_url === 'string' && safeWebsite(site)))
    && (v.token_delta === undefined || v.token_delta === null || typeof v.token_delta === 'string' && v.token_delta.length <= 2000)
    && (!v.assessment_card || ['draft', 'saved', 'generation'].includes(v.assessment_card.kind)
      && typeof v.assessment_card.id === 'string' && v.assessment_card.id.length <= 100
      && typeof v.assessment_card.title === 'string' && v.assessment_card.title.length <= 200);
}

export function ChatActivity({ conversationId, turnId, attempt, stopping = false }: { conversationId: string; turnId?: string; attempt?: number; stopping?: boolean }) {
  const [current, setCurrent] = useState<Activity>();
  const [assessment, setAssessment] = useState<AssessmentReference>();
  const label = useActivityFeedback(current, !!turnId);
  useEffect(() => {
    setCurrent(undefined);
    setAssessment(undefined);
    if (!turnId || !attempt) return;
    const controller = new AbortController();
    let cursor = 0, timer: ReturnType<typeof setTimeout> | undefined, terminal = false;
    async function connect() {
      try {
        await apiEvents(`/api/v1/conversations/${conversationId}/turns/${turnId}/events?attempt=${attempt}&after=${cursor}`, controller.signal, (name, data) => {
          if (controller.signal.aborted) return;
          if (name === 'terminal') {
            terminal = true; void chatStore.receiveTerminal(conversationId, turnId!, attempt!, data); return;
          }
          if (name === 'unavailable') {
            terminal = true; void chatStore.open(conversationId, false, true); return;
          }
          if (name === 'reset') { terminal = true; void chatStore.open(conversationId, false, true); return; }
          if (name !== 'activity' || !valid(data) || data.conversation_id !== conversationId
              || data.turn_id !== turnId || data.attempt !== attempt || data.sequence <= cursor) return;
          cursor = data.sequence;
          if (data.assessment_card) setAssessment(data.assessment_card);
          // Keep activity live; publish answer content only after the canonical
          // message and its interactive cards are ready to reveal together.
          if (activityLabel(data) === null) return;
          setCurrent(previous => {
            const websites = data.websites?.length ? data.websites
              : data.status === 'completed' && data.tool_name === 'web_search' && previous?.tool_name === 'web_search' ? previous.websites : [];
            if (previous && previous.status === data.status && activityLabel(previous) === activityLabel(data)
              && JSON.stringify(previous.websites ?? []) === JSON.stringify(websites ?? [])) return previous;
            // Token deltas advance the recovery cursor, but never enter UI state.
            const { token_delta: _delta, token_reset: _reset, ...feedback } = data;
            return { ...feedback, websites };
          });
        });
      } catch { /* Existing canonical status polling remains available during connection failures. */ }
      if (!controller.signal.aborted && !terminal) timer = setTimeout(() => void connect(), 2000);
    }
    void connect();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [conversationId, turnId, attempt]);
  const sites = (step: Activity) => !!step.websites?.length && <span className="mt-1 flex flex-wrap gap-2">{step.websites.map(site =>
    <span key={site.domain} className="inline-flex min-w-0 items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-muted">
      <WebsiteIcon website={site} /><span className="break-all">{site.domain}</span>
    </span>)}</span>;
  return <div aria-label="Current activity">
    <ThinkingIndicator label={stopping ? 'Stopping this response' : label} />
    {current && <div className="sm:ml-11">{sites(current)}</div>}
    {assessment && !stopping && <div className="sm:ml-11"><Suspense fallback={<Skeleton variant="card" />}><AssessmentPreview key={`${assessment.kind}:${assessment.id}`} reference={assessment} conversationId={conversationId} /></Suspense></div>}
  </div>;
}
