import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../ui';
import { useStudentProfile } from './StudentProfileProvider';
import { ProfileForm } from './ProfileForm';
import { ProfileEstimates } from './ProfileEstimates';
import { educationLevels, preferences, depths } from './options';

export function ProfileSettings() {
  const { profile, error } = useStudentProfile();
  const [editing, setEditing] = useState(false);
  if (!profile?.details) return null;
  const details = profile.details;
  const entries = [
    ['Education level', educationLevels.find((option) => option.value === details.education_level)?.label],
    ['Field or area of study', details.field_of_study], ['Primary learning goal', details.learning_goal],
    ['Learning preference', preferences.find((option) => option.value === details.learning_preference)?.label],
    ['Explanation depth', depths.find((option) => option.value === details.explanation_depth)?.label],
  ];
  return <section className="mt-10 border-y border-border py-6" aria-label="Student profile settings">
    <div className="mb-6 flex items-start justify-between gap-4">
      <div><h2 className="text-lg font-medium tracking-tight text-heading">Your learning profile</h2>
        <p className="mt-2 text-sm leading-6 text-muted">{profile.details_source === 'eduverse' ? 'Provided by EduVerse. You can view and edit these details here.' : 'Your background, goals, and preferences. These details stay in your control.'}</p></div>
      {!editing && <Button className="shrink-0" size="sm" variant="secondary" onClick={() => setEditing(true)}>Edit profile</Button>}
    </div>
    {error && <p role="alert" className="mb-4 text-sm text-danger">{error}</p>}
    {editing ? <ProfileForm onSaved={() => setEditing(false)} onCancel={() => setEditing(false)} />
      : <dl className="grid gap-5 sm:grid-cols-2">{entries.map(([label, value]) => <div key={label} className={label === 'Primary learning goal' ? 'sm:col-span-2' : undefined}>
        <dt className="text-xs text-subtle">{label}</dt><dd className="mt-1 text-sm leading-6 text-body break-words">{value}</dd></div>)}</dl>}
    <div className="mt-8 border-t border-border pt-6"><ProfileEstimates profile={profile} /></div>
    {profile.calibration_status !== 'completed' && <div className="mt-6 flex flex-col items-start gap-3 rounded-xl border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
      <div><p className="text-sm font-medium text-heading">A better starting point</p>
        <p className="mt-1 text-xs leading-5 text-muted">Eight quick questions help Mentra personalize explanations. About 1–2 minutes.</p></div>
      <Link to="/calibration" className="shrink-0 rounded-lg px-3 py-2 text-sm font-medium text-accent hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
        {profile.calibration_status === 'in_progress' ? 'Resume calibration' : 'Start calibration'}</Link>
    </div>}
  </section>;
}
