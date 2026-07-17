"""Download the recommended Smart-mode LLM from Hugging Face.

The engine's IPC loop is single-threaded, so a 1 GB download runs in a
background thread; the shell polls download_llm_status for progress.
"main" revision means the user always gets the latest published build
of the recommended model.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

RECOMMENDED_REPO = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
RECOMMENDED_FILE = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
_URL = f"https://huggingface.co/{RECOMMENDED_REPO}/resolve/main/{RECOMMENDED_FILE}"

_CHUNK = 1 << 20  # 1 MB


class LlmDownloader:
    def __init__(self, target_dir: Path):
        self.target_dir = Path(target_dir)
        self._lock = threading.Lock()
        self._state = "idle"  # idle | downloading | done | error
        self._pct = 0.0
        self._error: str | None = None
        self._path: str | None = None
        # set by the IPC layer once the finished path is written to config,
        # so the config update happens exactly once and on the IPC thread
        self.applied = False

    def start(self) -> dict:
        with self._lock:
            if self._state == "downloading":
                return {"ok": True, "already": True}
            target = self.target_dir / RECOMMENDED_FILE
            if target.exists() and target.stat().st_size > 0:
                self._state, self._pct, self._path = "done", 100.0, str(target)
                return {"ok": True, "already_downloaded": True}
            self._state, self._pct, self._error, self.applied = "downloading", 0.0, None, False
            threading.Thread(target=self._run, args=(target,), daemon=True).start()
            return {"ok": True}

    def status(self) -> dict:
        with self._lock:
            out = {"state": self._state, "pct": round(self._pct, 1)}
            if self._error:
                out["error"] = self._error
            if self._path:
                out["path"] = self._path
            return out

    def _run(self, target: Path) -> None:
        part = target.with_suffix(target.suffix + ".part")
        try:
            import requests

            self.target_dir.mkdir(parents=True, exist_ok=True)
            with requests.get(_URL, stream=True, timeout=60) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                done = 0
                with open(part, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=_CHUNK):
                        fh.write(chunk)
                        done += len(chunk)
                        if total:
                            with self._lock:
                                self._pct = done * 100.0 / total
            if total and done != total:
                raise IOError(f"incomplete download: {done} of {total} bytes")
            part.replace(target)
            with self._lock:
                self._state, self._pct, self._path = "done", 100.0, str(target)
            log.info("LLM downloaded to %s (%d bytes)", target, done)
        except Exception as exc:
            part.unlink(missing_ok=True)
            with self._lock:
                self._state, self._error = "error", str(exc)
            log.error("LLM download failed: %s", exc)
