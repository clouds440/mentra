import { Camera, ImagePlus } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Dialog } from '../ui/Dialog';
import { Button } from '../ui';

export function ComposerCamera({ onClose, onPhoto }: { onClose: () => void; onPhoto: (file: File) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const fallback = useRef<HTMLInputElement>(null);
  const active = useRef(false);
  const [error, setError] = useState('');
  const [ready, setReady] = useState(false);
  const [capturing, setCapturing] = useState(false);

  useEffect(() => {
    active.current = true;
    let disposed = false;
    let stream: MediaStream | undefined;
    async function start() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
        if (disposed) { stream.getTracks().forEach(track => track.stop()); return; }
        if (video.current) video.current.srcObject = stream;
      } catch {
        if (!disposed) setError('Camera unavailable. Check camera permissions or choose a photo.');
      }
    }
    void start();
    return () => {
      disposed = true; active.current = false;
      stream?.getTracks().forEach(track => track.stop());
    };
  }, []);

  function capture() {
    const source = video.current;
    if (!source?.videoWidth || !source.videoHeight || capturing) return;
    const canvas = document.createElement('canvas');
    const scale = Math.min(1, 1920 / Math.max(source.videoWidth, source.videoHeight));
    canvas.width = Math.max(1, Math.round(source.videoWidth * scale));
    canvas.height = Math.max(1, Math.round(source.videoHeight * scale));
    const context = canvas.getContext('2d');
    if (!context) { setError('Could not capture the photo. Choose a photo instead.'); return; }
    context.drawImage(source, 0, 0, canvas.width, canvas.height);
    setCapturing(true);
    canvas.toBlob(blob => {
      if (!active.current) return;
      if (!blob) { setCapturing(false); setError('Could not capture the photo. Choose a photo instead.'); return; }
      onPhoto(new File([blob], 'Camera photo.jpg', { type: 'image/jpeg' }));
    }, 'image/jpeg', .9);
  }

  return <Dialog open onDismiss={onClose} aria-labelledby="composer-camera-title" className="max-w-lg"
    heading={<h2 id="composer-camera-title" className="text-sm font-semibold">Take a photo</h2>}>
    <video ref={video} autoPlay muted playsInline onLoadedData={() => setReady(true)} aria-label="Camera preview"
      className="aspect-video w-full rounded-control bg-background object-contain" />
    {!ready && !error && <p role="status" className="mt-2 text-xs text-muted">Starting camera…</p>}
    {error && <p role="alert" className="mt-2 text-xs text-danger">{error}</p>}
    <input ref={fallback} type="file" accept="image/*" capture="environment" hidden onChange={event => {
      const file = event.currentTarget.files?.[0];
      if (file) onPhoto(file);
    }} />
    <div className="mt-4 flex flex-wrap justify-end gap-2">
      <Button size="sm" variant="ghost" onClick={() => fallback.current?.click()}><ImagePlus size={15} aria-hidden="true" />Choose photo</Button>
      <Button size="sm" disabled={!ready || capturing} onClick={capture}><Camera size={15} aria-hidden="true" />Capture photo</Button>
    </div>
  </Dialog>;
}
