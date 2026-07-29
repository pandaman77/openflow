"""Progress reporting for the one-time model download.

The first launch pulls ONNX weights from HuggingFace (Parakeet is ~2.4 GB).
Silence during that made the app look broken: the shell gave up on the call
long before the download finished and showed "engine timed out".

huggingface_hub has no progress hook that stays stable across versions, so we
watch its cache instead: it writes `.incomplete` blobs under `blobs/` that grow
as bytes land. The watcher also ticks while nothing is downloading, which is
what tells the shell the engine is working rather than hung.

Nothing here may raise into the caller: a failed watch costs a progress bar,
never the download itself.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

ProgressCallback = Callable[[dict[str, Any]], None]

# Full download size per engine, measured from a warm cache. Only used to turn
# bytes-on-disk into a percentage, so being slightly off is harmless.
DOWNLOAD_SIZES: dict[str, int] = {
    "parakeet": 2_550_000_000,   # nemo-parakeet-tdt-0.6b-v3, ~2.4 GiB
    "gigaam": 890_000_000,       # gigaam-v3-e2e-ctc, ~846 MiB
}

# Fallback for onnx-asr model name -> HuggingFace repo. onnx_asr owns the real
# table; this only covers the engines we ship, in case that import moves.
_FALLBACK_REPOS: dict[str, str] = {
    "nemo-parakeet-tdt-0.6b-v3": "istupakov/parakeet-tdt-0.6b-v3-onnx",
    "gigaam-v3-e2e-ctc": "istupakov/gigaam-v3-onnx",
}


def repo_for_model(model_name: str) -> str | None:
    """HuggingFace repo that holds `model_name`, or None if we can't tell."""
    try:
        from onnx_asr.resolver import model_repos

        found = model_repos.get(model_name)
        if found:
            return found
    except Exception:  # library moved the table; fall back to our own copy
        pass
    return _FALLBACK_REPOS.get(model_name)


def _blobs_dir(repo_id: str) -> Path | None:
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
    except Exception:
        return None
    return Path(HF_HUB_CACHE) / f"models--{repo_id.replace('/', '--')}" / "blobs"


def _live_size(path: Path) -> int:
    """Size of a file that is being written right now.

    Windows serves directory metadata from a cache that can lag behind a
    growing file, so `stat()` may under-report an in-flight blob. Seeking to
    the end of an open handle asks the file system itself.

    (This is not what makes the bar move in steps: huggingface_hub downloads
    through Xet, which buffers roughly 50 MB before appending to the blob.
    Disabling Xet would smooth the bar at the cost of download speed, which is
    a bad trade for the thing we're actually waiting on.)
    """
    try:
        with path.open("rb") as handle:
            return handle.seek(0, 2)
    except OSError:
        try:
            return path.stat().st_size
        except OSError:
            return 0


def downloaded_bytes(repo_id: str) -> int:
    """Bytes on disk for this repo, finished blobs and in-flight ones alike."""
    blobs = _blobs_dir(repo_id)
    if blobs is None or not blobs.is_dir():
        return 0
    total = 0
    try:
        for entry in blobs.iterdir():
            try:
                # Finished blobs never change; only in-flight ones need the
                # slower open-and-seek.
                total += _live_size(entry) if entry.name.endswith(".incomplete") else entry.stat().st_size
            except OSError:
                continue  # blob renamed out from under us mid-scan
    except OSError:
        return 0
    return total


class DownloadWatcher:
    """Ticks progress for a model load until the body finishes.

    Use as a context manager around a blocking `load()`. Every tick carries the
    bytes seen so far; the shell reads it both as a progress bar and as proof
    the engine is alive, so it must keep ticking even when the size is unknown.
    """

    def __init__(
        self,
        engine: str,
        model_name: str | None,
        on_progress: ProgressCallback | None,
        interval: float = 0.7,
    ):
        self.engine = engine
        self.on_progress = on_progress
        self.repo_id = repo_for_model(model_name) if model_name else None
        self.total = DOWNLOAD_SIZES.get(engine)
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _emit(self, done: bool = False) -> None:
        if self.on_progress is None:
            return
        payload: dict[str, Any] = {"engine": self.engine, "done": done}
        if self.repo_id:
            payload["downloaded"] = downloaded_bytes(self.repo_id)
            if self.total:
                payload["total"] = self.total
        try:
            self.on_progress(payload)
        except Exception as exc:  # a broken pipe must not kill the load
            log.debug("progress callback failed: %s", exc)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._emit()

    def __enter__(self) -> "DownloadWatcher":
        if self.on_progress is not None:
            self._emit()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._emit(done=True)


def watch(transcriber: Any, on_progress: ProgressCallback | None) -> DownloadWatcher:
    """Watcher for whatever transcriber is about to load."""
    return DownloadWatcher(
        engine=getattr(transcriber, "engine", "whisper"),
        model_name=getattr(transcriber, "model_name", None),
        on_progress=on_progress,
    )
