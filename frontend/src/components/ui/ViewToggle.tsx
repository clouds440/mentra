import { LayoutGrid, List } from 'lucide-react';
import { IconButton } from './IconButton';

export function ViewToggle({view, onChange, label}: {view: 'grid' | 'list'; onChange: (view: 'grid' | 'list') => void; label: string}) {
  return <div role="group" aria-label={label} className="flex shrink-0 gap-1 rounded-control border border-border bg-surface p-1">
    {([{value:'grid', label:'Grid view', Icon:LayoutGrid}, {value:'list', label:'List view', Icon:List}] as const).map(item => <IconButton key={item.value} aria-label={item.label} title={item.label} aria-pressed={view === item.value} className={view === item.value ? 'bg-card text-heading shadow-sm' : 'text-muted'} onClick={() => onChange(item.value)}><item.Icon size={16} aria-hidden="true" /></IconButton>)}
  </div>;
}
