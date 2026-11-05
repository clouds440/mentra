import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import type { PanelResource } from '../../types/sourceAnnotations';

export interface PanelTab {
  title: string;
  content: ReactNode;
  icon?: ReactNode;
  reuseKey?: string;
  parentId?: string;
  inPlace?: boolean;
  resource?: PanelResource;
}
interface Entry extends PanelTab { entryId: string }
interface OpenTab extends Entry { id: string; entries: Entry[]; cursor: number }
interface PanelLauncher { tab: PanelTab; menuContent: ReactNode }
interface PanelState { tabs: OpenTab[]; active: string; visible: boolean; launcher?: PanelLauncher }
const empty: PanelState = { tabs: [], active: '', visible: false };

function removeTab(state: PanelState, id: string) {
  const index = state.tabs.findIndex(tab => tab.id === id);
  if (index < 0) return state;
  const tabs = state.tabs.filter(tab => tab.id !== id);
  if (!tabs.length) return { ...state, ...empty };
  return { ...state, tabs, active: state.active === id ? tabs[Math.min(index, tabs.length - 1)].id : state.active };
}

function tabAt(id: string, entries: Entry[], cursor: number): OpenTab {
  return { ...entries[cursor], entries, cursor, id };
}

const State = createContext(empty);
export const PanelEntryScope = createContext<object | undefined>(undefined);
export const PanelTabScope = createContext<string | undefined>(undefined);
export const PanelResourceScope = createContext<PanelResource | undefined>(undefined);
const Actions = createContext<{
  open: (tab: PanelTab) => void;
  select: (id: string) => void;
  close: (id: string) => void;
  go: (id: string, offset: -1 | 1) => void;
  hide: () => void;
  toggle: (allowEmpty?: boolean) => void;
  setLauncher: (tab?: PanelLauncher) => void;
} | null>(null);

export function SidePanelProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(empty);
  const actions = useMemo(() => ({
    open(tab: PanelTab) {
      const entry = { ...tab, entryId: crypto.randomUUID() };
      setState(value => {
        const parent = value.tabs.find(open => open.id === tab.parentId);
        if (parent && tab.inPlace) {
          const entries = [...parent.entries.slice(Math.max(0, parent.cursor - 28), parent.cursor + 1), entry];
          return { ...value, tabs: value.tabs.map(open => open === parent ? tabAt(parent.id, entries, entries.length - 1) : open),
            active: parent.id, visible: true };
        }
        const existing = tab.reuseKey && value.tabs.find(open => open.reuseKey === tab.reuseKey);
        if (existing) return { ...value, active: existing.id, visible: true };
        // A source opened from a list gets its own tab with a local return
        // point. Closing the originating tab does not invalidate that history.
        const entries = parent ? [parent.entries[parent.cursor], entry] : [entry];
        return { ...value, tabs: [...value.tabs, tabAt(entry.entryId, entries, entries.length - 1)], active: entry.entryId, visible: true };
      });
    },
    select(id: string) {
      setState(value => value.tabs.some(tab => tab.id === id) ? { ...value, active: id } : value);
    },
    close(id: string) { setState(value => removeTab(value, id)); },
    go(id: string, offset: -1 | 1) {
      setState(value => {
        const tab = value.tabs.find(open => open.id === id);
        const cursor = (tab?.cursor ?? 0) + offset;
        if (!tab || cursor < 0 || cursor >= tab.entries.length) return value;
        return { ...value, tabs: value.tabs.map(open => open === tab ? tabAt(id, tab.entries, cursor) : open) };
      });
    },
    hide() { setState(value => value.visible ? { ...value, visible: false } : value); },
    toggle(allowEmpty = false) {
      const id = crypto.randomUUID();
      setState(value => {
        if (value.tabs.length) return { ...value, visible: !value.visible };
        if (!value.launcher) return allowEmpty ? { ...value, visible: !value.visible } : value;
        return { ...value, tabs: [tabAt(id, [{ ...value.launcher.tab, entryId: id }], 0)], active: id, visible: true };
      });
    },
    setLauncher(launcher?: PanelLauncher) { setState(value => value.launcher === launcher ? value : { ...value, launcher }); },
  }), []);
  return <Actions.Provider value={actions}><State.Provider value={state}>{children}</State.Provider></Actions.Provider>;
}

export const useSidePanelActions = () => useContext(Actions);
export const useSidePanelState = () => useContext(State);
