import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { StoredMessage } from '../types/conversations';

/** Viewport-sized current exchanges provide room for replies without tail spacers. */
export function useChatScroll(id: string, messages: StoredMessage[], loading: boolean, busy: boolean, pending: boolean) {
  const container = useRef<HTMLDivElement>(null);
  const latest = useRef<HTMLDivElement>(null);
  const bottom = useRef(true);
  const followAnchor = useRef(false);
  const target = useRef<number | null>(null);
  const requested = useRef<number | null>(null);
  const known = useRef<number | null>(null);
  const newAnswer = useRef<string | null>(null);
  const prepend = useRef<{ height: number; first: number } | null>(null);
  const userScrollUntil = useRef(0);
  const lastScrollTop = useRef(0);
  const scrolledUp = useRef(false);
  const jumping = useRef(false);
  const jumpVisible = useRef(false);
  const footerVisible = useRef(false);
  const viewportHeight = useRef(0);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [anchor, setAnchor] = useState<number | null>(null);
  const groups = useMemo(() => {
    const result: { key: number; userSequence: number | null; messages: StoredMessage[] }[] = [];
    for (const message of messages) {
      if (!result.length || message.role === 'user') result.push({key:message.sequence, userSequence:message.role === 'user' ? message.sequence : null, messages:[]});
      result[result.length - 1].messages.push(message);
    }
    return result;
  }, [messages]);

  useLayoutEffect(() => {
    known.current = null; requested.current = null; target.current = null; newAnswer.current = null;
    prepend.current = null; bottom.current = true; followAnchor.current = false;
    userScrollUntil.current = 0; lastScrollTop.current = 0; scrolledUp.current = false;
    jumping.current = false; jumpVisible.current = false; setShowScrollToBottom(false); setAnchor(null);
    footerVisible.current = false; viewportHeight.current = 0;
  }, [id]);
  useLayoutEffect(() => {
    if (loading || !messages.length) return;
    const previous = known.current;
    const incoming = busy && pending ? messages.find(message => message.role === 'user'
      && message.sequence >= (requested.current ?? (previous === null ? Infinity : previous + 1))) : undefined;
    known.current = Math.max(previous ?? 0, ...messages.map(message => message.sequence));
    if (incoming) {
      requested.current = null; target.current = incoming.sequence; followAnchor.current = true;
      bottom.current = false; userScrollUntil.current = 0; setAnchor(incoming.sequence);
    } else if (previous !== null && target.current === null && bottom.current) {
      newAnswer.current = messages.find(message => message.role === 'assistant' && message.sequence > previous)?.id ?? null;
    }
  }, [messages, loading, busy, pending]);

  function updateJumpButton() {
    const el = container.current; if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    const visible = scrolledUp.current && distance > (jumpVisible.current ? 120 : Math.max(360, el.clientHeight * .75));
    if (visible !== jumpVisible.current) { jumpVisible.current = visible; setShowScrollToBottom(visible); }
  }
  function position() {
    const el = container.current; if (!el) return;
    const style = getComputedStyle(el);
    const inset = parseFloat(style.paddingTop);
    const contentHeight = Math.max(0, el.clientHeight - inset - parseFloat(style.paddingBottom));
    const footer = el.querySelector<HTMLElement>('[data-chat-footer]');
    if (viewportHeight.current && viewportHeight.current !== el.clientHeight && footerVisible.current && !scrolledUp.current) {
      // If the reader could see the footer, resizing the composer must keep it
      // visible, rather than reapplying the old exchange's top anchor.
      followAnchor.current = false; bottom.current = true;
    }
    viewportHeight.current = el.clientHeight;
    const available = Math.max(0, contentHeight - (footer?.getBoundingClientRect().height ?? 0));
    const size = `${available}px`;
    if (el.style.getPropertyValue('--latest-turn-height') !== size) el.style.setProperty('--latest-turn-height', size);
    if (jumping.current) { updateJumpButton(); return; }
    if (prepend.current) {
      if (!loading && messages[0]?.sequence !== prepend.current.first) {
        el.scrollTop += el.scrollHeight - prepend.current.height; prepend.current = null;
      }
      updateJumpButton(); return;
    }
    if (followAnchor.current && latest.current?.dataset.userSequence === String(target.current)) {
      el.scrollTop += latest.current.getBoundingClientRect().top - el.getBoundingClientRect().top - inset;
    } else if (newAnswer.current && bottom.current) {
      const answer = el.querySelector<HTMLElement>(`[data-message-id="${CSS.escape(newAnswer.current)}"]`);
      if (answer) el.scrollTop += answer.getBoundingClientRect().top - el.getBoundingClientRect().top - 24;
      newAnswer.current = null;
      bottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    } else if (bottom.current) el.scrollTop = el.scrollHeight;
    lastScrollTop.current = el.scrollTop;
    footerVisible.current = !!footer && footer.getBoundingClientRect().bottom <= el.getBoundingClientRect().bottom + 1;
    updateJumpButton();
  }
  const positioning = useRef(position); positioning.current = position;
  useLayoutEffect(() => { position(); }, [id, messages, loading, busy, anchor]);
  useLayoutEffect(() => {
    const el = container.current; if (!el) return;
    const observer = new ResizeObserver(() => positioning.current());
    observer.observe(el); if (el.firstElementChild) observer.observe(el.firstElementChild);
    return () => observer.disconnect();
  }, [id, loading, !!messages.length]);

  return {
    container, latest, groups, anchor, showScrollToBottom,
    // Composer layout effects run before paint; do not wait one observer frame
    // with the footer still positioned for the previous viewport height.
    onComposerResize() { positioning.current(); },
    anchorNextSend() {
      requested.current = Math.max(0, ...messages.map(message => message.sequence)) + 1;
      followAnchor.current = false; bottom.current = false;
      scrolledUp.current = false; jumping.current = false; updateJumpButton();
    },
    noteUserScroll() { userScrollUntil.current = performance.now() + 1500; followAnchor.current = false; jumping.current = false; },
    onScroll() {
      const el = container.current;
      if (!el) return;
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (!jumping.current && performance.now() < userScrollUntil.current) {
        const movedUp = el.scrollTop < lastScrollTop.current - 1;
        // Stop following immediately, including small upward gestures near the
        // bottom, so late image/font sizing cannot pull the reader back down.
        bottom.current = !movedUp && distance < 100;
        if (movedUp) scrolledUp.current = true;
      }
      if (distance < 2) { jumping.current = false; bottom.current = true; scrolledUp.current = false; }
      lastScrollTop.current = el.scrollTop;
      updateJumpButton();
    },
    preparePrepend() {
      prepend.current = {height:container.current?.scrollHeight ?? 0, first:messages[0]?.sequence ?? 0};
      followAnchor.current = false; bottom.current = false;
      const operation = prepend.current;
      return () => { requestAnimationFrame(() => {
        if (prepend.current !== operation) return;
        positioning.current(); prepend.current = null;
      }); };
    },
    showLatest() { setAnchor(null); target.current = null; followAnchor.current = false; bottom.current = true;
      scrolledUp.current = false; jumping.current = false; updateJumpButton(); },
    scrollToBottom() {
      const el = container.current; if (!el) return;
      jumping.current = true; followAnchor.current = false; target.current = null;
      newAnswer.current = null; bottom.current = true; setAnchor(null);
      el.focus({ preventScroll: true });
      requestAnimationFrame(() => {
        if (container.current !== el) return;
        el.scrollTo({ top: el.scrollHeight, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
      });
    },
  };
}
