"""Entry point.

    python -m openflow_engine                  # serve JSON-RPC on stdio (sidecar mode)
    python -m openflow_engine --selftest       # offline pipeline check, no model needed
    python -m openflow_engine --transcribe f.wav   # one-shot file transcription
    python -m openflow_engine --mic 5          # record 5s from mic and transcribe
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time


def main() -> int:
    # The IPC protocol is UTF-8. Without this, Python picks the ANSI code
    # page (cp1251 on Russian Windows) for pipes and Cyrillic device names
    # arrive as invalid UTF-8 on the shell side.
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    parser = argparse.ArgumentParser(prog="openflow-engine")
    parser.add_argument("--selftest", action="store_true", help="run offline text-pipeline check")
    parser.add_argument("--transcribe", metavar="FILE", help="transcribe an audio file and exit")
    parser.add_argument("--mic", type=float, metavar="SECONDS", help="record from mic, transcribe, exit")
    parser.add_argument("--mode", choices=["fast", "smart", "literal"], help="cleanup mode override")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,  # stdout is reserved for the IPC protocol
    )

    from .config import Config
    config = Config.load()
    if args.mode:
        config.set("cleanup.mode", args.mode)

    if args.selftest:
        return _selftest(config)

    from .pipeline import Pipeline

    if args.transcribe:
        pipeline = Pipeline(config)
        t0 = time.perf_counter()
        result = pipeline.transcriber.transcribe(args.transcribe)
        processed = pipeline.process_text(result.text, language=result.language)
        print(json.dumps({
            "raw": result.text,
            "final": processed.text if processed.type == "text" else f"<{processed.type}:{processed.action}>",
            "language": result.language,
            "language_probability": round(result.language_probability, 3),
            "audio_s": round(result.duration_s, 2),
            "inference_s": round(result.inference_s, 2),
            "total_s": round(time.perf_counter() - t0, 2),
            "device": pipeline.transcriber.resolved_device,
        }, ensure_ascii=False, indent=2))
        return 0

    if args.mic:
        from .audio import Recorder
        pipeline = Pipeline(config)
        pipeline.warmup()
        rec = Recorder(device=config.get("audio.device"))
        print(f"Recording {args.mic}s — speak now...", file=sys.stderr)
        rec.start()
        time.sleep(args.mic)
        audio = rec.stop()
        result = pipeline.process_audio(audio)
        print(json.dumps({
            "type": result.type, "text": result.text, "action": result.action,
            "language": result.language, "timings": result.timings,
        }, ensure_ascii=False, indent=2))
        return 0

    # default: sidecar mode
    from .ipc import IpcServer
    IpcServer(config).serve_forever()
    return 0


def _selftest(config) -> int:
    """Text-pipeline check that needs no model and no microphone."""
    from .pipeline import Pipeline

    config.set("cleanup.mode", "fast")
    pipeline = Pipeline(config)
    cases = [
        ("эм ну вот я хочу сказать что что проект готов", "text"),
        ("um so I think think the project is ready", "text"),
        ("новый абзац", "command"),
        ("delete last sentence", "command"),
        ("", "empty"),
    ]
    failed = 0
    for raw, expected_type in cases:
        res = pipeline.process_text(raw)
        ok = res.type == expected_type
        # filler words must actually be gone
        if ok and res.type == "text":
            lowered = res.text.lower()
            ok = not any(f in lowered.split() for f in ("эм", "um", "ну"))
        status = "OK " if ok else "FAIL"
        failed += 0 if ok else 1
        print(f"[{status}] {raw!r} -> {res.type}: {res.text or res.action!r}")
    print("selftest:", "PASSED" if failed == 0 else f"FAILED ({failed})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
