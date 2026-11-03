# Current transcription transport and device policy

This supplement supersedes the transport/device portions of [voice-input.md](voice-input.md) as of 2026-11-03. The older guide and its measurements are retained as historical evidence. See the [system acceptance report](../system/System_Audit_Implementation_2026-11-03.md) for tests, raw measurements and limitations.

| Contract | Current behavior |
| --- | --- |
| Browser voice input | `POST /api/v1/speech/transcriptions/direct`, authenticated multipart `file` plus UUID `operation_id`. Reuse the operation ID for retrying the same recording. Existing draft text survives errors and cancellation. |
| Transient audio | Request bytes go directly to a killable local speech worker. No Files upload, verification download or transcription download. Only the bounded result receipt and request hash persist; audio bytes do not. |
| Replay | Owner/content-bound result retained for 24 hours. Repeating the same operation/content returns its result. Different owner/content conflicts; active work returns busy; failed inference releases its claim for retry. |
| Limits | Dedicated upload-byte limit, supported self-contained container validation and bounded decoded duration. Startup, pipe send/receive and transcription share the operation deadline. Native upload validation for the legacy route is isolated too. |
| Legacy compatibility | `POST /api/v1/speech/transcriptions` with an owned speech file ID remains supported; this path still uses private storage. |
| Model quality | Whisper Base, CPU INT8, beam 3, two threads remain the defaults. Automatic language handling and upstream Silero segmentation are preserved. |
| Device choice | `LOCAL_INFERENCE_DEVICE=auto` probes CTranslate2 and ONNX separately. `cpu` forces CPU; `cuda` prefers supported CUDA and still falls back to CPU. Compatible packages/drivers must already be installed. |
| Mid-execution loss | Rebuild on CPU once, discard partial lazy output, preserve the original deadline. Supervision can also recover a native child exit. CPU selection remains sticky until worker restart. No domain writes run inside the inference retry callback. |

The final paired CPU benchmark removed three private-storage operations and retained exact transcript equality on a public English clip. Median 4.3529 s became 4.2850 s in five alternating paired trials with memory storage and zero added network delay (1.6% observed reduction; the earlier run observed 3.2%). These small samples do not establish a general latency gain or multilingual speech accuracy. CPU inference still dominates. Physical CUDA loss was simulated, not physically exercised. Model/beam/concurrency changes require separate quality and performance evidence before adoption.
