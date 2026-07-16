"""Fast rule-based cleanup: fillers, spacing, capitalization, terminal punctuation.

Whisper already produces decent punctuation; this pass removes speech
artifacts it keeps (fillers, duplicated words) and normalizes the result.
Designed to add near-zero latency, so: regex only, no models.
"""

from __future__ import annotations

import re

# Speech fillers. Word-boundary matched, case-insensitive.
# Kept conservative: only words that are near-always noise in dictation.
_FILLERS_RU = [
    r"э+м*",      # э, ээ, эм, эмм
    r"а+м+",      # ам, амм (не трогаем одиночное "а" — это союз)
    r"ну\s+вот",
    r"как\s+бы",
    r"это\s+самое",
    r"короче\s+говоря",
]
_FILLERS_EN = [
    r"u+h+m*",    # uh, uhh, uhm
    r"u+m+",      # um, umm
    r"e+r+m*",    # er, erm
    r"you\s+know",
    r"i\s+mean",
    r"kind\s+of\s+like",
]

_FILLER_RE = re.compile(
    r"(?<![\w-])(?:" + "|".join(_FILLERS_RU + _FILLERS_EN) + r")(?![\w-])[,.]?\s*",
    re.IGNORECASE | re.UNICODE,
)

# "слово, слово" / "word word" immediate duplicates (stutter artifacts).
# Only comma or space as separator: a period usually means an intentional repeat.
_DUP_WORD_RE = re.compile(r"(?<![\w-])([\w'-]+),?\s+\1(?![\w-])", re.IGNORECASE | re.UNICODE)

_SENT_END = (".", "!", "?", "…", ":", ";")


def remove_fillers(text: str) -> str:
    return _FILLER_RE.sub("", text)


def collapse_duplicates(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = _DUP_WORD_RE.sub(r"\1", text)
        text = re.sub(r"([\w'-]+)\s+\1([,.!?])", r"\1\2", text, flags=re.IGNORECASE)
    # collapse the separator the removed duplicate left behind ("слово, ." etc.)
    text = re.sub(r",\s+([.!?])", r"\1", text)
    return text


def normalize_spacing(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([,.!?;:…])", r"\1", text)
    text = re.sub(r"([,.!?;:])(?=[^\s.!?…\d])", r"\1 ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def capitalize_sentences(text: str) -> str:
    if not text:
        return text
    chars = list(text)
    capitalize_next = True
    for i, ch in enumerate(chars):
        if capitalize_next and ch.isalpha():
            chars[i] = ch.upper()
            capitalize_next = False
        elif ch in ".!?…":
            capitalize_next = True
        elif ch == "\n":
            capitalize_next = True
    return "".join(chars)


def ensure_terminal_punctuation(text: str) -> str:
    if text and text[-1] not in _SENT_END and text[-1] not in (",", "-"):
        return text + "."
    return text


# Words that, at the start of a sentence, make it a question. Whisper 'small'
# often hears the question but writes a period; this restores the '?'.
_QUESTION_STARTERS_RU = {
    "кто", "что", "чё", "где", "когда", "куда", "откуда", "почему", "зачем",
    "как", "какой", "какая", "какое", "какие", "каких", "каким", "чей", "чья",
    "чьё", "сколько", "разве", "неужели", "можно", "ли",
}
_QUESTION_STARTERS_EN = {
    "who", "what", "where", "when", "why", "how", "which", "whose", "whom",
    "is", "are", "am", "was", "were", "do", "does", "did", "can", "could",
    "will", "would", "should", "shall", "may", "might", "have", "has", "had",
}
_SENTENCE_SPLIT_RE = re.compile(r"([.!?…]+)")
_LI_PARTICLE_RE = re.compile(r"(?<!\w)ли(?!\w)", re.IGNORECASE | re.UNICODE)


def _looks_like_question(sentence: str) -> bool:
    words = re.findall(r"[\w'-]+", sentence.lower(), re.UNICODE)
    if not words:
        return False
    first = words[0]
    if first in _QUESTION_STARTERS_RU or first in _QUESTION_STARTERS_EN:
        return True
    # Russian yes/no questions carry the particle "ли": "пойдёшь ли ты"
    return bool(_LI_PARTICLE_RE.search(sentence))


def restore_question_marks(text: str) -> str:
    """Turn a trailing '.' into '?' for sentences that read as questions."""
    parts = _SENTENCE_SPLIT_RE.split(text)
    out = []
    for i in range(0, len(parts), 2):
        sentence = parts[i]
        terminator = parts[i + 1] if i + 1 < len(parts) else ""
        if terminator in (".", "") and _looks_like_question(sentence):
            terminator = "?" if terminator == "." else terminator
            if terminator == "" and sentence.strip():
                terminator = "?"
        out.append(sentence + terminator)
    return "".join(out)


def fast_cleanup(text: str, remove_fillers_enabled: bool = True) -> str:
    """Full fast pass. Order matters: fillers -> dups -> spacing -> caps -> punct."""
    if not text or not text.strip():
        return ""
    result = text.strip()
    if remove_fillers_enabled:
        result = remove_fillers(result)
    result = collapse_duplicates(result)
    result = normalize_spacing(result)
    result = capitalize_sentences(result)
    result = ensure_terminal_punctuation(result)
    result = restore_question_marks(result)
    return result


def literal_cleanup(text: str) -> str:
    """Literal mode: only trim and fix whitespace, keep everything the user said."""
    return normalize_spacing(text) if text else ""
