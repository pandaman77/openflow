"""Context profiles: the active application decides the writing style.

The shell reports the focused window's process name over IPC; we map it
to a profile that tunes cleanup behaviour. Users can override/extend the
mapping in config (cleanup.app_profiles).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    name: str
    llm_hint: str          # appended to the smart-cleanup system prompt
    remove_fillers: bool   # fast-pass behaviour
    ensure_punctuation: bool


PROFILES: dict[str, Profile] = {
    "coding": Profile(
        "coding",
        "code editor; preserve identifiers, syntax, file paths exactly; no prose embellishment",
        remove_fillers=True,
        ensure_punctuation=False,
    ),
    "email": Profile(
        "email",
        "business email; full sentences, correct grammar, polite tone",
        remove_fillers=True,
        ensure_punctuation=True,
    ),
    "chat": Profile(
        "chat",
        "instant messaging; informal tone is fine, keep it natural and short",
        remove_fillers=True,
        ensure_punctuation=False,
    ),
    "documentation": Profile(
        "documentation",
        "technical documentation; clear structured prose, correct terminology",
        remove_fillers=True,
        ensure_punctuation=True,
    ),
    "social": Profile(
        "social",
        "social media post; punchy, natural voice",
        remove_fillers=True,
        ensure_punctuation=True,
    ),
    "default": Profile(
        "default",
        "general text",
        remove_fillers=True,
        ensure_punctuation=True,
    ),
}

# process name (lowercase, no .exe) -> profile
_APP_MAP: dict[str, str] = {
    "code": "coding", "cursor": "coding", "windsurf": "coding", "idea64": "coding",
    "pycharm64": "coding", "webstorm64": "coding", "sublime_text": "coding",
    "windowsterminal": "coding", "wezterm-gui": "coding", "alacritty": "coding",
    "outlook": "email", "olk": "email", "thunderbird": "email",
    "telegram": "chat", "discord": "chat", "slack": "chat", "whatsapp": "chat",
    "notion": "documentation", "obsidian": "documentation", "winword": "documentation",
}


def profile_for_app(process_name: str | None, overrides: dict[str, str] | None = None) -> Profile:
    if not process_name:
        return PROFILES["default"]
    key = process_name.lower().removesuffix(".exe")
    mapping = dict(_APP_MAP)
    if overrides:
        mapping.update({k.lower().removesuffix(".exe"): v for k, v in overrides.items()})
    return PROFILES.get(mapping.get(key, "default"), PROFILES["default"])
