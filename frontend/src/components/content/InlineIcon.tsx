import { Component, lazy, memo, Suspense, type ComponentType, type ReactNode } from 'react';
import type { LucideProps } from 'lucide-react';
const loaded = new Map<string, ComponentType<LucideProps>>();
const IconAsset = lazy(() => import('./IconAsset'));
function Placeholder() { return <span className="rich-icon-placeholder" />; }
class IconBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <Placeholder /> : this.props.children; }
}
function resolve(name: string): ComponentType<LucideProps> {
  if (!/^[A-Za-z][A-Za-z0-9-]{0,63}$/.test(name)) return Placeholder;
  const key = name.replace(/-/g, '').toLowerCase();
  const cached = loaded.get(key);
  if (cached) return cached;
  const icon = lazy(() => import('./lucideIconCatalog').then(module => module.loadIcon(key))
    .then(icon => ({ default: icon ?? Placeholder })).catch(() => ({ default: Placeholder })));
  // Bound component definitions retained across long conversations.
  if (loaded.size >= 64) loaded.delete(loaded.keys().next().value!);
  loaded.set(key, icon);
  return icon;
}
export const InlineIcon = memo(function InlineIcon({ name, viewBox, variant }: { name: string; viewBox?: string; variant?: string }) {
  const Icon = resolve(name);
  const asset = /^https:\/\/|^[Mm][\d\s.,+-]/.test(name);
  return <span className="rich-icon" aria-hidden="true"><IconBoundary key={name}><Suspense fallback={<Placeholder />}>{asset ? <IconAsset key={`${name}:${viewBox}:${variant}`} input={name} viewBox={viewBox} variant={variant} /> : <Icon size="1em" />}</Suspense></IconBoundary></span>;
});
InlineIcon.displayName = 'InlineIcon';
