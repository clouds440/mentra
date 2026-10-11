from io import BytesIO
from typing import Protocol

from app.core.exceptions import AppError


class SpeechEngine(Protocol):
    def transcribe(self, data: bytes, language: str | None) -> dict: ...


def _container_format(data: bytes) -> str:
    # Only decode self-contained audio containers, never playlists or external URLs.
    if data.startswith(b'\x1aE\xdf\xa3'): return 'matroska'
    if data.startswith(b'OggS'): return 'ogg'
    if data.startswith(b'RIFF') and data[8:12] == b'WAVE': return 'wav'
    if data.startswith(b'fLaC'): return 'flac'
    if data[4:8] == b'ftyp': return 'mov'
    if data.startswith(b'ID3'): return 'mp3'
    if len(data) >= 2 and data[0] == 255 and data[1] & 0xf6 == 0xf0: return 'aac'
    if len(data) >= 2 and data[0] == 255 and data[1] & 0xe0 == 0xe0: return 'mp3'
    raise AppError('SPEECH_AUDIO_INVALID', 'This recording could not be read. Record it again.', 422)


def decode_audio(data: bytes, maximum_seconds: int):
    """Decode incrementally to bounded mono 16 kHz PCM; ignore untrusted metadata."""
    import av
    import numpy as np

    chunks, samples = [], 0
    # Browser codecs can add a small trailing packet past the recorder stop time.
    sample_limit = int((maximum_seconds + 0.25) * 16000)
    try:
        with av.open(BytesIO(data), format=_container_format(data)) as container:
            if not container.streams.audio:
                raise ValueError('No audio stream')
            resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
            for frame in container.decode(audio=0):
                # Bound both source frames and resampled samples before inference.
                if frame.sample_rate > 192000 or len(frame.layout.channels) > 2:
                    raise ValueError('Unsupported audio configuration')
                if frame.samples / frame.sample_rate > maximum_seconds:
                    raise AppError('SPEECH_DURATION', f'Record no more than {maximum_seconds} seconds.', 422)
                for output in resampler.resample(frame):
                    samples += output.samples
                    if samples > sample_limit:
                        raise AppError('SPEECH_DURATION', f'Record no more than {maximum_seconds} seconds.', 422)
                    chunks.append(output.to_ndarray().reshape(-1))
            for output in resampler.resample(None):
                samples += output.samples
                if samples > sample_limit:
                    raise AppError('SPEECH_DURATION', f'Record no more than {maximum_seconds} seconds.', 422)
                chunks.append(output.to_ndarray().reshape(-1))
    except AppError:
        raise
    except Exception:
        raise AppError('SPEECH_AUDIO_INVALID', 'This recording could not be read. Record it again.', 422) from None
    if samples < 1600:
        raise AppError('SPEECH_AUDIO_EMPTY', 'The recording is too short. Please try again.', 422)
    return np.concatenate(chunks)[:maximum_seconds * 16000].astype(np.float32) / 32768.0


class FasterWhisperEngine:
    def __init__(self, config: dict):
        self.config = config
        self.model = None

    def warm(self):
        if self.model is None:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(
                self.config['model_path'] or self.config['model'], device='cpu', compute_type='int8',
                cpu_threads=self.config['threads'], num_workers=1, local_files_only=True,
            )

    def transcribe(self, data: bytes, language: str | None) -> dict:
        from time import perf_counter
        started = perf_counter()
        audio = decode_audio(data, self.config['max_seconds'])
        regions = speech_regions(audio)
        if not regions:
            raise AppError('SPEECH_NO_SPEECH', 'No speech was detected. Please record again.', 422)
        self.warm()
        results = [(end-start, self._transcribe_region(audio[start:end], language)) for start, end in regions]
        text = ' '.join(result['text'] for _, result in results if result['text']).strip()
        if not text:
            raise AppError('SPEECH_NO_SPEECH', 'No speech was detected. Please record again.', 422)
        dominant = max(results, key=lambda item: item[0])[1]
        return dict(text=text, language=dominant['language'], language_probability=dominant['language_probability'],
                    duration_seconds=len(audio) / 16000, processing_seconds=perf_counter() - started)

    def _transcribe_region(self, audio, language):
        segments, info = self.model.transcribe(
            audio, task='transcribe', language=language, beam_size=self.config['beam_size'],
            temperature=0, condition_on_previous_text=False, vad_filter=False,
        )
        probability = info.language_probability
        text = ''.join(segment.text for segment in segments).strip()
        return dict(text=text, language=info.language, language_probability=probability)


def speech_regions(audio):
    """Detect at pauses so a language change does not suppress an entire utterance.

    Bound detection/decoding passes to four; merge short spans to avoid fragile
    sub-second language detection. This does not solve code-switching inside a sentence.
    """
    from faster_whisper.vad import get_speech_timestamps, VadOptions
    spans = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=500, speech_pad_ms=200))
    regions = []
    for span in spans:
        if regions and regions[-1][1] - regions[-1][0] < 2 * 16000:
            regions[-1] = (regions[-1][0], span['end'])
        else:
            regions.append((span['start'], span['end']))
    while len(regions) > 4:
        index = min(range(len(regions)-1), key=lambda i: regions[i+1][0]-regions[i][1])
        regions[index:index+2] = [(regions[index][0], regions[index+1][1])]
    return regions
