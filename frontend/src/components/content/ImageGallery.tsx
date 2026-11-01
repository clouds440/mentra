import { createContext, memo, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight, ImageOff, X } from 'lucide-react';
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
  const start = useRef<{ x: number; y: number }>();
  const stage = useRef<HTMLDivElement>(null);
  const move = (offset: number) => { direction.current = Math.sign(offset); setSelected(current => current === null ? null : Math.max(0, Math.min(images.length - 1, current + offset))); stage.current?.focus({ preventScroll: true }); };
  const source = image?.source ? publicImageUrl(image.source, true) : null;
  return <GalleryContext.Provider value={context}>{children}
    {image && index !== null && <Dialog open className="visual-fullscreen image-viewer" aria-label={`Expanded image: ${imageCaption(image)}`} onDismiss={() => setSelected(null)}
      onKeyDown={event => {
        if (event.altKey || event.ctrlKey || event.metaKey) return;
        if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); move(event.key === 'ArrowLeft' ? -1 : 1); }
        if (event.key === 'Home' || event.key === 'End') { event.preventDefault(); setSelected(event.key === 'Home' ? 0 : images.length - 1); stage.current?.focus({ preventScroll: true }); }
      }}>
      <div className="image-viewer-toolbar"><span role="status" aria-live="polite" className="text-xs tabular-nums">Image {index + 1} of {images.length}</span><div className="flex items-center gap-2">
        {images.length > 1 && <><IconButton aria-label="Previous image" disabled={index === 0} onClick={() => move(-1)}><ChevronLeft size={20} /></IconButton><IconButton aria-label="Next image" disabled={index === images.length - 1} onClick={() => move(1)}><ChevronRight size={20} /></IconButton></>}
        <IconButton aria-label="Close image viewer" onClick={() => setSelected(null)}><X size={20} /></IconButton>
      </div></div>
      <div className="image-viewer-stage" ref={stage} tabIndex={-1} role="group" aria-label="Image preview" data-direction={direction.current > 0 ? 'next' : 'previous'} onPointerDown={event => { if (event.pointerType === 'touch' && event.isPrimary) start.current = { x: event.clientX, y: event.clientY }; }}
        onPointerCancel={() => { start.current = undefined; }} onPointerUp={event => {
          const from = start.current; start.current = undefined;
          if (from && Math.abs(event.clientX - from.x) > 48 && Math.abs(event.clientX - from.x) > Math.abs(event.clientY - from.y) * 1.5) move(event.clientX < from.x ? 1 : -1);
        }}><div className="image-viewer-frame" key={`${index}:${image.src}`}><ImageAsset image={image} expanded /></div></div>
      <div className="image-viewer-caption" dir="auto">{imageCaption(image)}{source && <> · <a href={source} target="_blank" rel="noopener noreferrer">Source</a></>}</div>
    </Dialog>}
  </GalleryContext.Provider>;
}

/** Native scrolling keeps touch/trackpad input off React's rendering path. */
export function ImageReel({ children }: { children: ReactNode }) {
  const track = useRef<HTMLDivElement>(null);
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
  return <section className="image-reel" aria-label="Image collection"><div className="image-reel-track" ref={track} role="region" aria-label="Scrollable images" tabIndex={0} onKeyDown={event => {
    if (event.target === event.currentTarget && ['ArrowLeft', 'ArrowRight'].includes(event.key)) { event.preventDefault(); scroll(event.key === 'ArrowLeft' ? -1 : 1); }
  }}>{children}</div><div className="image-reel-navigation"><IconButton aria-label="Scroll images left" disabled={!edges.previous} onClick={() => scroll(-1)}><ChevronLeft size={16} /></IconButton><IconButton aria-label="Scroll images right" disabled={!edges.next} onClick={() => scroll(1)}><ChevronRight size={16} /></IconButton></div></section>;
}
