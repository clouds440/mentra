import { useCallback, useSyncExternalStore } from 'react';
import { assessments } from '../services/assessments';
import { ApiError } from '../services/api';
import { invalidatePageCache } from '../services/pageCache';
import type { GenerationJob } from '../types/assessments';

interface Snapshot { job?: GenerationJob; error: string; unavailable: boolean; receivedAt?: number }
interface Entry { value: Snapshot; listeners: Set<() => void>; controller?: AbortController; timer?: ReturnType<typeof setTimeout>; release?: ReturnType<typeof setTimeout> }
const empty: Snapshot = { error: '', unavailable: false };
const terminal = (job: GenerationJob) => ['completed', 'failed', 'stopped'].includes(job.state);

/** One owner-scoped observation per job, shared by activity previews and chat. */
class AssessmentGeneration {
  private owner: string | null = null;
  private entries = new Map<string, Entry>();
  private listening = false;
  setOwner(owner: string | null) {
    if (this.owner === owner) return;
    this.entries.forEach(entry => { entry.controller?.abort(); clearTimeout(entry.timer); clearTimeout(entry.release); });
    const previous = [...this.entries.values()]; this.entries.clear(); this.owner = owner;
    previous.forEach(entry => entry.listeners.forEach(listener => listener()));
  }
  private entry(id: string) {
    let entry = this.entries.get(id);
    if (!entry) {
      for (const [key, value] of this.entries) {
        if (this.entries.size < 64) break;
        if (!value.listeners.size && !value.controller) this.entries.delete(key);
      }
      entry = { value: empty, listeners: new Set() }; this.entries.set(id, entry);
    }
    return entry;
  }
  snapshot = (id: string) => this.owner ? this.entry(id).value : empty;
  subscribe = (id: string, listener: () => void) => {
    const entry = this.entry(id); clearTimeout(entry.release); entry.listeners.add(listener);
    if (!this.listening) {
      this.listening = true;
      window.addEventListener('focus', this.refreshVisible);
      document.addEventListener('visibilitychange', this.refreshVisible);
      window.addEventListener('mentra:assessment-generation', this.changed);
    }
    if (!entry.value.job || !terminal(entry.value.job)) void this.read(id);
    return () => {
      entry.listeners.delete(listener);
      // A StrictMode remount or another subscriber reuses the in-flight read.
      entry.release = setTimeout(() => {
        if (entry.listeners.size) return;
        entry.controller?.abort(); entry.controller = undefined; clearTimeout(entry.timer);
      }, 0);
    };
  };
  private changed = (event: Event) => {
    const id = (event as CustomEvent<{ jobId?: string }>).detail?.jobId;
    if (id && this.entries.get(id)?.listeners.size) void this.read(id);
  };
  private refreshVisible = () => {
    if (document.hidden) { this.entries.forEach(entry => clearTimeout(entry.timer)); return; }
    this.entries.forEach((entry, id) => {
      if (entry.listeners.size && !entry.value.unavailable) void this.read(id);
    });
  };
  accept(id: string, job: GenerationJob) {
    if (!this.owner || id !== job.id) return;
    const entry = this.entry(id), previous = entry.value.job;
    if (previous && ((previous.revision ?? 1) > (job.revision ?? 1)
      || previous.state === 'completed' && (previous.revision ?? 1) === (job.revision ?? 1) && job.state !== 'completed')) return;
    entry.value = { job, error: '', unavailable: false, receivedAt: performance.now() };
    entry.listeners.forEach(listener => listener());
    if (previous?.state !== job.state) {
      if (job.state === 'completed') invalidatePageCache(['assessments'], true);
      window.dispatchEvent(new CustomEvent('mentra:assessment-generation', { detail: { conversationId: job.conversation_id } }));
    }
  }
  refresh(id: string) { void this.read(id); }
  private async read(id: string) {
    const entry = this.entry(id);
    if (!this.owner || entry.controller || !entry.listeners.size || document.hidden) return;
    clearTimeout(entry.timer);
    const owner = this.owner, controller = new AbortController(); entry.controller = controller;
    try {
      const job = await assessments.job(id, controller.signal);
      if (controller.signal.aborted || this.owner !== owner || this.entries.get(id) !== entry) return;
      this.accept(id, job);
    } catch (error) {
      if (controller.signal.aborted || this.owner !== owner) return;
      const unavailable = error instanceof ApiError && [403, 404].includes(error.status);
      entry.value = { ...entry.value, unavailable, error: unavailable ? 'This assessment is no longer available.' : 'Progress could not be refreshed. Trying again shortly.' };
      entry.listeners.forEach(listener => listener());
    } finally {
      if (entry.controller === controller) entry.controller = undefined;
      if (!controller.signal.aborted && entry.listeners.size && this.owner === owner && !entry.value.unavailable && !document.hidden) {
        const job = entry.value.job;
        if (!job || !terminal(job)) entry.timer = setTimeout(() => void this.read(id), 1500);
        else if (job.state === 'stopped' && job.can_resume && job.resume_until) {
          entry.timer = setTimeout(() => void this.read(id), Math.min(30_000, Math.max(500, Date.parse(job.resume_until) - Date.now() + 100)));
        }
      }
    }
  }
}
export const assessmentGeneration = new AssessmentGeneration();
export const useAssessmentGeneration = (id: string) => useSyncExternalStore(
  useCallback(listener => assessmentGeneration.subscribe(id, listener), [id]),
  useCallback(() => assessmentGeneration.snapshot(id), [id]));
