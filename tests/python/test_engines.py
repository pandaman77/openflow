"""STT engine selection: factory routing, onnx wrapper, translate -> Whisper.

No model is loaded here — OnnxTranscriber/Transcriber load lazily, and the
translate guard raises before any load, so these stay fast and offline.
"""

import numpy as np
import pytest

from openflow_engine.config import Config
from openflow_engine.pipeline import Pipeline
from openflow_engine.stt import OnnxTranscriber, Transcriber


def _pipe(tmp_path, monkeypatch, engine):
    monkeypatch.setenv("OPENFLOW_CONFIG_DIR", str(tmp_path))
    cfg = Config()
    cfg.set("stt.engine", engine)
    return Pipeline(cfg)


class TestFactory:
    def test_parakeet_builds_onnx(self, tmp_path, monkeypatch):
        p = _pipe(tmp_path, monkeypatch, "parakeet")
        assert isinstance(p.transcriber, OnnxTranscriber)
        assert p.transcriber.engine == "parakeet"

    def test_gigaam_builds_onnx(self, tmp_path, monkeypatch):
        p = _pipe(tmp_path, monkeypatch, "gigaam")
        assert isinstance(p.transcriber, OnnxTranscriber)
        assert p.transcriber.model_name == "gigaam-v3-e2e-ctc"

    def test_whisper_builds_whisper(self, tmp_path, monkeypatch):
        p = _pipe(tmp_path, monkeypatch, "faster-whisper")
        assert isinstance(p.transcriber, Transcriber)

    def test_default_engine_is_parakeet(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENFLOW_CONFIG_DIR", str(tmp_path))
        assert Config().get("stt.engine") == "parakeet"


class TestTranslateRouting:
    def test_translate_forces_whisper_when_engine_is_onnx(self, tmp_path, monkeypatch):
        p = _pipe(tmp_path, monkeypatch, "parakeet")
        assert isinstance(p.transcriber, OnnxTranscriber)
        assert isinstance(p._whisper_for_translate(), Transcriber)

    def test_translate_reuses_main_whisper(self, tmp_path, monkeypatch):
        p = _pipe(tmp_path, monkeypatch, "faster-whisper")
        assert p._whisper_for_translate() is p.transcriber


class TestOnnxTranscriber:
    def test_cannot_translate(self):
        t = OnnxTranscriber("parakeet")
        with pytest.raises(NotImplementedError):
            t.transcribe(np.zeros(16000, dtype="float32"), task="translate")

    def test_unknown_engine_rejected(self):
        with pytest.raises(ValueError):
            OnnxTranscriber("bogus")


class TestReload:
    def test_no_change_no_reload(self, tmp_path, monkeypatch):
        p = _pipe(tmp_path, monkeypatch, "parakeet")
        assert p.reload_stt()["reloaded"] is False

    def test_engine_change_reloads(self, tmp_path, monkeypatch):
        p = _pipe(tmp_path, monkeypatch, "parakeet")
        # don't actually load models on switch
        monkeypatch.setattr(OnnxTranscriber, "load", lambda self: None)
        monkeypatch.setattr(Transcriber, "load", lambda self: None)
        p.config.set("stt.engine", "faster-whisper")
        res = p.reload_stt()
        assert res["reloaded"] is True
        assert isinstance(p.transcriber, Transcriber)
