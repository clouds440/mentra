import { useState, type FormEvent } from 'react';
import { Button, Input, Select, Spinner, Textarea } from '../ui';
import { ApiError } from '../../services/api';
import { profileError, updateDetails } from '../../services/studentProfile';
import { useStudentProfile } from './StudentProfileProvider';
import type { EducationLevel, ProfileDetails } from '../../types/studentProfile';
import { educationLevels, preferences, depths } from './options';

export function ProfileForm({ onSaved, onCancel }: { onSaved?: () => void; onCancel?: () => void }) {
  const { profile, replace, refresh } = useStudentProfile();
  const [details, setDetails] = useState<Omit<ProfileDetails, 'education_level'> & { education_level: EducationLevel | '' }>(profile?.details ?? {
    education_level: '', field_of_study: '', learning_goal: '', learning_preference: 'balanced', explanation_depth: 'standard',
  });
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  function change<K extends keyof typeof details>(key: K, value: typeof details[K]) {
    setDetails((current) => ({ ...current, [key]: value }));
    setFields((current) => ({ ...current, [key]: '' }));
    setError(null);
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !profile) return;
    const issues: Record<string, string> = {};
    if (!details.education_level) issues.education_level = 'Select your education level.';
    if (!details.field_of_study.trim()) issues.field_of_study = 'Enter your field or area of study.';
    if (details.learning_goal.trim().length < 5) issues.learning_goal = 'Add a short sentence about what you want to learn.';
    setFields(issues);
    if (Object.keys(issues).length) {
      event.currentTarget.querySelector<HTMLElement>(`[name="${Object.keys(issues)[0]}"]`)?.focus();
      return;
    }
    setPending(true); setError(null);
    try {
      const next = await updateDetails({ ...details, education_level: details.education_level as EducationLevel,
        field_of_study: details.field_of_study.trim(), learning_goal: details.learning_goal.trim() }, profile.version);
      replace(next); onSaved?.();
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 422) {
        const validation: Record<string, string> = {};
        for (const issue of failure.details) validation[String(issue.location[issue.location.length - 1])] = issue.message.replace(/^Value error, /, '');
        setFields(validation);
      }
      setError(profileError(failure));
      if (failure instanceof ApiError && failure.status === 409) await refresh().catch(() => {});
    } finally { setPending(false); }
  }
  const fieldError = (name: string) => fields[name] && <p id={`${name}-error`} role="alert" className="mt-2 text-xs leading-5 text-danger">{fields[name]}</p>;
  return <form aria-label="Student profile" aria-busy={pending} noValidate onSubmit={submit} className="space-y-5">
    {error && <p role="alert" className="rounded-xl border border-danger/20 bg-danger/5 px-4 py-3 text-sm text-danger">{error}</p>}
    <fieldset disabled={pending} className="space-y-5">
      <div>
        <label htmlFor="education_level" className="mb-2 block text-sm font-medium text-heading">Education level</label>
        <Select id="education_level" name="education_level" required value={details.education_level}
          aria-invalid={Boolean(fields.education_level)} aria-describedby={fields.education_level ? 'education_level-error' : undefined}
          onChange={(event) => change('education_level', event.target.value as EducationLevel)}>
          <option value="" disabled>Select a level</option>
          {educationLevels.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
        </Select>{fieldError('education_level')}
      </div>
      <div>
        <label htmlFor="field_of_study" className="mb-2 block text-sm font-medium text-heading">Field or area of study</label>
        <Input id="field_of_study" name="field_of_study" required maxLength={120} value={details.field_of_study}
          placeholder="e.g. General studies, Computer science" aria-invalid={Boolean(fields.field_of_study)}
          aria-describedby={fields.field_of_study ? 'field_of_study-error' : 'field-hint'} onChange={(event) => change('field_of_study', event.target.value)} />
        {fieldError('field_of_study') || <p id="field-hint" className="mt-2 text-xs leading-5 text-subtle">General studies is fine if you haven’t chosen a major.</p>}
      </div>
      <div>
        <label htmlFor="learning_goal" className="mb-2 block text-sm font-medium text-heading">Primary learning goal</label>
        <Textarea id="learning_goal" name="learning_goal" className="min-h-20" required minLength={5} maxLength={500}
          placeholder="What would you like Mentra to help you learn?" value={details.learning_goal}
          aria-invalid={Boolean(fields.learning_goal)} aria-describedby={fields.learning_goal ? 'learning_goal-error' : undefined}
          onChange={(event) => change('learning_goal', event.target.value)} />{fieldError('learning_goal')}
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <div><label htmlFor="learning_preference" className="mb-2 block text-sm font-medium text-heading">Learning preference</label>
          <Select id="learning_preference" name="learning_preference" value={details.learning_preference}
            onChange={(event) => change('learning_preference', event.target.value as ProfileDetails['learning_preference'])}>
            {preferences.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
          </Select></div>
        <div><label htmlFor="explanation_depth" className="mb-2 block text-sm font-medium text-heading">Explanation depth</label>
          <Select id="explanation_depth" name="explanation_depth" value={details.explanation_depth}
            onChange={(event) => change('explanation_depth', event.target.value as ProfileDetails['explanation_depth'])}>
            {depths.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
          </Select></div>
      </div>
    </fieldset>
    <p className="text-xs leading-5 text-subtle">Only you can change these details. Mentra adapts its estimates, not your education level or preferences.</p>
    {onCancel && <p className="text-xs leading-5 text-subtle">Changing your education level resets broad estimates. Changing your field resets domain familiarity.</p>}
    <div className="flex flex-wrap gap-3 pt-1">
      <Button type="submit" disabled={pending}>{pending && <Spinner className="h-4 w-4" label="Saving profile" />}
        {pending ? 'Saving…' : onCancel ? 'Save profile' : 'Continue'}</Button>
      {onCancel && <Button disabled={pending} variant="ghost" onClick={onCancel}>Cancel</Button>}
    </div>
  </form>;
}
