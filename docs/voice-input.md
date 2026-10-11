# Voice input

Implemented on 11 October 2026. Voice is an alternative way to fill the existing chat draft. It never sends a message automatically.

## Composer

The microphone sits immediately left of Send. During recording the text field shows one compact microphone-reactive waveform line, a timer, and Cancel. The mic becomes Stop. The original draft is preserved and the transcript is appended when processing finishes. The user reviews/edits it and uses the existing Send action. `dir="auto"` handles Urdu and Arabic text. There is no new page, conversation flow, language picker, or displayed duration limit. Language detection is always automatic.

Recording stops automatically at 30 seconds. This bounds CPU latency, decoded memory, and the time other users can be denied access to the single worker. The server independently enforces decoded duration and a 4 MiB upload limit. Up to 250 ms of codec padding is accepted and trimmed before inference. The 30-second cap is a practical resource policy, not a model restriction.

Cancellation aborts the client request and invalidates its generation. Navigation, logout/composer unmount, and disabled chat state clean up microphone tracks, recorder handlers, visualization AudioContext, timers and pending requests. Late responses cannot populate another chat. A failed upload/transcription can retry the in-memory recording; Cancel/Dismiss or a new recording discards it. Browser microphone access requires HTTPS or localhost and MediaRecorder. WebM/Opus, MP4/AAC and Ogg/Opus are negotiated; actual physical iOS/Safari and Android testing remains outstanding.

## Backend and model

`POST /api/v1/speech/transcriptions` accepts multipart `audio` using the existing session authentication and cookie-origin checks. It returns `text`, `language`, `language_probability`, `duration_seconds` and `processing_seconds`, with no-store caching. A submitted language field does not override automatic detection.

The route reads a bounded upload and calls the service in the thread pool. A transport middleware bounds both declared and chunked body sizes before multipart parsing/spooling. PyAV validates recognizable self-contained container signatures and incrementally converts audio to mono 16 kHz float PCM. Arbitrary playlists/URLs are not accepted. There are no application-owned audio temporary files; Starlette's transient upload spool is closed in `finally`. Audio and transcripts are not written to a database or logs.

Default engine: faster-whisper 1.2.1, **Whisper Base multilingual**, CTranslate2 CPU INT8, two inference threads, beam size three, deterministic transcription rather than translation. No GPU/CUDA dependency is needed. Base is the practical latency/memory baseline; Tiny trades capacity for a smaller footprint, while Small has more capacity at a greater CPU/memory cost. Only multilingual Tiny/Base/Small model names are allowed. Tiny and Small have not been benchmarked in this implementation. See [faster-whisper documentation](https://github.com/SYSTRAN/faster-whisper) and [Whisper model documentation](https://github.com/openai/whisper#available-models-and-languages).

One persistent spawned worker holds the model per API process. Startup can warm it; requests reuse it. Native decoding/inference occurs outside the ASGI process. Concurrent transcription requests fail promptly with `SPEECH_BUSY` (429), with no unbounded queue. A 20-second service deadline terminates a stuck worker and a later request can create a replacement. Normal shutdown exits the worker gracefully. Client cancellation prevents publication but does not instantly interrupt an already running shared-worker operation; that operation remains bounded by the server deadline. Use one Uvicorn worker on modest hosting to avoid replicating model memory; each additional API process gets its own speech worker.

VAD identifies paused utterances before transcription. Each utterance detects its own language, so a paused switch to English does not suppress the earlier Urdu/Arabic utterance. Short spans are combined, and at most four regions are decoded to bound CPU work. All languages supported by the installed multilingual model are accepted without a language allowlist or forced fallback. The reported probability is the original detector probability, not an artificially normalized confidence; `language` describes the longest detected speech region, not every language in a mixed message.

## Measured results

Hardware: AMD Ryzen 5 5600X, six physical cores / twelve logical CPUs, Docker Desktop WSL2. Final engine benchmark: Python 3.12 container, **two CPU quota, 768 MiB container limit**, two inference threads, INT8, beam three, warmed Base model, three runs per sample. Latency below includes audio decoding, VAD, detection and fully consumed transcription, excluding HTTP upload and process startup. RTF = elapsed processing time / original audio duration. These measurements do not predict performance on a slower shared production host.

| Sample | Audio seconds | Median processing seconds | Median RTF |
| --- | ---: | ---: | ---: |
| Urdu, FLEURS test ID 1930 | 6.240 | 1.878 | 0.301 |
| Urdu, FLEURS test ID 1806 | 12.240 | 2.120 | 0.173 |
| Arabic, FLEURS test ID 1993 | 8.160 | 1.680 | 0.206 |
| Arabic, FLEURS test ID 1730 | 14.160 | 2.031 | 0.143 |
| English, LibriSpeech 1272-128104-0000 | 5.855 | 1.499 | 0.256 |
| English, LibriSpeech 1272-128104-0001 | 4.815 | 1.402 | 0.291 |

Model initialization took 1.216 seconds; approximate RSS increase during model load was 147.7 MiB. Maximum **sampled speech-process RSS** across these runs was 237.6 MiB; this is not total backend/container memory or an instrumented instantaneous peak. Existing LLM/RAG/backend resources are additional.

Public recordings came from [Google FLEURS](https://huggingface.co/datasets/google/fleurs) (`ur_pk`, `ar_eg`, test split) and the [LibriSpeech test fixture](https://huggingface.co/datasets/hf-internal-testing/librispeech_asr_dummy) (`clean`, validation). No private student recording was used. The initial single-pass Base implementation dropped an entire language in two constructed mixed clips. After pause-aware detection, both source utterances appeared in order, retaining Urdu/Arabic script and English text. On native Windows, the constructed 12.295-second Urdu-English clip took 2.812 seconds (RTF 0.229), and the 14.215-second Arabic-English clip took 2.724 seconds (RTF 0.192). These are concatenations of different public speakers, **not natural conversational code-switching** or an accuracy benchmark.

Recognition observations: English transcripts matched the sample wording aside from normal casing/punctuation and “Mister” → “Mr.” Urdu and Arabic retained their scripts after the supported-language fallback, but had substantial spelling/substitution errors and incorrect numbers/names. Lightweight recognition quality is not established as production-ready for natural Pakistani code-switching, scientific terms, accents, noisy rooms, or short commands. No reliable WER/CER claim is made. Natural student recordings and a consented reference set are still needed. Within-sentence switching can still lose or transliterate English terminology. Small is configurable for a measured quality comparison if Base proves inadequate; it should not be assumed to solve these issues or meet the same latency target.

## Setup and reproduction

The backend Dockerfile provisions the model before enabling offline Hugging Face mode. Compose forwards `SPEECH_MODEL` as a build argument; rebuild after changing it so the model files and configured size agree. The updated images were deployed locally on 11 October 2026: backend/frontend health checks passed, all three workers restarted using the rebuilt backend image, and offline Urdu inference passed in the deployed image. The full backend build stalled downloading unchanged PyTorch dependencies; this local rollout reused the previously validated CPU dependency image and copied the current source plus verified speech model into a fresh image. The normal Dockerfile remains the full-build path.

For local Python, install `backend/requirements.txt`, then provision once in a network-enabled shell:

```powershell
$env:SPEECH_MODEL = 'base'
$env:SPEECH_MODEL_PATH = "$PWD/data/speech/base"
./.venv/Scripts/python.exe backend/bake_speech_model.py
```

Set `SPEECH_MODEL_PATH` to that same absolute directory for the backend. Requests use `local_files_only=True` and never download models. `SPEECH_WARM_ON_STARTUP=false` permits lazy first-request loading. Missing/corrupt model files return a clean 503 and do not break typed chat.

The benchmark requires `psutil` only as a developer tool, not a production dependency. Supply a UTF-8 manifest containing local paths and optional references, e.g. `[{"path":"sample.wav","reference":"spoken text"}]`:

```powershell
$env:PYTHONPATH = 'backend'
$env:PYTHONIOENCODING = 'utf-8'
./.venv/Scripts/python.exe backend/scripts/benchmark_speech.py manifest.json --model-path data/speech/base --threads 2 --repeats 3
./.venv/Scripts/python.exe -m testing.speech_real manifest.json --model-path data/speech/base
./.venv/Scripts/python.exe -m unittest tests.test_speech tests.test_chat_endpoint -v
cd frontend
npx playwright test --config playwright.voice.config.ts
npm run build
npm run check:theme
```

`--language-hints` is a benchmark-only diagnostic comparison. Product requests remain automatic. Raw benchmark JSONL and public samples used here are in ignored local `data/speech/`; model weights/audio are not committed.

## Files and verification

- Backend feature: `app/speech/{engine,service,upload_limit}.py`, package initializer, `app/api/routes/speech.py`.
- Backend integration: `app/api/router.py`, `app/main.py`, `app/core/config.py`, `requirements.txt`, `Dockerfile`, `bake_speech_model.py`.
- Frontend: `ChatComposer.tsx`, `useVoiceInput.ts`, `VoiceInput.tsx`.
- Configuration/docs: `.env.example`, `docker-compose.yml`, this report.
- Verification tooling: `tests/test_speech.py`, `testing/speech_real.py`, `scripts/benchmark_speech.py`; frontend `playwright.voice.config.ts`, `tests/voice.spec.ts` and standalone test harness. The harness is a development test fixture, not a production route/page or user flow.

Verified production frontend build and semantic theme checks; **16 backend/chat tests and five browser cases passed**. Browser checks exercise the real composer with mocked MediaRecorder/HTTP at 390 px and 1280 px: microphone placement, no selector/limit text, draft append/review/edit/send, RTL direction, permission denial, cancellation, retry, navigation/late-response suppression, responsive width, and automatic stop. API/service tests cover authentication/origin checks, no-store responses, chunked/declared/file size limits, invalid audio, silence, duration and codec padding, actual PyAV WebM/Opus + Ogg/Opus + MP4/AAC decoding, original scripts/transcription mode, pause ordering, unrestricted automatic detection, worker reuse, busy rejection, timeout and recovery. Existing chat endpoint tests remain unchanged and pass. Six additional opt-in HTTP checks use the real spawned worker and Base model with public audio in Python 3.12. Physical-device browser and natural educational/code-switching accuracy validation remain outstanding.

Language coverage now follows the installed Whisper multilingual model. Removing the former English/Urdu/Arabic restriction adds no model weights; accuracy and decoding time still vary by language and recording. Earlier Urdu benchmark observations used a forced supported-language fallback and do not establish accuracy after its removal.
