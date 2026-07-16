"""JSON-RPC 2.0 over stdio — the contract between the Tauri shell and this engine.

One JSON object per line (NDJSON). Requests from the shell:

    initialize        {} -> {version, stt_device, smart_available, devices}
    start_recording   {device?} -> {ok}
    stop_recording    {active_app?} -> PipelineResult  (the big one)
    cancel_recording  {} -> {ok}
    get_level         {} -> {level}            # overlay waveform polling
    process_text      {text, active_app?} -> PipelineResult   # testing/re-run
    transform_text    {text, action} -> {text}
    list_devices      {} -> {devices}
    get_config / set_config / reload_user_data
    shutdown          {} -> {ok}

Errors follow JSON-RPC: {"error": {"code": ..., "message": ...}}.
Progress notifications (no id) may be emitted for long model loads.
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from dataclasses import asdict
from typing import Any, Callable

from . import __version__
from .audio import Recorder, list_devices
from .config import Config
from .pipeline import Pipeline

log = logging.getLogger(__name__)


class IpcServer:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()
        self.pipeline = Pipeline(self.config)
        self.recorder: Recorder | None = None
        self._running = True
        self._handlers: dict[str, Callable[[dict], Any]] = {
            "initialize": self._initialize,
            "start_recording": self._start_recording,
            "stop_recording": self._stop_recording,
            "cancel_recording": self._cancel_recording,
            "get_level": self._get_level,
            "process_text": self._process_text,
            "transform_text": self._transform_text,
            "list_devices": lambda p: {"devices": list_devices()},
            "get_config": lambda p: self.config.as_dict(),
            "set_config": self._set_config,
            "reload_user_data": self._reload_user_data,
            "shutdown": self._shutdown,
        }

    # --- handlers -----------------------------------------------------

    def _initialize(self, params: dict) -> dict:
        info = self.pipeline.warmup()
        log.info("warmup done: %s", info)
        try:
            devices = list_devices()
            log.info("audio devices: %d", len(devices))
        except Exception as exc:  # a broken audio stack must not block startup
            log.error("list_devices failed: %s", exc)
            devices = []
        return {"version": __version__, **info, "devices": devices}

    def _start_recording(self, params: dict) -> dict:
        if self.recorder and self.recorder.recording:
            return {"ok": True, "already": True}
        device = params.get("device", self.config.get("audio.device"))
        self.recorder = Recorder(device=device)
        self.recorder.start()
        return {"ok": True}

    def _stop_recording(self, params: dict) -> dict:
        if not self.recorder or not self.recorder.recording:
            return {"type": "empty", "reason": "not_recording"}
        audio = self.recorder.stop()
        result = self.pipeline.process_audio(audio, active_app=params.get("active_app"))
        return asdict(result)

    def _cancel_recording(self, params: dict) -> dict:
        if self.recorder and self.recorder.recording:
            self.recorder.stop()
        return {"ok": True}

    def _get_level(self, params: dict) -> dict:
        level = self.recorder.level() if self.recorder and self.recorder.recording else 0.0
        return {"level": level}

    def _process_text(self, params: dict) -> dict:
        result = self.pipeline.process_text(
            params.get("text", ""), active_app=params.get("active_app"))
        return asdict(result)

    def _transform_text(self, params: dict) -> dict:
        return {"text": self.pipeline.transform_text(
            params.get("text", ""), params.get("action", ""))}

    def _set_config(self, params: dict) -> dict:
        for key, value in params.items():
            self.config.set(key, value)
        self.config.save()
        return {"ok": True}

    def _reload_user_data(self, params: dict) -> dict:
        self.pipeline.snippets.reload()
        self.pipeline.dictionary.reload()
        return {"ok": True}

    def _shutdown(self, params: dict) -> dict:
        self._running = False
        return {"ok": True}

    # --- transport ----------------------------------------------------

    def handle_line(self, line: str) -> str | None:
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            return json.dumps({"jsonrpc": "2.0", "id": None,
                               "error": {"code": -32700, "message": "parse error"}})
        req_id = req.get("id")
        method = req.get("method", "")
        handler = self._handlers.get(method)
        if handler is None:
            return json.dumps({"jsonrpc": "2.0", "id": req_id,
                               "error": {"code": -32601, "message": f"unknown method {method!r}"}})
        try:
            log.info("-> %s (id=%s)", method, req_id)
            result = handler(req.get("params") or {})
            log.info("<- %s (id=%s) ok", method, req_id)
            return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result},
                              ensure_ascii=False)
        except Exception as exc:
            log.error("handler %s failed: %s\n%s", method, exc, traceback.format_exc())
            return json.dumps({"jsonrpc": "2.0", "id": req_id,
                               "error": {"code": -32000, "message": str(exc)}})

    def serve_forever(self) -> None:
        """Blocking loop over stdin/stdout. Logs go to stderr, protocol to stdout."""
        stdin = sys.stdin
        stdout = sys.stdout
        while self._running:
            line = stdin.readline()
            if not line:  # shell closed the pipe -> exit
                break
            line = line.strip()
            if not line:
                continue
            response = self.handle_line(line)
            if response is not None:
                stdout.write(response + "\n")
                stdout.flush()
