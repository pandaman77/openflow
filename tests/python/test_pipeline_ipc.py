"""Pipeline text-path and IPC protocol tests (no model, no microphone)."""

import json

import numpy as np
import pytest

from openflow_engine.config import Config
from openflow_engine.language import LanguageTracker, detect_script
from openflow_engine.pipeline import Pipeline
from openflow_engine.vad import has_speech


@pytest.fixture()
def pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENFLOW_CONFIG_DIR", str(tmp_path))
    config = Config()
    config.set("cleanup.mode", "fast")
    return Pipeline(config)


class TestPipelineText:
    def test_dictation(self, pipeline):
        res = pipeline.process_text("эм ну вот проект готов")
        assert res.type == "text"
        assert res.text == "Проект готов."

    def test_command(self, pipeline):
        res = pipeline.process_text("новый абзац")
        assert res.type == "command"
        assert res.action == "new_paragraph"

    def test_empty(self, pipeline):
        assert pipeline.process_text("").type == "empty"

    def test_snippet_returned_verbatim(self, pipeline):
        pipeline.snippets.add("мой сайт", "https://sharapov.pro")
        res = pipeline.process_text("мой сайт")
        # cleanup must NOT capitalize or add period to expanded snippet
        assert res.text == "https://sharapov.pro"

    def test_dictionary_applied_before_cleanup(self, pipeline):
        pipeline.dictionary.add_replacement("опен флоу", "OpenFlow")
        res = pipeline.process_text("я делаю опен флоу сегодня")
        assert "OpenFlow" in res.text

    def test_coding_profile_no_forced_period(self, pipeline):
        res = pipeline.process_text("npm install tauri", active_app="Code.exe")
        assert res.type == "text"
        assert not res.text.endswith(".")

    def test_smart_mode_falls_back_without_model(self, pipeline):
        pipeline.config.set("cleanup.mode", "smart")
        res = pipeline.process_text("эм проект готов")
        assert res.type == "text"
        assert res.text == "Проект готов."  # fast fallback did the job


class TestVadAndLanguage:
    def test_silence_rejected(self):
        assert has_speech(np.zeros(16000, dtype=np.float32)) is False

    def test_speech_like_signal_accepted(self):
        rng = np.random.default_rng(42)
        signal = (rng.standard_normal(16000) * 0.1).astype(np.float32)
        assert has_speech(signal) is True

    def test_empty_buffer(self):
        assert has_speech(np.zeros(0, dtype=np.float32)) is False

    def test_detect_script(self):
        assert detect_script("привет мир") == "ru"
        assert detect_script("hello world") == "en"
        assert detect_script("открой Cursor и создай component") == "mixed"

    def test_tracker_hint_only_when_unanimous(self):
        t = LanguageTracker(window=3)
        assert t.hint() is None
        for _ in range(3):
            t.observe("ru", 0.95)
        assert t.hint() == "ru"
        t.observe("en", 0.95)
        assert t.hint() is None  # window no longer unanimous


class TestIpc:
    @pytest.fixture()
    def server(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENFLOW_CONFIG_DIR", str(tmp_path))
        from openflow_engine.ipc import IpcServer
        return IpcServer(Config())

    def _call(self, server, method, params=None, req_id=1):
        line = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method,
                           "params": params or {}})
        return json.loads(server.handle_line(line))

    def test_process_text_roundtrip(self, server):
        resp = self._call(server, "process_text", {"text": "эм привет мир"})
        assert resp["result"]["type"] == "text"
        assert resp["result"]["text"] == "Привет мир."

    def test_unknown_method(self, server):
        resp = self._call(server, "no_such_method")
        assert resp["error"]["code"] == -32601

    def test_parse_error(self, server):
        resp = json.loads(server.handle_line("{broken json"))
        assert resp["error"]["code"] == -32700

    def test_get_set_config(self, server):
        resp = self._call(server, "set_config", {"cleanup.mode": "literal"})
        assert resp["result"]["ok"] is True
        resp = self._call(server, "get_config")
        assert resp["result"]["cleanup"]["mode"] == "literal"

    def test_stop_without_start(self, server):
        resp = self._call(server, "stop_recording")
        assert resp["result"]["type"] == "empty"

    def test_shutdown(self, server):
        resp = self._call(server, "shutdown")
        assert resp["result"]["ok"] is True
        assert server._running is False
