import { useState } from 'react';
import { Button, Spinner } from '../ui';
import { profileError, retryEvaluation } from '../../services/studentProfile';
import type { Dimension, StudentProfile } from '../../types/studentProfile';
import { useStudentProfile } from './StudentProfileProvider';
import { dimensionLabels } from './options';

export function ProfileEstimates({ profile }: { profile: StudentProfile }) {
  const { replace } = useStudentProfile();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function retry() {
    setPending(true); setError(null);
    try { replace(await retryEvaluation()); }
    catch (failure) { setError(profileError(failure)); }
    finally { setPending(false); }
  }
  const waiting = ['pending', 'evaluating', 'failed'].includes(profile.evaluation_status);
  return <section aria-label="Broad proficiency estimates">
    <h3 className="text-sm font-medium text-heading">Broad starting estimates</h3>
    <p className="mt-2 text-xs leading-5 text-muted">Provisional signals at your stated education level, not a grade or a measure of intelligence. They can develop with evidence.</p>
    {waiting && <div className="mt-4 rounded-xl border border-border bg-surface px-4 py-3">
      <p className="text-sm leading-6 text-muted">Your answers are saved. {profile.evaluation_status === 'failed' ? 'AI evaluation is temporarily unavailable.' : 'AI evaluation has not finished yet.'}</p>
      <Button className="mt-3" variant="secondary" size="sm" disabled={pending} onClick={() => { void retry(); }}>
        {pending && <Spinner className="h-4 w-4" label="Evaluating results" />}{pending ? 'Evaluating…' : 'Retry evaluation'}</Button>
      {error && <p role="alert" className="mt-3 text-xs leading-5 text-danger">{error}</p>}
    </div>}
    <dl className="mt-4 divide-y divide-border">
      {(Object.keys(dimensionLabels) as Dimension[]).map((dimension) => {
        const estimate = profile.estimates[dimension];
        const unknown = estimate.value === null || estimate.confidence === 0;
        const label = unknown ? 'Not yet estimated' : estimate.value! < .4 ? 'Developing' : estimate.value! < .7 ? 'Comfortable' : 'Strong starting point';
        return <div key={dimension} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-3">
          <dt className="text-sm text-body">{dimensionLabels[dimension]}</dt>
          <dd className="text-right text-sm text-heading"><span>{label}</span>
            <p className="mt-0.5 text-xs text-subtle">{unknown ? 'More evidence needed' : `${estimate.evidence_count} results · ${estimate.confidence <= .3 ? 'low confidence' : estimate.confidence <= .6 ? 'provisional' : 'moderate confidence'}`}</p>
          </dd>
        </div>;
      })}
    </dl>
  </section>;
}
