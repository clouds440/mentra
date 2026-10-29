import { LayoutGrid, List, type LucideIcon } from 'lucide-react';
import { IconButton } from './IconButton';
import { Button } from './Button';

type ToggleOption<T extends string> = { value: T; label: string; Icon: LucideIcon };
const defaultOptions = [{ value: 'grid', label: 'Grid view', Icon: LayoutGrid }, { value: 'list', label: 'List view', Icon: List }];
export function ViewToggle<T extends string = 'grid' | 'list'>({ view, onChange, label, options, showLabels = false }: {
  view: T; onChange: (view: T) => void; label: string; options?: ToggleOption<T>[]; showLabels?: boolean;
}) {
  // Legacy grid/list callers retain their existing options and appearance.
  const items = options ?? defaultOptions as ToggleOption<T>[];
  return <div role="group" aria-label={label} className="flex shrink-0 gap-1 rounded-control border border-border bg-surface p-1">
    {items.map(item => {
      const props = { 'aria-label': item.label, title: item.label, 'aria-pressed': view === item.value, className: view === item.value ? 'bg-card text-heading shadow-sm' : 'text-muted', onClick: () => onChange(item.value) };
      return showLabels ? <Button key={item.value} {...props} size="sm" variant="ghost"><item.Icon size={14} aria-hidden="true" />{item.label}</Button>
        : <IconButton key={item.value} {...props}><item.Icon size={16} aria-hidden="true" /></IconButton>;
    })}
  </div>;
}
