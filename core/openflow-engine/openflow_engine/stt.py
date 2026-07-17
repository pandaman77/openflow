"""Speech-to-text via faster-whisper (CTranslate2).

Device selection: "auto" tries CUDA and falls back to CPU int8, so the
same build works on a GPU desktop and a CPU-only laptop. The model is
loaded lazily on first use and kept resident for the process lifetime.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


def _enable_nvidia_dlls() -> None:
    """Make pip-installed CUDA runtime DLLs (nvidia-cublas-cu12, nvidia-cudnn-cu12)
    loadable on Windows. Strictly best-effort: this must NEVER break loading —
    frozen (PyInstaller) bundles can expose phantom namespace paths."""
    if os.name != "nt":
        return
    try:
        import nvidia

        # `nvidia` is a namespace package: no __file__, iterate __path__ roots
        for base in getattr(nvidia, "__path__", []):
            base_path = Path(base)
            if not base_path.is_dir():
                continue
            for pkg_dir in base_path.iterdir():
                bin_dir = pkg_dir / "bin"
                if bin_dir.is_dir():
                    os.add_dll_directory(str(bin_dir))
                    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
    except Exception as exc:  # noqa: BLE001 — optional speedup, never fatal
        log.debug("nvidia DLL setup skipped: %s", exc)


def _join_segments(texts: list[str]) -> str:
    """Join whisper segments, restoring dots the model swallowed.

    Segment boundaries are real speech pauses. Small models (especially on
    Russian) often start the next segment capitalized but leave the previous
    one without terminal punctuation — "прав доступа Мне кажется". If a
    segment ends in a letter/digit and the next one starts uppercase, the
    dot was dropped, so put it back. A sentence merely split mid-flow
    continues lowercase and is left untouched.
    """
    parts = [t.strip() for t in texts]
    parts = [p for p in parts if p]
    out = []
    for i, part in enumerate(parts):
        nxt = parts[i + 1] if i + 1 < len(parts) else None
        if nxt and part[-1].isalnum() and nxt[0].isupper():
            part += "."
        out.append(part)
    return " ".join(out).strip()


@dataclass
class TranscriptionResult:
    text: str
    language: str
    language_probability: float
    duration_s: float
    inference_s: float
    segments: list[dict] = field(default_factory=list)


class Transcriber:
    def __init__(
        self,
        model_name: str = "small",
        device: str = "auto",
        compute_type: str = "auto",
        beam_size: int = 1,
    ):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self._model = None
        self.resolved_device: str | None = None

    def load(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        _enable_nvidia_dlls()

        attempts: list[tuple[str, str]] = []
        if self.device == "auto":
            if self.compute_type == "auto":
                # float16 needs Volta+; int8 covers Pascal cards (GTX 10xx)
                attempts = [("cuda", "float16"), ("cuda", "int8"), ("cpu", "int8")]
            else:
                attempts = [("cuda", self.compute_type), ("cpu", self.compute_type)]
        else:
            ct = self.compute_type
            if ct == "auto":
                ct = "float16" if self.device == "cuda" else "int8"
            attempts = [(self.device, ct)]

        last_err: Exception | None = None
        for device, compute_type in attempts:
            try:
                t0 = time.perf_counter()
                self._model = WhisperModel(self.model_name, device=device, compute_type=compute_type)
                self.resolved_device = device
                log.info(
                    "Loaded whisper '%s' on %s/%s in %.1fs",
                    self.model_name, device, compute_type, time.perf_counter() - t0,
                )
                return
            except Exception as exc:  # CUDA missing/driver issues -> try next
                last_err = exc
                log.warning("Failed to load on %s/%s: %s", device, compute_type, exc)
        raise RuntimeError(f"Could not load whisper model '{self.model_name}': {last_err}")

    def transcribe(
        self,
        audio: "np.ndarray | str",
        language: str | None = None,
        initial_prompt: str | None = None,
    ) -> TranscriptionResult:
        """audio: float32 mono 16 kHz numpy array, or a path to an audio file."""
        self.load()
        t0 = time.perf_counter()
        segments_iter, info = self._model.transcribe(
            audio,
            language=language,
            beam_size=self.beam_size,
            initial_prompt=initial_prompt,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
        )
        segments = [
            {"start": s.start, "end": s.end, "text": s.text}
            for s in segments_iter
        ]
        inference_s = time.perf_counter() - t0
        text = _join_segments([s["text"] for s in segments])
        return TranscriptionResult(
            text=text,
            language=info.language,
            language_probability=info.language_probability,
            duration_s=info.duration,
            inference_s=inference_s,
            segments=segments,
        )
