"""Microphone capture: 16 kHz mono float32, push-to-talk friendly.

start() begins buffering immediately (recording must start <150 ms after
the hotkey), stop() returns the whole utterance as one numpy array for
the transcriber. Device switching = stop + new Recorder with device id.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000


def list_devices() -> list[dict]:
    import sounddevice as sd

    devices = []
    default_input = None
    try:
        default_input = sd.default.device[0]
    except Exception:
        pass
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0:
            devices.append(
                {
                    "id": idx,
                    "name": dev["name"],
                    "default": idx == default_input,
                    "sample_rate": dev.get("default_samplerate"),
                }
            )
    return devices


class Recorder:
    def __init__(self, device: int | None = None, sample_rate: int = SAMPLE_RATE):
        self.device = device
        self.sample_rate = sample_rate
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()
        self.recording = False

    def start(self) -> None:
        import sounddevice as sd

        if self.recording:
            return
        self._chunks = []

        def callback(indata, frames, time_info, status):
            if status:
                log.warning("audio status: %s", status)
            with self._lock:
                self._chunks.append(indata[:, 0].copy())

        self._stream = sd.InputStream(
            device=self.device,
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=int(self.sample_rate * 0.03),  # 30 ms blocks
            callback=callback,
        )
        self._stream.start()
        self.recording = True

    def stop(self) -> np.ndarray:
        if not self.recording:
            return np.zeros(0, dtype=np.float32)
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self.recording = False
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            audio = np.concatenate(self._chunks)
            self._chunks = []
        return audio

    def level(self) -> float:
        """Current RMS level 0..1 of the last chunk — feeds the overlay waveform."""
        with self._lock:
            if not self._chunks:
                return 0.0
            chunk = self._chunks[-1]
        return float(np.sqrt(np.mean(chunk**2)))
