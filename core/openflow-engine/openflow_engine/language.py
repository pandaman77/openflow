"""Language handling for RU/EN and mixed dictation.

Whisper auto-detects the dominant language per utterance and transcribes
mixed speech surprisingly well ("Открой Cursor и создай React component").
This module adds:
- script-based sanity check on the *output* text (cheap, no model);
- a sticky hint: if the user consistently dictates in one language,
  pass it explicitly to skip Whisper's detection pass (saves latency).
"""

from __future__ import annotations

import re
from collections import deque

_CYRILLIC_RE = re.compile(r"[а-яё]", re.IGNORECASE)
_LATIN_RE = re.compile(r"[a-z]", re.IGNORECASE)


def detect_script(text: str) -> str:
    """Return 'ru', 'en' or 'mixed' based on characters actually present."""
    has_cyr = bool(_CYRILLIC_RE.search(text))
    has_lat = bool(_LATIN_RE.search(text))
    if has_cyr and has_lat:
        return "mixed"
    if has_cyr:
        return "ru"
    if has_lat:
        return "en"
    return "unknown"


class LanguageTracker:
    """Remembers recent utterance languages to provide a hint for the next one."""

    def __init__(self, window: int = 5):
        self._recent: deque[str] = deque(maxlen=window)

    def observe(self, language: str, probability: float) -> None:
        if probability >= 0.8:
            self._recent.append(language)

    def hint(self) -> str | None:
        """Explicit language if the recent window is unanimous, else None (auto)."""
        if len(self._recent) == self._recent.maxlen and len(set(self._recent)) == 1:
            return self._recent[0]
        return None

    def reset(self) -> None:
        self._recent.clear()
