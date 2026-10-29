import { PageSection } from '../workspace/PageShell';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Dialog } from '../ui';
import { useStudentProfile } from './StudentProfileProvider';
import { ProfileForm } from './ProfileForm';
import { ProfileEstimates } from './ProfileEstimates';
import { educationLevels, preferences, depths, participationOptions, visualOptions, purposeOptions, editableDetails } from './options';

export function ProfileSettings() {
  const { profile, error } = useStudentProfile();
  const [editing, setEditing] = useState(false);
  if (!profile?.details) return null;
  const details = editableDetails(profile.details);
  const entries: [string, string | undefined][] = [
    ['What Mentra calls you', details.preferred_name || 'Not set'],
    ['Education level', educationLevels.find((option) => option.value === details.education_level)?.label],
    ['Background or interests', details.field_of_study], ['Primary learning goal', details.learning_goal],
    ['Learning purpose', purposeOptions.find(option => option.value === details.learning_purpose)?.label],
    ['Teaching approach', preferences.find((option) => option.value === details.learning_preference)?.label],
    ['Participation', participationOptions.find(option => option.value === details.participation)?.label],
    ['Explanation detail', depths.find((option) => option.value === details.explanation_depth)?.label],
    ['Visual support', visualOptions.find(option => option.value === details.visual_support)?.label],
  ];
  return <PageSection className="workspace-panel space-y-5" aria-label="Student profile settings">
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="text-lg font-medium tracking-tight text-heading">Your learning profile</h2>
        <p className="mt-2 text-sm leading-6 text-muted">Your background, goals, and preferences. These details stay in your control.</p></div>
      <Button className="shrink-0" size="sm" variant="secondary" onClick={() => setEditing(true)}>Edit profile</Button>
    </div>
    {error && <p role="alert" className="mb-4 text-sm text-danger">{error}</p>}
    {editing && <Dialog open onDismiss={() => setEditing(false)} aria-label="Edit learning profile" className="max-w-3xl"><h2 className="mb-5 text-lg font-semibold">Edit learning profile</h2><ProfileForm onSaved={() => setEditing(false)} onCancel={() => setEditing(false)} /></Dialog>}
      <dl className="grid gap-3 sm:grid-cols-2">{entries.map(([label, value]) => <div key={label} className={`rounded-control border border-border bg-surface p-3 ${['Primary learning goal', 'Background or interests'].includes(label) ? 'sm:col-span-2' : ''}`}>
        <dt className="text-xs text-subtle">{label}</dt><dd className="mt-1 text-sm leading-6 text-body break-words">{value}</dd></div>)}</dl>
    <div className="mt-5 border-t border-border pt-4"><ProfileEstimates profile={profile} /></div>
    {profile.calibration_status !== 'completed' && <div className="mt-6 flex flex-col items-start gap-3 rounded-xl border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
      <div><p className="text-sm font-medium text-heading">A better starting point</p>
        <p className="mt-1 text-xs leading-5 text-muted">Eight quick questions help Mentra personalize explanations. About 1–2 minutes.</p></div>
      <Link to="/calibration" className="shrink-0 rounded-lg px-3 py-2 text-sm font-medium text-accent hover:bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
        {profile.calibration_status === 'in_progress' ? 'Resume calibration' : 'Start calibration'}</Link>
    </div>}
  </PageSection>;
}
