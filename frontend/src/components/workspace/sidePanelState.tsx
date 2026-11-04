import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

export interface PanelTab {
  title: string;
  content: ReactNode;
  icon?: ReactNode;
  reuseKey?: string;
  parentId?: string;
}
interface OpenTab extends PanelTab { id: string }
interface PanelState { tabs: OpenTab[]; active: string; visible: boolean; launcher?: PanelTab }
const empty: PanelState = { tabs: [], active: '', visible: false };

function removeTab(state: PanelState, id: string) {
  const index = state.tabs.findIndex(tab => tab.id === id);
  if (index < 0) return state;
  const tabs = state.tabs.filter(tab => tab.id !== id);
  if (!tabs.length) return { ...state, ...empty };
  return { ...state, tabs, active: state.active === id ? tabs[Math.min(index, tabs.length - 1)].id : state.active };
}

const State = createContext(empty);
export const PanelTabScope = createContext<string | undefined>(undefined);
const Actions = createContext<{
  open: (tab: PanelTab) => void;
  select: (id: string) => void;
  close: (id: string) => void;
  back: (id: string) => void;
  hide: () => void;
  toggle: () => void;
  setLauncher: (tab?: PanelTab) => void;
} | null>(null);

export function SidePanelProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(empty);
  const actions = useMemo(() => ({
    open(tab: PanelTab) {
      const item = { ...tab, id: crypto.randomUUID() };
      setState(value => {
        const existing = tab.reuseKey && value.tabs.find(open => open.reuseKey === tab.reuseKey);
        return existing ? { ...value, active: existing.id, visible: true }
          : { ...value, tabs: [...value.tabs, item], active: item.id, visible: true };
      });
    },
    select(id: string) {
      setState(value => value.tabs.some(tab => tab.id === id) ? { ...value, active: id } : value);
    },
    close(id: string) {
      setState(value => removeTab(value, id));
    },
    back(id: string) {
      setState(value => {
        const parentId = value.tabs.find(tab => tab.id === id)?.parentId;
        return parentId && value.tabs.some(tab => tab.id === parentId) ? { ...value, active: parentId } : removeTab(value, id);
      });
    },
    hide() { setState(value => value.visible ? { ...value, visible: false } : value); },
    toggle() {
      const id = crypto.randomUUID();
      setState(value => value.tabs.length ? { ...value, visible: !value.visible }
        : value.launcher ? { ...value, tabs: [{ ...value.launcher, id }], active: id, visible: true } : value);
    },
    setLauncher(launcher?: PanelTab) { setState(value => value.launcher === launcher ? value : { ...value, launcher }); },
  }), []);
  return <Actions.Provider value={actions}><State.Provider value={state}>{children}</State.Provider></Actions.Provider>;
}

export const useSidePanelActions = () => useContext(Actions);
export const useSidePanelState = () => useContext(State);
