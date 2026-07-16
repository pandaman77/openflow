"""Voice activity detection.

Heavy lifting (Silero VAD) already runs inside faster-whisper via
vad_filter=True, so we don't ship a second model. What we need locally
is a *cheap pre-check*: if the user tapped the hotkey and said nothing,
skip the whole STT call instead of feeding silence to Whisper.
"""

from __future__ import annotations

import numpy as np


def has_speech(audio: np.ndarray, sample_rate: int = 16000,
               rms_threshold: float = 0.004, min_active_ms: int = 120) -> bool:
    """Energy-based check: enough frames above the noise floor to bother Whisper.

    Threshold is deliberately permissive — false positives just cost one
    STT call; false negatives would eat the user's words.
    """
    if audio.size == 0:
        return False
    frame = int(sample_rate * 0.03)
    if audio.size < frame:
        return False
    n_frames = audio.size // frame
    frames = audio[: n_frames * frame].reshape(n_frames, frame)
    rms = np.sqrt(np.mean(frames**2, axis=1))
    active_ms = int(np.count_nonzero(rms > rms_threshold) * 30)
    return active_ms >= min_active_ms
