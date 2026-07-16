"""Personal dictionary: user vocabulary that STT tends to butcher.

Two mechanisms:
1. Words are joined into Whisper's initial_prompt so the model is biased
   toward them during decoding (names, brands, jargon).
2. Post-replacements fix stable mis-hearings: {"wrong": "битрикс", "right": "Bitrix24"}.

Stored in dictionary.json in the config dir:
    {"words": ["Bitrix24", "Гусар", "fondvera"],
     "replacements": [{"wrong": "битрикс 24", "right": "Bitrix24"}]}
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import config_dir


class PersonalDictionary:
    def __init__(self, path: Path | None = None):
        self.path = path or (config_dir() / "dictionary.json")
        self.words: list[str] = []
        self.replacements: list[dict] = []
        self.reload()

    def reload(self) -> None:
        self.words = []
        self.replacements = []
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.words = list(data.get("words", []))
                self.replacements = list(data.get("replacements", []))
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {"words": self.words, "replacements": self.replacements},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def add_word(self, word: str) -> None:
        if word and word not in self.words:
            self.words.append(word)

    def add_replacement(self, wrong: str, right: str) -> None:
        self.replacements = [r for r in self.replacements if r.get("wrong", "").lower() != wrong.lower()]
        self.replacements.append({"wrong": wrong, "right": right})

    def initial_prompt(self, limit: int = 40) -> str | None:
        """Vocabulary hint for Whisper. Kept short — long prompts hurt latency."""
        if not self.words:
            return None
        return ", ".join(self.words[:limit])

    def apply_replacements(self, text: str) -> str:
        for rep in self.replacements:
            wrong, right = rep.get("wrong"), rep.get("right")
            if not wrong or right is None:
                continue
            pattern = r"(?<!\w)" + re.escape(wrong) + r"(?!\w)"
            text = re.sub(pattern, right, text, flags=re.IGNORECASE)
        return text
