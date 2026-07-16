"""Download STT/LLM models listed in models/manifest.json.

    python scripts/download_models.py --list
    python scripts/download_models.py --stt small
    python scripts/download_models.py --llm qwen2.5-1.5b-instruct-q4

STT models go to the standard HuggingFace cache (faster-whisper finds them
there by name). LLM GGUF files go to models/llm/ and the path is printed —
put it into config llm.model_path (the app's onboarding does this itself).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "models" / "manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--stt", metavar="ID")
    parser.add_argument("--llm", metavar="ID")
    args = parser.parse_args()
    manifest = load_manifest()

    if args.list or (not args.stt and not args.llm):
        for kind in ("stt", "llm"):
            print(f"\n{kind.upper()} models:")
            for m in manifest[kind]:
                print(f"  {m['id']:32s} {m['size_mb']:>6} MB  {m['note']}")
        return 0

    if args.stt:
        entry = next((m for m in manifest["stt"] if m["id"] == args.stt), None)
        if not entry:
            print(f"unknown stt model {args.stt!r}", file=sys.stderr)
            return 1
        from huggingface_hub import snapshot_download

        path = snapshot_download(entry["hf_repo"])
        print(f"downloaded {entry['id']} -> {path}")

    if args.llm:
        entry = next((m for m in manifest["llm"] if m["id"] == args.llm), None)
        if not entry:
            print(f"unknown llm model {args.llm!r}", file=sys.stderr)
            return 1
        from huggingface_hub import hf_hub_download

        target_dir = ROOT / "models" / "llm"
        target_dir.mkdir(parents=True, exist_ok=True)
        path = hf_hub_download(
            entry["hf_repo"], entry["hf_file"], local_dir=target_dir)
        print(f"downloaded {entry['id']} -> {path}")
        print(f'set config: {{"llm.model_path": "{path}"}}')

    return 0


if __name__ == "__main__":
    sys.exit(main())
