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
    userScrollUntil.current = 0; setAnchor(null);
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

  function position() {
    const el = container.current; if (!el) return;
    const style = getComputedStyle(el);
    const inset = parseFloat(style.paddingTop);
    const contentHeight = Math.max(0, el.clientHeight - inset - parseFloat(style.paddingBottom));
    const contentSize = `${contentHeight}px`;
    if (el.style.getPropertyValue('--chat-content-height') !== contentSize) el.style.setProperty('--chat-content-height', contentSize);
    const footer = el.querySelector<HTMLElement>('[data-chat-footer]');
    const available = Math.max(0, contentHeight - (footer?.getBoundingClientRect().height ?? 0));
    const size = `${available}px`;
    if (el.style.getPropertyValue('--latest-turn-height') !== size) el.style.setProperty('--latest-turn-height', size);
    if (prepend.current) {
      if (!loading && messages[0]?.sequence !== prepend.current.first) {
        el.scrollTop += el.scrollHeight - prepend.current.height; prepend.current = null;
      }
      return;
    }
    if (followAnchor.current && latest.current?.dataset.userSequence === String(target.current)) {
      el.scrollTop += latest.current.getBoundingClientRect().top - el.getBoundingClientRect().top - inset;
    } else if (newAnswer.current && bottom.current) {
      const answer = el.querySelector<HTMLElement>(`[data-message-id="${CSS.escape(newAnswer.current)}"]`);
      if (answer) el.scrollTop += answer.getBoundingClientRect().top - el.getBoundingClientRect().top - 24;
      newAnswer.current = null;
      bottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    } else if (bottom.current) el.scrollTop = el.scrollHeight;
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
    container, latest, groups, anchor,
    anchorNextSend() {
      requested.current = Math.max(0, ...messages.map(message => message.sequence)) + 1;
      followAnchor.current = false; bottom.current = false;
    },
    noteUserScroll() { userScrollUntil.current = performance.now() + 1500; followAnchor.current = false; },
    onScroll() {
      const el = container.current;
      if (el && performance.now() < userScrollUntil.current) bottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
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
    showLatest() { setAnchor(null); target.current = null; followAnchor.current = false; bottom.current = true; },
  };
}
