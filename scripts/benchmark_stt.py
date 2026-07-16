"""STT benchmark: models x devices on a reference audio file.

    python scripts/benchmark_stt.py --audio tests/fixtures/ru_sample.wav
    python scripts/benchmark_stt.py --models tiny,base,small --devices cpu

Reports load time, inference time, RTF (real-time factor: inference/audio,
lower is better, <1.0 = faster than realtime) and the transcription itself
so accuracy can be eyeballed against the reference text.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "openflow-engine"))


def bench(model_name: str, device: str, audio_path: str, beam_size: int) -> dict:
    from faster_whisper import WhisperModel

    compute_type = "float16" if device == "cuda" else "int8"
    t0 = time.perf_counter()
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception as exc:
        return {"model": model_name, "device": device, "error": str(exc)}
    load_s = time.perf_counter() - t0

    # first pass warms caches; second pass is the honest measurement
    results = []
    for _ in range(2):
        t0 = time.perf_counter()
        segments, info = model.transcribe(audio_path, beam_size=beam_size, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments)
        results.append((time.perf_counter() - t0, text, info))
    inference_s, text, info = results[-1]

    return {
        "model": model_name,
        "device": device,
        "compute_type": compute_type,
        "load_s": round(load_s, 2),
        "inference_s": round(inference_s, 2),
        "audio_s": round(info.duration, 2),
        "rtf": round(inference_s / info.duration, 3),
        "language": info.language,
        "text": text,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", default="tests/fixtures/ru_sample.wav")
    parser.add_argument("--models", default="tiny,base,small")
    parser.add_argument("--devices", default="cpu")
    parser.add_argument("--beam-size", type=int, default=1)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    rows = []
    for device in args.devices.split(","):
        for model in args.models.split(","):
            print(f"benchmarking {model} on {device}...", file=sys.stderr)
            rows.append(bench(model, device, args.audio, args.beam_size))

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print(f"\n{'model':<18}{'device':<8}{'load,s':<8}{'infer,s':<9}{'RTF':<7}text")
    for r in rows:
        if "error" in r:
            print(f"{r['model']:<18}{r['device']:<8}ERROR: {r['error'][:60]}")
        else:
            print(f"{r['model']:<18}{r['device']:<8}{r['load_s']:<8}{r['inference_s']:<9}{r['rtf']:<7}{r['text'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
