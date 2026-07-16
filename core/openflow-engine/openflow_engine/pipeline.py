"""The dictation pipeline: everything between raw audio and final text.

Order of operations after STT:
1. command detection  — whole utterance is a command? return action, no text
2. dictionary         — fix known mis-hearings
3. snippets           — expand trigger phrases
4. cleanup            — literal / fast / smart (with fallback to fast)

Snippet expansion runs BEFORE cleanup so an expanded URL/address isn't
"polished" by the LLM; if the whole utterance was a snippet trigger the
expansion is returned verbatim.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .commands import CommandDetector
from .config import Config
from .cleanup.llm import SmartCleaner
from .cleanup.profiles import Profile, profile_for_app
from .cleanup.rules import fast_cleanup, literal_cleanup
from .dictionary import PersonalDictionary
from .language import LanguageTracker
from .snippets import SnippetStore
from .stt import Transcriber
from .vad import has_speech

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    type: str                    # "text" | "command" | "empty"
    text: str = ""
    action: str | None = None
    args: dict = field(default_factory=dict)
    language: str | None = None
    timings: dict[str, float] = field(default_factory=dict)


class Pipeline:
    def __init__(self, config: Config):
        self.config = config
        self.transcriber = self._build_transcriber()
        self.snippets = SnippetStore()
        self.commands = CommandDetector()
        self.dictionary = PersonalDictionary()
        self.lang_tracker = LanguageTracker()
        self.smart = SmartCleaner(
            model_path=config.get("llm.model_path"),
            context_size=config.get("llm.context_size"),
            max_tokens=config.get("llm.max_tokens"),
            temperature=config.get("llm.temperature"),
        )

    def _build_transcriber(self) -> Transcriber:
        return Transcriber(
            model_name=self.config.get("stt.model"),
            device=self.config.get("stt.device"),
            compute_type=self.config.get("stt.compute_type"),
            beam_size=self.config.get("stt.beam_size"),
        )

    def warmup(self) -> dict[str, Any]:
        """Load the STT model up-front so the first dictation isn't slow."""
        self.transcriber.load()
        return {"stt_device": self.transcriber.resolved_device,
                "smart_available": self.smart.available()}

    def reload_stt(self) -> dict[str, Any]:
        """Swap in a fresh transcriber after the model/device config changed.
        The old model was resident; without this a model switch has no effect."""
        old = (self.transcriber.model_name, self.transcriber.device,
               self.transcriber.compute_type, self.transcriber.beam_size)
        new = (self.config.get("stt.model"), self.config.get("stt.device"),
               self.config.get("stt.compute_type"), self.config.get("stt.beam_size"))
        if old == new:
            return {"reloaded": False}
        log.info("stt config changed %s -> %s, reloading", old, new)
        self.transcriber = self._build_transcriber()
        self.transcriber.load()
        return {"reloaded": True, "stt_device": self.transcriber.resolved_device}

    def process_audio(self, audio: np.ndarray, active_app: str | None = None) -> PipelineResult:
        timings: dict[str, float] = {}
        if not has_speech(audio):
            return PipelineResult(type="empty", timings=timings)

        t0 = time.perf_counter()
        lang_cfg = self.config.get("stt.language")
        result = self.transcriber.transcribe(
            audio,
            language=lang_cfg or self.lang_tracker.hint(),
            initial_prompt=self.dictionary.initial_prompt()
            if self.config.get("dictionary.enabled") else None,
        )
        timings["stt"] = time.perf_counter() - t0
        self.lang_tracker.observe(result.language, result.language_probability)

        return self.process_text(
            result.text, active_app=active_app,
            language=result.language, timings=timings,
        )

    def process_text(
        self,
        raw_text: str,
        active_app: str | None = None,
        language: str | None = None,
        timings: dict[str, float] | None = None,
    ) -> PipelineResult:
        """Text half of the pipeline — separately callable for tests and re-processing."""
        timings = timings if timings is not None else {}
        text = raw_text.strip()
        if not text:
            return PipelineResult(type="empty", timings=timings)

        if self.config.get("commands.enabled"):
            match = self.commands.detect(text)
            if match:
                return PipelineResult(
                    type="command", action=match.action, args=match.args,
                    language=language, timings=timings,
                )

        if self.config.get("dictionary.enabled"):
            text = self.dictionary.apply_replacements(text)

        snippet_expanded = False
        if self.config.get("snippets.enabled"):
            expanded = self.snippets.expand(text)
            snippet_expanded = expanded != text
            text = expanded

        t0 = time.perf_counter()
        profile = profile_for_app(active_app, self.config.get("cleanup.app_profiles"))
        text = self._cleanup(text, profile, skip=snippet_expanded)
        timings["cleanup"] = time.perf_counter() - t0

        return PipelineResult(type="text", text=text, language=language, timings=timings)

    def _cleanup(self, text: str, profile: Profile, skip: bool = False) -> str:
        if skip:
            return text  # snippet expansions are inserted verbatim
        mode = self.config.get("cleanup.mode")
        if mode == "literal":
            return literal_cleanup(text)
        if mode == "smart" and self.smart.available():
            try:
                return self.smart.polish(text, profile_hint=profile.llm_hint)
            except Exception as exc:
                log.warning("smart cleanup failed, falling back to fast: %s", exc)
        fast = fast_cleanup(text, remove_fillers_enabled=(
            self.config.get("cleanup.remove_fillers") and profile.remove_fillers))
        if not profile.ensure_punctuation and fast.endswith(".") and not text.rstrip().endswith("."):
            fast = fast[:-1]  # chat/coding: don't force a period the user didn't dictate
        return fast

    def transform_text(self, text: str, action: str) -> str:
        """LLM transforms (rewrite/summarize) on selection text sent by the shell."""
        if self.smart.available():
            try:
                return self.smart.transform(text, action)
            except Exception as exc:
                log.warning("transform %s failed: %s", action, exc)
        return text
