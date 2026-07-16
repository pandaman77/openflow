"""Engine configuration: defaults, load/save, per-key overrides.

Config lives in %APPDATA%/OpenFlow/config.json. The Tauri shell owns the
settings UI and pushes changes over IPC; the engine also reads the file
directly on startup so it works standalone (CLI/testing).
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "audio": {
        "device": None,          # None = system default input
        "sample_rate": 16000,
        "channels": 1,
    },
    "vad": {
        "enabled": True,
        "threshold": 0.5,
        "min_silence_ms": 300,
    },
    "stt": {
        "model": "small",        # tiny|base|small|medium|large-v3|large-v3-turbo
        "device": "auto",        # auto|cpu|cuda
        "compute_type": "auto",  # auto -> int8 on cpu, float16 on cuda
        "beam_size": 1,
        "language": None,        # None = auto-detect per utterance
    },
    "cleanup": {
        "mode": "fast",          # fast|smart|literal
        "remove_fillers": True,
        "profile": "auto",       # auto|chat|email|coding|documentation
    },
    "llm": {
        "model_path": None,      # path to GGUF; None -> smart mode falls back to fast
        "context_size": 2048,
        "max_tokens": 512,
        "temperature": 0.1,
    },
    "snippets": {"enabled": True},
    "commands": {"enabled": True},
    "dictionary": {"enabled": True},
}


def config_dir() -> Path:
    base = os.environ.get("OPENFLOW_CONFIG_DIR")
    if base:
        return Path(base)
    appdata = os.environ.get("APPDATA", str(Path.home()))
    return Path(appdata) / "OpenFlow"


class Config:
    def __init__(self, data: dict[str, Any] | None = None):
        self._data = copy.deepcopy(DEFAULTS)
        if data:
            _deep_merge(self._data, data)

    @classmethod
    def load(cls) -> "Config":
        path = config_dir() / "config.json"
        if path.exists():
            try:
                return cls(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass  # corrupt config -> fall back to defaults, don't crash the engine
        return cls()

    def save(self) -> None:
        path = config_dir() / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)


def _deep_merge(dst: dict, src: dict) -> None:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = value
