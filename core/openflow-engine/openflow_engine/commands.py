"""Voice commands: spoken phrases that trigger actions instead of text.

The engine only *detects* commands; execution (undo keystroke, deleting
text in the target app) is the shell's job. Detection result travels back
over IPC as {"type": "command", "action": "...", "args": {...}}.

Built-in actions:
    undo, redo, new_paragraph, new_line, delete_last_sentence,
    bullet_list, select_all
Text-transform commands (rewrite/summarize) are routed to the LLM layer
by the pipeline when smart mode is available.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass
class CommandMatch:
    action: str
    args: dict = field(default_factory=dict)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text.lower().strip())
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


# phrase -> action. Detection requires the utterance to BE the command
# (whole match) so normal dictation containing these words passes through.
_BUILTIN: dict[str, str] = {
    # RU
    "отмена": "undo",
    "отменить": "undo",
    "вернуть": "redo",
    "новый абзац": "new_paragraph",
    "с новой строки": "new_line",
    "новая строка": "new_line",
    "удали последнее предложение": "delete_last_sentence",
    "удалить последнее предложение": "delete_last_sentence",
    "маркированный список": "bullet_list",
    "выделить всё": "select_all",
    "выдели всё": "select_all",
    # EN
    "undo": "undo",
    "redo": "redo",
    "new paragraph": "new_paragraph",
    "new line": "new_line",
    "delete last sentence": "delete_last_sentence",
    "delete previous sentence": "delete_last_sentence",
    "bullet list": "bullet_list",
    "select all": "select_all",
}

# LLM-backed transforms operate on the current selection in the target app.
_TRANSFORMS: dict[str, str] = {
    "перепиши официально": "rewrite_professional",
    "перепиши профессионально": "rewrite_professional",
    "сделай короче": "make_shorter",
    "сделай дружелюбнее": "make_friendlier",
    "суммируй выделенное": "summarize_selection",
    "rewrite professionally": "rewrite_professional",
    "make shorter": "make_shorter",
    "make it shorter": "make_shorter",
    "make friendlier": "make_friendlier",
    "make it friendlier": "make_friendlier",
    "summarize selection": "summarize_selection",
}


class CommandDetector:
    def __init__(self, extra: dict[str, str] | None = None):
        self._phrases: dict[str, CommandMatch] = {}
        for phrase, action in _BUILTIN.items():
            self._phrases[_norm(phrase)] = CommandMatch(action=action)
        for phrase, action in _TRANSFORMS.items():
            self._phrases[_norm(phrase)] = CommandMatch(action=action, args={"llm": True})
        for phrase, action in (extra or {}).items():
            self._phrases[_norm(phrase)] = CommandMatch(action=action)

    def detect(self, text: str) -> CommandMatch | None:
        return self._phrases.get(_norm(text))

    def known_actions(self) -> list[str]:
        return sorted({m.action for m in self._phrases.values()})
