import { ArrowLeft, ArrowRight, ChevronLeft, ChevronRight, List, PanelRight, X } from 'lucide-react';
import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode, type KeyboardEvent } from 'react';
import { useMobileNavigation } from '../../hooks/useMobileNavigation';
import { useResizableSidebar } from '../../hooks/useResizableSidebar';
import { IconButton } from '../ui/IconButton';
import { Popover } from '../ui/Popover';
import { Tabs } from '../ui/Tabs';
import { PinSourceButton, PinnedSourceList, usePinnedSources } from './PinnedSources';
import { WebSourcePreview } from '../webSearch/WebSourcePreview';
import { SourceSelection } from './SourceAnnotations';
import type { PanelResource } from '../../types/sourceAnnotations';
import { PanelEntryScope, PanelResourceScope, PanelTabScope, useSidePanelActions, useSidePanelState } from './sidePanelState';

const panelId = 'workspace-side-panel';
const desktopQuery = '(min-width: 1200px)';
const resizeOptions = { min: 340, max: 600, initial: 410, rail: 0, side: 'right', id: panelId,
  label: 'Resize side panel', storageKey: 'mentra.side-panel.width.v1', desktopQuery };
const drawerOptions = { desktopQuery, inertIds: ['workspace-content', 'main-sidebar'], closeOnDesktop: false, opener: '',
  fallbackFocus: '[aria-controls="workspace-side-panel"]:is(button), #workspace-main' };

export function SidePanelTrigger({ inDrawer = false }: { inDrawer?: boolean }) {
  const { visible } = useSidePanelState();
  const actions = useSidePanelActions();
  const label = visible ? 'Hide side panel' : 'Open side panel';
  return <IconButton size="sm" className={inDrawer ? 'workspace-chrome-control' : 'workspace-chrome-control workspace-panel-global-trigger'} aria-label={label} title={label} aria-controls={panelId} aria-expanded={visible} onClick={() => visible ? actions?.hide() : actions?.toggle(true)}>
    <PanelRight size={17} aria-hidden="true" />
  </IconButton>;
}

export function SidePanel() {
  const { tabs, active, visible, launcher } = useSidePanelState();
  const actions = useSidePanelActions()!;
  const panel = useRef<HTMLElement>(null);
  const rail = useRef<HTMLDivElement>(null);
  const strip = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ overflow: false, left: false, right: false });
  const browseButton = useRef<HTMLButtonElement>(null);
  const browseId = useId();
  const [browsing, setBrowsing] = useState(false);
  const [browseSection, setBrowseSection] = useState<'chat' | 'pinned'>('chat');
  const section = launcher ? browseSection : 'pinned';
  const { error: pinError, items: pins, busy: pinsBusy } = usePinnedSources();
  const [hasBrowsed, setHasBrowsed] = useState(false);
  const drag = useRef<{ pointer: number; start: number; scroll: number; moved: boolean }>(undefined);
  const opener = useRef<HTMLElement | null>(null);
  const sidebar = useResizableSidebar(resizeOptions);
  const desktop = useMobileNavigation(panel, visible, actions.hide, drawerOptions);
  const tabId = (id: string) => 'workspace-tab-' + id;
  const contentId = (id: string) => 'workspace-content-' + id;
  useLayoutEffect(() => {
    if (panel.current) panel.current.inert = !visible;
    if (!desktop || !visible) return;
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    return () => {
      if (panel.current?.contains(document.activeElement) || document.activeElement === document.body) {
        requestAnimationFrame(() => {
          if (!panel.current?.inert) return;
          const target = opener.current?.isConnected && !opener.current.closest('[inert]') && opener.current.getClientRects().length ? opener.current
            : document.querySelector<HTMLElement>('[aria-controls="workspace-side-panel"]:is(button)') ?? document.getElementById('workspace-main');
          target?.focus({ preventScroll: true });
        });
      }
    };
  }, [desktop, visible]);
  useEffect(() => {
    if (!visible || !active) return;
    const tab = document.getElementById(tabId(active));
    const item = tab?.parentElement;
    const row = strip.current;
    if (item && row) {
      // The drawer is partly outside the viewport while opening. Scroll only
      // its tab strip so the browser cannot pull the workspace sideways.
      const bounds = item.getBoundingClientRect();
      const viewport = row.getBoundingClientRect();
      if (bounds.left < viewport.left) row.scrollLeft += bounds.left - viewport.left;
      else if (bounds.right > viewport.right) row.scrollLeft += bounds.right - viewport.right;
    }
    if (!document.querySelector('dialog[open]')) tab?.focus({ preventScroll: true });
  }, [visible, active, desktop]);
  useEffect(() => { setBrowsing(false); }, [active, visible]);
  function measureTabs() {
    const row = strip.current;
    const frame = rail.current;
    if (!row || !frame || !frame.clientWidth) return;
    const first = row.firstElementChild as HTMLElement | null;
    const last = row.lastElementChild as HTMLElement | null;
    const width = first && last ? last.offsetLeft + last.offsetWidth - first.offsetLeft : 0;
    const overflow = width > frame.clientWidth + 1;
    const left = overflow && row.scrollLeft > 1;
    const right = overflow && row.scrollLeft < row.scrollWidth - row.clientWidth - 1;
    setEdges(old => old.overflow === overflow && old.left === left && old.right === right ? old : { overflow, left, right });
  }
  useLayoutEffect(() => {
    if (!visible || !rail.current || !strip.current) return;
    const observer = new ResizeObserver(measureTabs);
    observer.observe(rail.current);
    observer.observe(strip.current);
    measureTabs();
    return () => observer.disconnect();
  }, [tabs, visible]);
  function scrollTabs(direction: number) {
    const row = strip.current;
    if (row) row.scrollBy({ left: direction * Math.max(90, row.clientWidth * .75),
      behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
  }

  function tabKey(event: KeyboardEvent<HTMLButtonElement>, id: string) {
    const index = tabs.findIndex(tab => tab.id === id);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1
      : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length
      : event.key === 'ArrowRight' ? (index + 1) % tabs.length : -1;
    if (event.key === 'Delete') {
      event.preventDefault();
      closeTab(id);
    } else if (next >= 0) {
      event.preventDefault();
      actions.select(tabs[next].id);
      document.getElementById(tabId(tabs[next].id))?.focus({ preventScroll: true });
    }
  }
  function closeTab(id: string) {
    const index = tabs.findIndex(tab => tab.id === id);
    const next = active !== id ? active : (tabs[index + 1] ?? tabs[index - 1])?.id;
    if (next) document.getElementById(tabId(next))?.focus({ preventScroll: true });
    actions.close(id);
  }
  return <>
    {visible && !desktop && <button type="button" tabIndex={-1} className="workspace-panel-backdrop overlay-backdrop" aria-label="Dismiss side panel" onClick={actions.hide} />}
    <aside ref={panel} id={panelId} tabIndex={-1} aria-label="Side panel" aria-hidden={!visible || undefined}
      role={!desktop && visible ? 'dialog' : undefined} aria-modal={!desktop && visible || undefined} data-modal-navigation={!desktop && visible || undefined}
      className="workspace-side-panel" data-open={visible} data-resizing={sidebar.resizing}
      onKeyDown={event => {
        if (event.key !== 'Escape' || event.defaultPrevented) return;
        if (browsing) { event.preventDefault(); setBrowsing(false); browseButton.current?.focus(); }
        else if (desktop && panel.current?.contains(event.target as Node)) actions.hide();
      }}
      style={{ '--right-panel-width': sidebar.width + 'px' } as CSSProperties}>
      {visible && desktop && <div {...sidebar.handleProps} className="workspace-panel-resize" title="Drag to resize · Double-click to reset" />}
      <div className="workspace-panel-shell">
        <header className="workspace-panel-tabs">
          <div ref={rail} className="workspace-panel-rail">
            {edges.overflow && <IconButton size="sm" className="workspace-panel-chevron" aria-label="Scroll tabs left" disabled={!edges.left} onClick={() => scrollTabs(-1)}><ChevronLeft size={14} aria-hidden="true" /></IconButton>}
            <div ref={strip} role={tabs.length ? 'tablist' : undefined} aria-label={tabs.length ? 'Side panel tabs' : undefined} className="workspace-panel-strip" onScroll={measureTabs}
              onPointerDown={event => {
                if (event.button === 0 && event.isPrimary && event.pointerType === 'mouse' && event.currentTarget.scrollWidth > event.currentTarget.clientWidth)
                  drag.current = { pointer: event.pointerId, start: event.clientX, scroll: event.currentTarget.scrollLeft, moved: false };
              }}
              onPointerMove={event => {
                const start = drag.current;
                if (!start || event.pointerId !== start.pointer || !(event.buttons & 1)) return;
                const delta = event.clientX - start.start;
                if (!start.moved && Math.abs(delta) < 5) return;
                if (!start.moved) {
                  start.moved = true;
                  event.currentTarget.setPointerCapture(event.pointerId);
                }
                event.currentTarget.scrollLeft = start.scroll - delta;
              }}
              onPointerLeave={() => { if (!drag.current?.moved) drag.current = undefined; }}
              onPointerCancel={() => { drag.current = undefined; }}
              onPointerUp={() => { requestAnimationFrame(() => { drag.current = undefined; }); }}
              onClickCapture={event => { if (drag.current?.moved) { event.preventDefault(); event.stopPropagation(); } }}>
              {!tabs.length && <span className="workspace-panel-label">Sources</span>}
              {tabs.map(tab => <div key={tab.id} role="presentation" className="workspace-panel-tab" data-selected={tab.id === active}>
                <button type="button" id={tabId(tab.id)} role="tab" aria-controls={contentId(tab.id)} aria-selected={tab.id === active}
                  tabIndex={tab.id === active ? 0 : -1} title={tab.title} onClick={() => actions.select(tab.id)} onKeyDown={event => tabKey(event, tab.id)}>
                  {tab.icon}<span>{tab.title}</span>
                </button>
                <IconButton size="sm" aria-label={'Close tab: ' + tab.title} tabIndex={tab.id === active ? 0 : -1} onClick={() => closeTab(tab.id)}><X size={13} aria-hidden="true" /></IconButton>
              </div>)}
            </div>
            {edges.overflow && <IconButton size="sm" className="workspace-panel-chevron" aria-label="Scroll tabs right" disabled={!edges.right} onClick={() => scrollTabs(1)}><ChevronRight size={14} aria-hidden="true" /></IconButton>}
          </div>
          <IconButton ref={browseButton} size="sm" aria-label="Browse" aria-expanded={browsing} aria-controls={browsing ? browseId : undefined}
              title="Browse sources" className="workspace-browse-trigger" onClick={() => { setHasBrowsed(true); setBrowsing(value => !value); }}><List size={17} aria-hidden="true" /></IconButton>
            <Popover anchor={browseButton} open={browsing && visible} onClose={() => setBrowsing(false)} id={browseId} role="region" label="Browse sources"
              width={Math.min(340, sidebar.width - 24)} maxHeight={450} align="end" className="workspace-browse-popover" dismissOnFocusOutside={false}
              focusOnOpen keepMounted={hasBrowsed} portalContainer={panel}>
              <div className="workspace-browse-tabs">
                <Tabs label="Browse categories" value={section} onChange={setBrowseSection} options={[
                  { value: 'chat', label: 'From this chat', id: browseId + '-chat', panel: browseId + '-chat-content', disabled: !launcher },
                  { value: 'pinned', label: 'Pinned', id: browseId + '-pinned', panel: browseId + '-pinned-content' },
                ]} />
              </div>
              <div role="tabpanel" aria-labelledby={browseId + '-chat'} id={browseId + '-chat-content'} hidden={section !== 'chat'}
                onClick={event => { if (event.target instanceof Element && event.target.closest('a[href], [data-open-panel-source]')) setBrowsing(false); }}
                onAuxClick={event => { if (event.button === 1 && event.target instanceof Element && event.target.closest('a[href]')) setBrowsing(false); }}>
                <PanelTabScope.Provider value={active || undefined}>{launcher?.menuContent}</PanelTabScope.Provider>
              </div>
              <div role="tabpanel" aria-labelledby={browseId + '-pinned'} id={browseId + '-pinned-content'} hidden={section !== 'pinned'}>
                {section === 'pinned' && <PinnedSourceList onChoose={() => setBrowsing(false)} />}
              </div>
            </Popover>
          {!desktop && visible && <SidePanelTrigger inDrawer />}
        </header>
        {tabs.map(tab => {
          const source = tab.resource;
          const navigation = <>
            <IconButton size="sm" aria-label="Back" title="Back" disabled={!tab.cursor} onClick={() => actions.go(tab.id, -1)}><ArrowLeft size={15} aria-hidden="true" /></IconButton>
            <IconButton size="sm" aria-label="Forward" title="Forward" disabled={tab.cursor === tab.entries.length - 1} onClick={() => actions.go(tab.id, 1)}><ArrowRight size={15} aria-hidden="true" /></IconButton>
          </>;
          const pin = source && source.kind !== 'web' && <PinSourceButton source={source} />;
          return <section key={tab.id} id={contentId(tab.id)} role="tabpanel" aria-labelledby={tabId(tab.id)}
            className="workspace-panel-content" tabIndex={0} hidden={tab.id !== active}>
            {source?.kind !== 'web' && (source || tab.entries.length > 1) && <div className="workspace-resource-toolbar" data-no-excerpt>
              {navigation}<span className="flex-1" />{pin}
            </div>}
            <PanelTabScope.Provider value={tab.id}><PanelResourceScope.Provider value={source}>
              <PanelEntryScope.Provider value={tab.entries[tab.cursor]}>
                <ResourceContent key={tab.entryId} enabled={tab.id === active && visible} source={source}>
                  {source?.kind === 'web' ? <WebSourcePreview source={source} navigation={navigation} /> : tab.content}
                  {source && pinError && <p role="alert" className="px-3 py-1 text-xs text-danger" data-no-excerpt>{pinError}</p>}
                </ResourceContent>
              </PanelEntryScope.Provider>
            </PanelResourceScope.Provider></PanelTabScope.Provider>
          </section>;
        })}
        {!tabs.length && visible && <div className="workspace-panel-empty">
          <PanelRight size={28} strokeWidth={1.4} aria-hidden="true" />
          <h2>Your sources, beside your work</h2>
          <p>Open a Library material or a chat source to read it here. Pin useful sources to return to them across chats.</p>
          {(pins.length > 0 || pinsBusy || pinError) && <PinnedSourceList />}
        </div>}
      </div>
    </aside>
  </>;
}

function ResourceContent({ enabled, source, children }: { enabled: boolean; source?: PanelResource; children: ReactNode }) {
  const content = useRef<HTMLDivElement>(null);
  return <div ref={content} className="workspace-resource-content">
    {children}
    {enabled && <SourceSelection scope={content} source={source} />}
  </div>;
}
