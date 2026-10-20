import { ApiError } from '../../services/api';
import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '../../services/api';

type Phase = 'idle' | 'permission' | 'recording' | 'processing';
const MAX_SECONDS = 30;
const MAX_BYTES = 4 * 1024 * 1024;

export function useVoiceInput(onText: (text: string) => void, disabled: boolean) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState('');
  const [canRetry, setCanRetry] = useState(false);
  const [levels, setLevels] = useState<number[]>(Array(16).fill(0));
  const callback = useRef(onText); callback.current = onText;
  const resources = useRef<{ recorder?: MediaRecorder; stream?: MediaStream; timer?: ReturnType<typeof setInterval>;
    request?: AbortController; context?: AudioContext; generation: number; blob?: Blob }>({ generation: 0 });

  function release() {
    const current = resources.current;
    clearInterval(current.timer); current.timer = undefined;
    if (current.recorder) {
      current.recorder.onstop = null; current.recorder.ondataavailable = null; current.recorder.onerror = null;
      if (current.recorder.state !== 'inactive') current.recorder.stop();
      current.recorder = undefined;
    }
    current.stream?.getTracks().forEach(track => track.stop()); current.stream = undefined;
    current.request?.abort(); current.request = undefined;
    void current.context?.close().catch(() => {}); current.context = undefined;
  }

  function cancel() {
    resources.current.generation++; release(); resources.current.blob = undefined;
    setPhase('idle'); setError(''); setCanRetry(false); setSeconds(0); setLevels(Array(16).fill(0));
  }

  useEffect(() => () => { resources.current.generation++; release(); resources.current.blob = undefined; }, []);
  useEffect(() => { if (disabled) cancel(); }, [disabled]);

  async function transcribe(blob: Blob, generation: number) {
    if (generation !== resources.current.generation) return;
    resources.current.blob = blob;
    setPhase('processing'); setError(''); setCanRetry(false);
    const request = new AbortController(); resources.current.request = request;
    const timeout = setTimeout(() => request.abort(), 120_000);
    try {
      const { uploadFile } = await import('../../services/files');
      const stored = await uploadFile(blob, 'recording', 'speech', request.signal);
      const result = await apiRequest<{ text: string; language: string }>('/api/v1/speech/transcriptions', {
        method: 'POST', body: JSON.stringify({ file_id: stored.id }), signal: request.signal,
      });
      if (generation !== resources.current.generation) return;
      if (!result.text.trim()) throw new Error('No speech was detected. Please record again.');
      callback.current(result.text);
      resources.current.blob = undefined;
    } catch (failure) {
      if (generation !== resources.current.generation) return;
      setError(request.signal.aborted ? 'Your recording took too long to transcribe.'
        : failure instanceof ApiError ? failure.message : 'Your recording could not be transcribed.');
      setCanRetry(true);
    } finally {
      clearTimeout(timeout);
      if (generation === resources.current.generation) { resources.current.request = undefined; setPhase('idle'); }
    }
  }

  function stop() {
    const current = resources.current;
    clearInterval(current.timer); current.timer = undefined;
    if (current.recorder?.state === 'recording') { setPhase('processing'); current.recorder.stop(); }
  }

  async function start() {
    if (disabled || phase !== 'idle') return;
    cancel();
    const generation = resources.current.generation;
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError('Voice recording is unavailable.'); return;
    }
    setPhase('permission');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (generation !== resources.current.generation) { stream.getTracks().forEach(track => track.stop()); return; }
      resources.current.stream = stream;
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus']
        .find(type => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      resources.current.recorder = recorder;
      const chunks: Blob[] = []; let bytes = 0;
      recorder.ondataavailable = event => {
        bytes += event.data.size;
        if (bytes > MAX_BYTES) { cancel(); setError('This recording is too large.'); return; }
        if (event.data.size) chunks.push(event.data);
      };
      recorder.onerror = () => { cancel(); setError('Your recording could not be completed.'); };
      recorder.onstop = () => {
        clearInterval(resources.current.timer);
        stream.getTracks().forEach(track => track.stop());
        resources.current.stream = undefined; resources.current.recorder = undefined;
        void resources.current.context?.close().catch(() => {}); resources.current.context = undefined;
        const blob = new Blob(chunks, { type: recorder.mimeType || mimeType || 'audio/webm' });
        void transcribe(blob, generation);
      };
      // A disappearing device or interruption must not leave the UI recording indefinitely.
      stream.getAudioTracks().forEach(track => track.onended = stop);
      recorder.start(250);
      setPhase('recording');
      let analyser: AnalyserNode | undefined;
      try {
        const context = new AudioContext(); resources.current.context = context;
        analyser = context.createAnalyser(); analyser.fftSize = 128; analyser.smoothingTimeConstant = 0.7;
        context.createMediaStreamSource(stream).connect(analyser);
        void context.resume().catch(() => {});
      } catch { /* Recording still works when visualization audio is unavailable. */ }
      const started = performance.now();
      resources.current.timer = setInterval(() => {
        if (analyser) {
          const bins = new Uint8Array(analyser.frequencyBinCount); analyser.getByteFrequencyData(bins);
          setLevels(Array.from({ length: 16 }, (_, index) => bins[index + 1] / 255));
        }
        const elapsed = Math.floor((performance.now() - started) / 1000); setSeconds(Math.min(elapsed, MAX_SECONDS));
        if (elapsed >= MAX_SECONDS) stop();
      }, 200);
    } catch (failure) {
      if (generation !== resources.current.generation) return;
      cancel();
      setError(failure instanceof DOMException && failure.name === 'NotAllowedError'
        ? 'Microphone permission was denied.'
        : 'The microphone could not be opened.');
    }
  }

  function retry() {
    const current = resources.current;
    if (!disabled && phase === 'idle' && current.blob) void transcribe(current.blob, ++current.generation);
  }
  return { phase, seconds, levels, error, canRetry, start, stop, cancel, retry, busy: phase !== 'idle' };
}
