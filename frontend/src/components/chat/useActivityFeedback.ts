import { useEffect, useRef, useState } from 'react';
import { activityLabel, type ActivityLabelInput } from './activityLabels';

/** Coalesce bursts without delaying answers or restarting the working logo. */
export function useActivityFeedback(activity: ActivityLabelInput | undefined, acknowledged: boolean) {
  const [label, setLabel] = useState(acknowledged ? 'Thinking' : 'Sending your message');
  const shown = useRef({ label, at: performance.now() });
  const desired = activityLabel(activity) ?? shown.current.label;
  const next = activity ? desired : acknowledged ? 'Thinking' : 'Sending your message';
  useEffect(() => {
    if (next === shown.current.label) return;
    const timer = setTimeout(() => {
      shown.current = { label: next, at: performance.now() }; setLabel(next);
    }, Math.max(0, 650 - (performance.now() - shown.current.at)));
    return () => clearTimeout(timer);
  }, [next]);
  useEffect(() => {
    // One honest long-wait message, never a carousel of invented work stages.
    if (activity && ['waiting', 'cancelled', 'failed', 'degraded', 'retry_wait'].includes(activity.status)) return;
    const timer = setTimeout(() => {
      const text = 'Still working on your request';
      shown.current = { label: text, at: performance.now() }; setLabel(text);
    }, 12_000);
    return () => clearTimeout(timer);
  }, [activity]);
  return label;
}
