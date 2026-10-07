import { Monitor, Moon, Sun } from 'lucide-react';
import { cn } from '../../utils/cn';
import { useTheme } from './ThemeProvider';

const options = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
] as const;

export function ThemeSelector({ collapsed }: { collapsed: boolean }) {
  const { preference, setPreference } = useTheme();
  return (
    <fieldset className="mt-3 min-w-0">
      <legend className={cn('mb-2 px-3 text-[11px] font-medium text-subtle', collapsed && 'lg:sr-only')}>
        Appearance
      </legend>
      <div className={cn('flex gap-1 rounded-lg border border-border p-1', collapsed && 'lg:flex-col')}>
        {options.map(({ value, label, icon: Icon }) => (
          <label key={value} className="relative min-w-0 flex-1 cursor-pointer">
            <input
              className="peer sr-only"
              type="radio"
              name="theme"
              value={value}
              checked={preference === value}
              onChange={() => setPreference(value)}
              aria-label={`${label} theme`}
            />
            <span
              title={`${label} theme`}
              className="flex min-h-8 items-center justify-center gap-1.5 rounded-md px-1 text-[11px] text-muted hover:bg-hover peer-checked:bg-active peer-checked:text-foreground peer-focus-visible:ring-2 peer-focus-visible:ring-accent"
            >
              <Icon aria-hidden="true" size={14} className="shrink-0" />
              <span className={cn(collapsed && 'lg:hidden')}>{label}</span>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
