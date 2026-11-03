import { createContext, memo, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight, ImageOff } from 'lucide-react';
import { Dialog, IconButton } from '../ui';
import { publicImageUrl } from '../../lib/imageUrls';

export type GalleryImage = { src: string; alt: string; label: string; source?: string };
const GalleryContext = createContext<{ open: (index: number) => void } | null>(null);
export const useImageGallery = () => useContext(GalleryContext);
export const imageCaption = (image: GalleryImage) => (image.label || image.alt || 'Image').slice(0, 1000);

export const ImageAsset = memo(function ImageAsset({ image, expanded = false }: { image: GalleryImage; expanded?: boolean }) {
  const url = publicImageUrl(image.src, true);
  const [failedFor, setFailedFor] = useState<string>();
  return url && failedFor !== url
    ? <img src={url} alt={image.alt || imageCaption(image)} draggable={false} loading={expanded ? 'eager' : 'lazy'} decoding="async" referrerPolicy="no-referrer" onError={() => setFailedFor(url)} />
    : <span role="status" className="image-unavailable"><ImageOff size={22} aria-hidden="true" /><span>Image unavailable</span></span>;
});

/** One response owns its catalogue. Opening the viewer never reparses Markdown. */
export function ImageGallery({ images, children }: { images: GalleryImage[]; children: ReactNode }) {
  const [selected, setSelected] = useState<number | null>(null);
  const direction = useRef(1);
  const open = useCallback((index: number) => { if (index >= 0 && index < images.length) { direction.current = 1; setSelected(index); } }, [images]);
  const context = useMemo(() => ({ open }), [open]);
  const index = selected === null ? null : Math.min(selected, images.length - 1);
  const image = index !== null ? images[index] : undefined;
  const start = useRef<{ x: number; y: number; pointer: number }>();
  const stage = useRef<HTMLDivElement>(null);
  const move = (offset: number) => { direction.current = Math.sign(offset); setSelected(current => current === null ? null : Math.max(0, Math.min(images.length - 1, current + offset))); stage.current?.focus({ preventScroll: true }); };
  const source = image?.source ? publicImageUrl(image.source, true) : null;
  return <GalleryContext.Provider value={context}>{children}
    {image && index !== null && <Dialog open className="visual-fullscreen image-viewer" aria-label={`Expanded image: ${imageCaption(image)}`} onDismiss={() => setSelected(null)}
      layout="viewer" closeLabel="Close image viewer"
      heading={<span role="status" aria-live="polite" className="image-viewer-count">Image {index + 1} of {images.length}</span>}
      onKeyDown={event => {
        if (event.altKey || event.ctrlKey || event.metaKey) return;
        if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); move(event.key === 'ArrowLeft' ? -1 : 1); }
        if (event.key === 'Home' || event.key === 'End') { event.preventDefault(); setSelected(event.key === 'Home' ? 0 : images.length - 1); stage.current?.focus({ preventScroll: true }); }
      }}>
      <div className="image-viewer-stage" ref={stage} tabIndex={-1} role="group" aria-label="Image preview" data-direction={direction.current > 0 ? 'next' : 'previous'}
        onPointerDown={event => {
          if (!event.isPrimary || event.button !== 0 || (event.target instanceof Element && event.target.closest('button'))) return;
          start.current = { x: event.clientX, y: event.clientY, pointer: event.pointerId };
          if (event.pointerType === 'mouse') event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerCancel={() => { start.current = undefined; }} onPointerUp={event => {
          const from = start.current;
          if (from?.pointer !== event.pointerId) return;
          start.current = undefined;
          const x = event.clientX - from.x;
          const y = event.clientY - from.y;
          if (Math.abs(x) > 48 && Math.abs(x) > Math.abs(y) * 1.5) move(x < 0 ? 1 : -1);
        }}>
        <div className="image-viewer-frame" key={index + ':' + image.src}><ImageAsset image={image} expanded /></div>
        {images.length > 1 && <div className="image-side-navigation">
          <IconButton aria-label="Previous image" disabled={index === 0} onClick={() => move(-1)}><ChevronLeft size={16} /></IconButton>
          <IconButton aria-label="Next image" disabled={index === images.length - 1} onClick={() => move(1)}><ChevronRight size={16} /></IconButton>
        </div>}
      </div>
      <div className="image-viewer-caption" dir="auto">{imageCaption(image)}{source && <> · <a href={source} target="_blank" rel="noopener noreferrer">Source</a></>}</div>
    </Dialog>}
  </GalleryContext.Provider>;
}

/** Native scrolling keeps touch/trackpad input off React's rendering path. */
export function ImageReel({ children }: { children: ReactNode }) {
  const track = useRef<HTMLDivElement>(null);
  const drag = useRef<{ pointer: number; x: number; left: number }>();
  const dragged = useRef(false);
  const [edges, setEdges] = useState({ previous: false, next: false });
  useEffect(() => {
    const element = track.current; if (!element) return;
    let frame = 0;
    const measure = () => {
      frame = 0;
      const previous = element.scrollLeft > 2;
      const next = element.scrollLeft + element.clientWidth < element.scrollWidth - 2;
      setEdges(old => old.previous === previous && old.next === next ? old : { previous, next });
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(measure); };
    const resize = new ResizeObserver(schedule); resize.observe(element);
    element.addEventListener('scroll', schedule, { passive: true }); measure();
    return () => { resize.disconnect(); element.removeEventListener('scroll', schedule); cancelAnimationFrame(frame); };
  }, []);
  function scroll(direction: number) {
    const element = track.current; if (!element) return;
    element.scrollBy({ left: direction * element.clientWidth * .75, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
  }
  return <section className="image-reel" aria-label="Image collection"><div className="image-reel-viewport">
    <div className="image-reel-track" ref={track} role="region" aria-label="Scrollable images" tabIndex={0}
      onPointerDown={event => {
        if (event.pointerType !== 'mouse' || event.button !== 0 || !event.isPrimary) return;
        const element = event.currentTarget;
        dragged.current = false;
        if (element.scrollWidth > element.clientWidth && !(event.target instanceof Element && event.target.closest('a'))) {
          drag.current = { pointer: event.pointerId, x: event.clientX, left: element.scrollLeft };
        }
      }}
      onPointerMove={event => {
        const from = drag.current;
        if (!from || from.pointer !== event.pointerId || !(event.buttons & 1)) return;
        const delta = event.clientX - from.x;
        if (!dragged.current && Math.abs(delta) < 5) return;
        const element = event.currentTarget;
        if (!dragged.current) {
          dragged.current = true;
          element.setPointerCapture(event.pointerId);
          element.dataset.dragging = '';
        }
        element.scrollLeft = from.left - delta;
      }}
      onPointerUp={event => { drag.current = undefined; delete event.currentTarget.dataset.dragging; }}
      onLostPointerCapture={event => { drag.current = undefined; delete event.currentTarget.dataset.dragging; }}
      onPointerCancel={event => { drag.current = undefined; dragged.current = false; delete event.currentTarget.dataset.dragging; }}
      onPointerLeave={() => { if (!dragged.current) drag.current = undefined; }}
      onClickCapture={event => {
        if (dragged.current && event.detail > 0) { dragged.current = false; event.preventDefault(); event.stopPropagation(); }
      }}
      onKeyDown={event => {
        if (event.target === event.currentTarget && ['ArrowLeft', 'ArrowRight'].includes(event.key)) { event.preventDefault(); scroll(event.key === 'ArrowLeft' ? -1 : 1); }
      }}>{children}</div>
    <div className="image-side-navigation image-reel-navigation">
      <IconButton aria-label="Scroll images left" disabled={!edges.previous} onClick={() => scroll(-1)}><ChevronLeft size={16} /></IconButton>
      <IconButton aria-label="Scroll images right" disabled={!edges.next} onClick={() => scroll(1)}><ChevronRight size={16} /></IconButton>
    </div>
  </div></section>;
}
