"""Voice snippets: spoken trigger phrase -> expanded text.

Snippets are stored as JSON in the config dir (snippets.json):
    [{"trigger": "мой календарь", "text": "https://cal.com/kolya", "folder": "links"},
     {"trigger": "my address", "text": "Moscow, ...", "folder": "personal"}]

Matching is whole-utterance and fuzzy to punctuation/case: a dictated
"Мой календарь." must expand even though STT added a period. Triggers
embedded inside longer sentences are also replaced inline.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from .config import config_dir


def _norm(text: str) -> str:
    """Lowercase, strip punctuation and extra spaces for trigger comparison."""
    text = unicodedata.normalize("NFC", text.lower().strip())
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


class SnippetStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (config_dir() / "snippets.json")
        self._snippets: list[dict] = []
        self._by_trigger: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        self._snippets = []
        if self.path.exists():
            try:
                self._snippets = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._snippets = []
        self._by_trigger = {_norm(s["trigger"]): s["text"] for s in self._snippets if s.get("trigger")}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._snippets, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def add(self, trigger: str, text: str, folder: str = "") -> None:
        self._snippets = [s for s in self._snippets if _norm(s.get("trigger", "")) != _norm(trigger)]
        self._snippets.append({"trigger": trigger, "text": text, "folder": folder})
        self._by_trigger[_norm(trigger)] = text

    def remove(self, trigger: str) -> bool:
        key = _norm(trigger)
        before = len(self._snippets)
        self._snippets = [s for s in self._snippets if _norm(s.get("trigger", "")) != key]
        self._by_trigger.pop(key, None)
        return len(self._snippets) < before

    def list(self) -> list[dict]:
        return list(self._snippets)

    def expand(self, text: str) -> str:
        """Whole-utterance match first, then inline occurrences."""
        if not self._by_trigger:
            return text
        whole = self._by_trigger.get(_norm(text))
        if whole is not None:
            return whole
        result = text
        # longest triggers first so "рабочая почта москва" wins over "рабочая почта"
        for trigger in sorted(self._by_trigger, key=len, reverse=True):
            pattern = r"(?<!\w)" + r"[\s,]+".join(map(re.escape, trigger.split())) + r"(?!\w)"
            result = re.sub(pattern, lambda _: self._by_trigger[trigger], result, flags=re.IGNORECASE)
        return result
