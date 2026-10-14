import { useSyncExternalStore } from 'react';
import { assessments } from '../services/assessments';
import type { AssessmentAttempt } from '../types/assessments';

export interface QuizDraft {
  signature: string; answers: Record<string, string>; index: number;
  assistance: 'unknown' | 'independent' | 'assisted'; operation: string;
  attempt: AssessmentAttempt | null;
}
const evaluating = (attempt: AssessmentAttempt) => ['submitted', 'grading'].includes(attempt.state) || attempt.state === 'failed' && !!attempt.retry_pending;
const needsRefresh = (attempt: AssessmentAttempt) => evaluating(attempt) || attempt.state === 'graded' && attempt.evidence_status === 'pending';

class AssessmentSession {
  private owner: string | null = null;
  private drafts = new Map<string, QuizDraft>();
  private attempts = new Map<string, AssessmentAttempt>();
  private submitting = new Set<string>();
  private timers = new Map<string, ReturnType<typeof setTimeout>>();
  private controller = new AbortController();
  private listeners = new Set<() => void>();
  private status = { evaluating: 0, submitting: 0 };
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
  snapshot = () => this.status;
  attempt = (id: string) => this.attempts.get(id);
  private publish() {
    const next = { evaluating: [...this.attempts.values()].filter(evaluating).length, submitting: this.submitting.size };
    if (next.evaluating !== this.status.evaluating || next.submitting !== this.status.submitting) this.status = next;
    this.listeners.forEach(fn => fn());
  }
  private accept(attempt: AssessmentAttempt) {
    const previous = this.attempts.get(attempt.id);
    if (previous && (previous.revision > attempt.revision || previous.revision === attempt.revision && previous.state === 'graded' && attempt.state !== 'graded')) return;
    if (previous === attempt) return;
    this.attempts.set(attempt.id, attempt); this.publish();
  }
  setOwner(owner: string | null) {
    if (owner === this.owner) {
      for (const attempt of this.attempts.values()) if (needsRefresh(attempt)) this.poll(attempt.id);
      return;
    }
    this.controller.abort(); this.controller = new AbortController();
    this.timers.forEach(clearTimeout); this.timers.clear();
    this.drafts.clear(); this.attempts.clear(); this.submitting.clear(); this.owner = owner; this.publish();
  }
  draft(owner: string | undefined, key: string) { return owner === this.owner ? this.drafts.get(key) : undefined; }
  remember(owner: string | undefined, key: string, draft: QuizDraft) { if (owner && owner === this.owner) this.drafts.set(key, draft); }
  forget(owner: string | undefined, key: string) { if (owner === this.owner) this.drafts.delete(key); }
  begin(owner: string | undefined, operation: string) { if (owner && owner === this.owner) { this.submitting.add(operation); this.publish(); } }
  end(owner: string | undefined, operation: string) { if (owner === this.owner) { this.submitting.delete(operation); this.publish(); } }
  observe(owner: string | undefined, attempt: AssessmentAttempt) {
    if (!owner || owner !== this.owner) return;
    this.accept(attempt);
    const current = this.attempts.get(attempt.id)!;
    if (needsRefresh(current)) this.poll(attempt.id);
    else { const timer = this.timers.get(attempt.id); if (timer) clearTimeout(timer); this.timers.delete(attempt.id); }
  }
  private poll(id: string, count = 0) {
    if (this.timers.has(id) || !this.owner) return;
    const signal = this.controller.signal;
    this.timers.set(id, setTimeout(async () => {
      // Retain the entry while fetching so mounting another card cannot start
      // a second poll. Polling survives navigation and never submits answers.
      try {
        const result = await assessments.attempt(id, signal);
        if (signal.aborted) return;
        this.accept(result);
      } catch { /* A temporary read failure leaves the known pending state visible. */ }
      if (signal.aborted) return;
      this.timers.delete(id);
      const latest = this.attempts.get(id);
      if (latest && needsRefresh(latest)) this.poll(id, count + 1);
    }, this.attempts.get(id)?.state === 'graded' ? 10000 : Math.min(1000 + count * 250, 5000)));
  }
}
export const assessmentSession = new AssessmentSession();
export const useAssessmentEvaluation = () => useSyncExternalStore(assessmentSession.subscribe, assessmentSession.snapshot);
export const useEvaluatedAttempt = (id: string) => useSyncExternalStore(assessmentSession.subscribe, () => assessmentSession.attempt(id));
