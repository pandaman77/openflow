"""Text cleanup: fast rule-based pass and smart LLM polishing."""

from .rules import fast_cleanup

__all__ = ["fast_cleanup"]
