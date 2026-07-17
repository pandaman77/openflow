"""_join_segments: restore dots whisper drops at segment boundaries."""

from openflow_engine.stt import _join_segments


def test_dot_restored_before_capitalized_segment():
    # Real case: small model on Russian drops terminal dots between pauses.
    segments = [
        "Ну конечно не очень убедительно то что у них не было прав доступа",
        "Мне кажется просто никто ничего не хочет делать",
        "Какая-то прям классика жанра.",
    ]
    assert _join_segments(segments) == (
        "Ну конечно не очень убедительно то что у них не было прав доступа. "
        "Мне кажется просто никто ничего не хочет делать. "
        "Какая-то прям классика жанра."
    )


def test_existing_punctuation_kept():
    assert _join_segments(["Привет!", "Как дела?"]) == "Привет! Как дела?"


def test_mid_sentence_split_untouched():
    # A long sentence split across segments continues lowercase — no dot.
    assert _join_segments(["я говорил про", "сервер и бэкапы"]) == "я говорил про сервер и бэкапы"


def test_last_segment_not_terminated():
    # Final punctuation is the cleanup stage's job, not the joiner's.
    assert _join_segments(["Привет"]) == "Привет"


def test_empty_segments_skipped():
    assert _join_segments(["", "  ", "Привет", ""]) == "Привет"
