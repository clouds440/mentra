import { PageSection } from '../workspace/PageShell';
import { FormField, Select } from '../ui';
import { setChatFontSize, useChatFontSize, type ChatFontSize } from './chatAppearance';

export function ChatAppearanceSettings() {
  const size = useChatFontSize();
  return <PageSection className="workspace-panel mt-6 space-y-4" aria-label="Chat appearance">
    <div><h2 className="text-lg font-medium tracking-tight text-heading">Chat appearance</h2><p className="mt-2 text-sm text-muted">A softer, clearer typeface for your conversations. This changes main chat text only.</p></div>
    <div className="max-w-xs"><FormField label="Chat font size">{props => <Select {...props} value={size} onChange={event => setChatFontSize(event.target.value as ChatFontSize)}><option value="small">Small</option><option value="medium">Medium (default)</option><option value="large">Large</option></Select>}</FormField></div>
    <div className="chat-prose space-y-3 rounded-panel border border-border bg-surface p-4" data-chat-size={size} aria-label="Chat text preview"><p className="text-muted">How does a new idea become clear?</p><p className="text-body">Start with a simple example, then connect each step. <strong className="font-semibold">Understanding grows with practice.</strong></p></div>
  </PageSection>;
}
