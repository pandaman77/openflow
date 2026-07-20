"""Translate-to-English mode and the tightened language-drift guard.

Two independent things are covered:
- Whisper `task` is wired from config through the pipeline (no model needed);
- the Smart-cleanup guard tells a real translation from kept technical terms.
"""

import numpy as np
import pytest

from openflow_engine.cleanup.llm import LanguageDriftError, SmartCleaner
from openflow_engine.config import Config
from openflow_engine.language import cyrillic_ratio
from openflow_engine.pipeline import Pipeline
from openflow_engine.stt import TranscriptionResult


# ---------- cyrillic_ratio ----------

class TestCyrillicRatio:
    def test_empty(self):
        assert cyrillic_ratio("") == 0.0

    def test_no_letters(self):
        assert cyrillic_ratio("123 !!! ...") == 0.0

    def test_pure_ru(self):
        assert cyrillic_ratio("привет мир") == 1.0

    def test_pure_en(self):
        assert cyrillic_ratio("hello world") == 0.0

    def test_half(self):
        assert cyrillic_ratio("абв abc") == 0.5


# ---------- language-drift guard ----------

def _cleaner_returning(monkeypatch, output: str) -> SmartCleaner:
    """A SmartCleaner whose LLM call is stubbed to return `output` verbatim,
    so polish() runs its post-processing (labels, length, drift guard) on it."""
    c = SmartCleaner(model_path=None)
    monkeypatch.setattr(c, "_chat", lambda user: output)
    return c


class TestLanguageGuard:
    def test_full_translation_ru_to_en_flagged(self, monkeypatch):
        c = _cleaner_returning(monkeypatch, "we need to call each other tomorrow morning")
        with pytest.raises(LanguageDriftError):
            c.polish("нам надо созвониться завтра утром")

    def test_partial_translation_latin_dominant_flagged(self, monkeypatch):
        # The closed hole: output is "mixed" but Latin dominates — still a
        # translation, must fall back (old guard let "mixed" pass unconditionally).
        c = _cleaner_returning(monkeypatch, "We need to send the письмо")
        with pytest.raises(LanguageDriftError):
            c.polish("нам надо отправить письмо")

    def test_techterms_kept_not_flagged(self, monkeypatch):
        # Legitimate: a Russian sentence keeping a Latin technical term stays
        # Cyrillic-dominant and must NOT be treated as a translation.
        c = _cleaner_returning(monkeypatch, "Сохрани файл в GitHub.")
        assert c.polish("сохрани файл в гитхаб") == "Сохрани файл в GitHub."

    def test_en_to_ru_flagged(self, monkeypatch):
        c = _cleaner_returning(monkeypatch, "отправь отчёт завтра")
        with pytest.raises(LanguageDriftError):
            c.polish("send the report tomorrow")

    def test_ru_to_ru_ok(self, monkeypatch):
        c = _cleaner_returning(monkeypatch, "Созвонимся завтра утром.")
        assert c.polish("эм ну созвонимся завтра утром") == "Созвонимся завтра утром."


# ---------- task wiring: config/flag -> whisper ----------

class _CapturingTranscriber:
    """Stands in for Transcriber: records the `task` it was called with."""

    def __init__(self):
        self.calls: list[str] = []

    def load(self):
        pass

    def transcribe(self, audio, language=None, initial_prompt=None, task="transcribe"):
        self.calls.append(task)
        return TranscriptionResult(
            text="привет мир", language="ru", language_probability=0.99,
            duration_s=1.0, inference_s=0.1, segments=[],
        )


def _speech() -> np.ndarray:
    rng = np.random.default_rng(42)
    return (rng.standard_normal(16000) * 0.1).astype(np.float32)


@pytest.fixture()
def pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENFLOW_CONFIG_DIR", str(tmp_path))
    p = Pipeline(Config())
    p.transcriber = _CapturingTranscriber()
    return p


class TestTranslateTaskWiring:
    def test_default_is_transcribe(self, pipeline):
        pipeline.process_audio(_speech())
        assert pipeline.transcriber.calls == ["transcribe"]

    def test_config_translate_on(self, pipeline):
        pipeline.config.set("stt.translate", True)
        pipeline.process_audio(_speech())
        assert pipeline.transcriber.calls == ["translate"]

    def test_explicit_flag_overrides_config(self, pipeline):
        pipeline.config.set("stt.translate", False)
        pipeline.process_audio(_speech(), translate=True)
        assert pipeline.transcriber.calls == ["translate"]
