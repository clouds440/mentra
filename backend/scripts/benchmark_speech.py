"""Run with PYTHONPATH=backend; install psutil only for this benchmark tool.

Manifest JSON: [{"path":"recording.wav", "language":"ur", "reference":"..."}]
Human review of script/terms/code-switching is required; references are reported, not rewritten.
"""
import argparse
import json
import os
import platform
from pathlib import Path
from time import perf_counter

import psutil
from app.speech.engine import FasterWhisperEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--model', choices=['tiny', 'base', 'small'], default='base')
    parser.add_argument('--model-path', default='')
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--beam-size', type=int, default=3)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--language-hints', action='store_true', help='Diagnostic comparison; product input always auto-detects')
    args = parser.parse_args()
    engine = FasterWhisperEngine(dict(model=args.model, model_path=args.model_path, threads=args.threads,
                                      beam_size=args.beam_size, max_seconds=30))
    process = psutil.Process()
    before = process.memory_info().rss
    started = perf_counter(); engine.warm()
    print(json.dumps(dict(model=args.model, compute='CPU INT8', threads=args.threads, beam_size=args.beam_size,
                          cpu=platform.processor(), logical_cpus=os.cpu_count(), platform=platform.platform(),
                          load_seconds=perf_counter()-started, model_rss_delta_mb=(process.memory_info().rss-before)/2**20)))
    for sample in json.loads(args.manifest.read_text(encoding='utf-8')):
        data = (args.manifest.parent / sample['path']).read_bytes()
        for run in range(args.repeats):
            started = perf_counter()
            result = engine.transcribe(data, sample.get('language') if args.language_hints else None)
            elapsed = perf_counter()-started
            print(json.dumps(dict(sample=sample['path'], run=run+1, **result, wall_seconds=elapsed,
                                  real_time_factor=elapsed/result['duration_seconds'], rss_mb=process.memory_info().rss/2**20,
                                  expected_language=sample.get('language'), reference=sample.get('reference')), ensure_ascii=False))


if __name__ == '__main__':
    main()
