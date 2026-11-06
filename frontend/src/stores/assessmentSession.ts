import { invalidatePageCache } from '../services/pageCache';
import { useSyncExternalStore } from 'react';
import { assessments } from '../services/assessments';
import type { Assessment,AssessmentAttempt } from '../types/assessments';

export interface QuizDraft {
  paper:Assessment;
  signature: string; answers: Record<string, string>; index: number;
  assistance: 'unknown' | 'independent' | 'assisted'; operation: string;
  attempt: AssessmentAttempt | null;
}
const evaluating = (attempt: AssessmentAttempt) => ['submitted', 'grading'].includes(attempt.state) || attempt.state === 'failed' && !!attempt.retry_pending;
const needsRefresh = (attempt: AssessmentAttempt) => attempt.source_pending || evaluating(attempt) || attempt.state === 'graded' && attempt.evidence_status === 'pending';

class AssessmentSession {
  private owner: string | null = null;
  private drafts = new Map<string, QuizDraft>();
  private draftTimers=new Map<string,ReturnType<typeof setTimeout>>();
  private cacheKey(owner:string,key:string){return `mentra:assessment-draft:${owner}:${key}`;}
  private attempts = new Map<string, AssessmentAttempt>();
  private submitting = new Set<string>();
  private timers = new Map<string, ReturnType<typeof setTimeout>>();
  private controller = new AbortController();
  private listeners = new Set<() => void>();
  private storageUnavailable=false;
  private status = { evaluating: 0, submitting: 0, draftStorageUnavailable:false };
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
  snapshot = () => this.status;
  attempt = (id: string) => this.attempts.get(id);
  latest(assessment: string) {
    return [...this.attempts.values()].filter(value => value.assessment_id === assessment && (value.source_pending || value.source_error || value.state !== 'draft' || Object.keys(value.answers).length > 0)).sort((a,b) => b.attempt_number - a.attempt_number)[0];
  }
  private publish() {
    const next = { evaluating: [...this.attempts.values()].filter(evaluating).length, submitting: this.submitting.size,draftStorageUnavailable:this.storageUnavailable };
    if (next.evaluating !== this.status.evaluating || next.submitting !== this.status.submitting || next.draftStorageUnavailable!==this.status.draftStorageUnavailable) this.status = next;
    this.listeners.forEach(fn => fn());
  }
  private accept(attempt: AssessmentAttempt) {
    const previous = this.attempts.get(attempt.id);
    if (previous && (previous.revision > attempt.revision || previous.revision === attempt.revision && previous.state === 'graded' && attempt.state !== 'graded')) return;
    if (previous === attempt) return;
    if (previous && (previous.state !== attempt.state || previous.grade_revision !== attempt.grade_revision || previous.evidence_status !== attempt.evidence_status)) {
      invalidatePageCache(['assessments', 'learning'], true);
    }
    this.attempts.set(attempt.id, attempt); this.publish();
  }
  setOwner(owner: string | null) {
    if (owner === this.owner) {
      for (const attempt of this.attempts.values()) if (needsRefresh(attempt)) this.poll(attempt.id);
      return;
    }
    this.controller.abort(); this.controller = new AbortController();
    this.timers.forEach(clearTimeout); this.timers.clear();
    this.draftTimers.forEach(clearTimeout);this.draftTimers.clear();
    if(this.owner){try{const prefix=this.cacheKey(this.owner,'');for(const key of Object.keys(sessionStorage))if(key.startsWith(prefix))sessionStorage.removeItem(key);}catch{/* Browser storage can be unavailable. */}}
    try{for(const key of Object.keys(sessionStorage))if(key.startsWith('mentra:assessment-draft:')&&(!owner||!key.startsWith(this.cacheKey(owner,''))))sessionStorage.removeItem(key);}catch{/* No cross-owner cache is read. */}
    this.drafts.clear(); this.attempts.clear(); this.submitting.clear(); this.owner = owner;this.storageUnavailable=false; this.publish();
  }
  draft(owner: string | undefined, key: string) {
    if(!owner||owner!==this.owner)return undefined;
    if(!this.drafts.has(key)){try{const text=sessionStorage.getItem(this.cacheKey(owner,key));if(text){const value=JSON.parse(text) as QuizDraft;if(value.paper?.id&&value.signature&&value.answers&&value.operation)this.drafts.set(key,value);}}catch{/* Keep an invalid cache out of the current contract. */}}
    return this.drafts.get(key);
  }
  remember(owner: string | undefined, key: string, draft: QuizDraft) {
    if(!owner||owner!==this.owner)return;
    this.drafts.set(key,draft);
    const timer=this.draftTimers.get(key);if(timer)clearTimeout(timer);
    // Paint/input stay local. Browser-session durability is saved after input,
    // with a pagehide flush; no question-navigation request reaches the server.
    this.draftTimers.set(key,setTimeout(()=>{this.draftTimers.delete(key);this.persistDraft(owner,key);},250));
  }
  persistDraft(owner:string,key:string){
    if(owner!==this.owner)return;
    try{const value=this.drafts.get(key);if(value)sessionStorage.setItem(this.cacheKey(owner,key),JSON.stringify(value));}catch{this.storageUnavailable=true;this.publish();}
  }
  flushDrafts(){if(this.owner)for(const key of this.drafts.keys())this.persistDraft(this.owner,key);}
  archiveDraft(owner:string|undefined,key:string){
    if(!owner||owner!==this.owner)return;
    const value=this.draft(owner,key);if(!value)return;
    const archived=`${value.paper.id}:recovery:${Date.now()}:${crypto.randomUUID()}`;
    this.drafts.set(archived,value);this.persistDraft(owner,archived);this.forget(owner,key);
    window.dispatchEvent(new CustomEvent('mentra:assessment-recovery',{detail:value.paper.id}));
  }
  recoveryKeys(owner:string|undefined,assessment:string){
    if(!owner||owner!==this.owner)return [];
    const prefix=`${assessment}:recovery:`;const keys=new Set([...this.drafts.keys()].filter(key=>key.startsWith(prefix)));
    try{const storedPrefix=this.cacheKey(owner,prefix);for(const key of Object.keys(sessionStorage))if(key.startsWith(storedPrefix))keys.add(key.slice(this.cacheKey(owner,'').length));}catch{/* In-memory recovery remains available. */}
    return [...keys].sort();
  }
  forget(owner: string | undefined, key: string) { if (owner&&owner === this.owner){this.drafts.delete(key);const timer=this.draftTimers.get(key);if(timer)clearTimeout(timer);this.draftTimers.delete(key);try{sessionStorage.removeItem(this.cacheKey(owner,key));}catch{/* Nothing to restore. */}} }
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
window.addEventListener('pagehide',()=>assessmentSession.flushDrafts());
export const useAssessmentEvaluation = () => useSyncExternalStore(assessmentSession.subscribe, assessmentSession.snapshot);
export const useEvaluatedAttempt = (id: string) => useSyncExternalStore(assessmentSession.subscribe, () => assessmentSession.attempt(id));

export const useLatestAssessmentAttempt = (id: string) => useSyncExternalStore(assessmentSession.subscribe, () => assessmentSession.latest(id));
