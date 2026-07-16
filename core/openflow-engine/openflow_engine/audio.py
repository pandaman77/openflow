"""Microphone capture: 16 kHz mono float32, push-to-talk friendly.

start() begins buffering immediately (recording must start <150 ms after
the hotkey), stop() returns the whole utterance as one numpy array for
the transcriber. Device switching = stop + new Recorder with device id.
"""

from __future__ import annotations

import logging
import re
import threading

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000


_DRIVER_NOISE_RE = re.compile(r"@System32\\[^;]*;%1[^;]*%0\s*;?", re.IGNORECASE)


def _clean_device_name(name: str) -> str:
    """Windows exposes some devices as '... (@System32\\drivers\\...;(Real Name))'.
    Strip the driver path so only the human-readable part remains."""
    name = _DRIVER_NOISE_RE.sub("", name)
    # collapse the '(( ... ))' left behind and trim
    name = re.sub(r"\(\s*\(", "(", name)
    name = re.sub(r"\)\s*\)", ")", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name


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
                    "name": _clean_device_name(dev["name"]),
                    "default": idx == default_input,
                    "sample_rate": dev.get("default_samplerate"),
                }
            )
    return devices


def _resample(audio: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    """Linear resample to the STT rate. Good enough for speech; no scipy dep."""
    if sr_from == sr_to or audio.size == 0:
        return audio.astype(np.float32)
    n = int(round(audio.size * sr_to / sr_from))
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    x_old = np.linspace(0.0, 1.0, audio.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


class Recorder:
    def __init__(self, device: int | None = None, sample_rate: int = SAMPLE_RATE):
        self.device = device
        self.sample_rate = sample_rate
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()
        self._capture_sr = sample_rate
        self.recording = False

    def start(self) -> None:
        import sounddevice as sd

        if self.recording:
            return
        self._chunks = []

        # The stored device id can drift (reorder) to a non-input device;
        # fall back to the system default input rather than crashing.
        if self.device is not None:
            try:
                if int(sd.query_devices(self.device).get("max_input_channels", 0)) < 1:
                    log.warning("device %s is not an input, using default", self.device)
                    self.device = None
            except Exception as exc:
                log.warning("device %s invalid (%s), using default", self.device, exc)
                self.device = None

        # Bluetooth headsets and pro sound cards don't all accept mono@16 kHz.
        # Open at the device's own rate/channels and downmix+resample later.
        info = sd.query_devices(self.device, "input")
        native_sr = int(info.get("default_samplerate") or self.sample_rate)
        max_ch = int(info.get("max_input_channels") or 1)

        # Try a few configs, most-preferred first; keep the one that opens.
        candidates = [
            (self.sample_rate, 1),
            (native_sr, 1),
            (native_sr, min(2, max_ch)),
            (native_sr, max_ch),
        ]
        last_err: Exception | None = None
        for sr, ch in candidates:
            if ch < 1:
                continue
            try:
                self._open_stream(sd, sr, ch)
                self._capture_sr = sr
                self.recording = True
                log.info("mic opened at %d Hz, %d ch (device native %d Hz)", sr, ch, native_sr)
                return
            except Exception as exc:  # portaudio -9998 etc — try the next config
                last_err = exc
                log.warning("mic config %d Hz/%d ch failed: %s", sr, ch, exc)
        raise RuntimeError(f"could not open microphone: {last_err}")

    def _open_stream(self, sd, sr: int, ch: int) -> None:
        def callback(indata, frames, time_info, status):
            if status:
                log.warning("audio status: %s", status)
            # downmix any channel count to mono
            mono = indata[:, 0] if indata.shape[1] == 1 else indata.mean(axis=1)
            with self._lock:
                self._chunks.append(mono.astype(np.float32).copy())

        self._stream = sd.InputStream(
            device=self.device,
            samplerate=sr,
            channels=ch,
            dtype="float32",
            blocksize=int(sr * 0.03),
            callback=callback,
        )
        self._stream.start()

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
        return _resample(audio, self._capture_sr, self.sample_rate)

    def level(self) -> float:
        """Current RMS level 0..1 of the last chunk — feeds the overlay waveform."""
        with self._lock:
            if not self._chunks:
                return 0.0
            chunk = self._chunks[-1]
        return float(np.sqrt(np.mean(chunk**2)))
