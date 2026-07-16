"""Smart cleanup: local LLM polishing via llama.cpp (llama-cpp-python).

Fully optional. If llama-cpp-python isn't installed or no GGUF model is
configured, available() returns False and the pipeline silently uses the
fast rule-based pass instead — dictation must never break because a
1 GB model file is missing.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


class LanguageDriftError(Exception):
    """LLM translated the text instead of cleaning it; caller should fall back."""

    def __init__(self, script_in: str, script_out: str):
        super().__init__(f"language drift {script_in} -> {script_out}")

# Small instruct models (0.5-3B) ignore system-prompt rules but reliably
# continue a demonstrated pattern, so polishing is prompted as a completion
# template with RU+EN few-shot pairs in a single user message.
_POLISH_INSTRUCTION = (
    "Edit dictated text: remove filler words and false starts, fix punctuation "
    "and capitalization, keep the meaning, keep technical terms, and NEVER "
    "translate — reply in the same language as the text. Reply ONLY with the result."
)

_FEW_SHOT: list[tuple[str, str]] = [
    (
        "эм ну вот короче нам надо надо созвониться завтра утром",
        "Нам надо созвониться завтра утром.",
    ),
    (
        "um so basically I think we should uh ship it on Friday",
        "I think we should ship it on Friday.",
    ),
]


def _polish_prompt(text: str, style_hint: str | None = None) -> str:
    parts = [_POLISH_INSTRUCTION]
    if style_hint:
        parts.append(f"Style context: {style_hint}.")
    parts.append("")
    for example_in, example_out in _FEW_SHOT:
        parts.append(f"Text: {example_in}")
        parts.append(f"Result: {example_out}")
        parts.append("")
    parts.append(f"Text: {text}")
    parts.append("Result:")
    return "\n".join(parts)

_TRANSFORM_PROMPTS = {
    "rewrite_professional": "Rewrite the text in a professional, formal tone. Keep the language.",
    "make_shorter": "Rewrite the text to be significantly shorter while keeping the meaning. Keep the language.",
    "make_friendlier": "Rewrite the text in a friendlier, warmer tone. Keep the language.",
    "summarize_selection": "Summarize the text in 2-3 sentences. Keep the language.",
}


class SmartCleaner:
    def __init__(self, model_path: str | None, context_size: int = 2048,
                 max_tokens: int = 512, temperature: float = 0.1):
        self.model_path = model_path
        self.context_size = context_size
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._llm = None
        self._load_failed = False

    def available(self) -> bool:
        if self._load_failed:
            return False
        if not self.model_path or not Path(self.model_path).exists():
            return False
        try:
            import llama_cpp  # noqa: F401
        except ImportError:
            return False
        return True

    def _ensure_loaded(self):
        if self._llm is not None:
            return
        from llama_cpp import Llama

        try:
            self._llm = Llama(
                model_path=self.model_path,
                n_ctx=self.context_size,
                n_gpu_layers=-1,  # offload all if built with GPU support, no-op on CPU builds
                verbose=False,
            )
        except Exception as exc:
            self._load_failed = True
            log.error("Failed to load LLM %s: %s", self.model_path, exc)
            raise

    def _chat(self, user: str, system: str | None = None) -> str:
        self._ensure_loaded()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        out = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return out["choices"][0]["message"]["content"].strip()

    def polish(self, text: str, profile_hint: str | None = None) -> str:
        result = self._chat(_polish_prompt(text, profile_hint))
        # models sometimes echo the template labels — strip them
        for label in ("Result:", "Результат:", "Text:", "Текст:"):
            if result.startswith(label):
                result = result[len(label):].strip()
        # Guard against a chatty model: if output ballooned, distrust it.
        if not result or len(result) > max(len(text) * 2, len(text) + 200):
            log.warning("LLM output suspicious (len %d vs %d), keeping input", len(result), len(text))
            return text
        # Language guard: a small model must never silently translate.
        from ..language import detect_script

        script_in, script_out = detect_script(text), detect_script(result)
        if script_in in ("ru", "en") and script_out not in (script_in, "mixed", "unknown"):
            log.warning("LLM changed language %s -> %s, falling back", script_in, script_out)
            raise LanguageDriftError(script_in, script_out)
        return result

    def transform(self, text: str, action: str) -> str:
        prompt = _TRANSFORM_PROMPTS.get(action)
        if not prompt:
            return text
        return self._chat(f"{prompt} Output ONLY the result.\n\nText: {text}")
