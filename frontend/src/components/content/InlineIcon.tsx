import { Component, lazy, memo, Suspense, type ComponentType, type ReactNode } from 'react';
import { BookOpen, Check, CircleCheck, CircleHelp, CircleX, Clock, FileText, GraduationCap, Info, Lightbulb, Search, ShieldCheck, Star, Target, TriangleAlert, type LucideProps } from 'lucide-react';

// Frequent explanation icons render immediately using the app's existing Lucide
// dependency. The full catalog and uncommon glyphs load only if actually used.
const common: Record<string, ComponentType<LucideProps>> = {
  bookopen: BookOpen, check: Check, circlecheck: CircleCheck, circlehelp: CircleHelp,
  circlex: CircleX, clock: Clock, filetext: FileText, graduationcap: GraduationCap,
  info: Info, lightbulb: Lightbulb, search: Search, shieldcheck: ShieldCheck,
  star: Star, target: Target, trianglealert: TriangleAlert,
};
const loaded = new Map<string, ComponentType<LucideProps>>();
function Placeholder() { return <span className="rich-icon-placeholder" />; }
class IconBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <Placeholder /> : this.props.children; }
}
function resolve(name: string): ComponentType<LucideProps> {
  if (!/^[A-Za-z][A-Za-z0-9-]{0,63}$/.test(name)) return Placeholder;
  const key = name.replace(/-/g, '').toLowerCase();
  if (Object.prototype.hasOwnProperty.call(common, key)) return common[key];
  const cached = loaded.get(key);
  if (cached) return cached;
  const icon = lazy(() => import('./lucideIconCatalog').then(module => module.loadIcon(key))
    .then(icon => ({ default: icon ?? Placeholder })).catch(() => ({ default: Placeholder })));
  // Bound component definitions retained across long conversations.
  if (loaded.size >= 64) loaded.delete(loaded.keys().next().value!);
  loaded.set(key, icon);
  return icon;
}
export const InlineIcon = memo(function InlineIcon({ name }: { name: string }) {
  const Icon = resolve(name);
  return <span className="rich-icon" aria-hidden="true"><IconBoundary key={name}><Suspense fallback={<Placeholder />}><Icon size="1em" /></Suspense></IconBoundary></span>;
});
InlineIcon.displayName = 'InlineIcon';
