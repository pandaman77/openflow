"""Fast rule-based cleanup tests: fillers, duplicates, spacing, caps."""

from openflow_engine.cleanup.rules import (
    capitalize_sentences,
    collapse_duplicates,
    ensure_terminal_punctuation,
    fast_cleanup,
    literal_cleanup,
    normalize_spacing,
    remove_fillers,
)


class TestRemoveFillers:
    def test_ru_fillers(self):
        assert "эм" not in remove_fillers("эм я хочу сказать").lower()
        assert remove_fillers("ну вот проект готов").strip() == "проект готов"
        assert "как бы" not in remove_fillers("это как бы важно")

    def test_en_fillers(self):
        assert "um" not in remove_fillers("um I think so").lower().split()
        assert "uh" not in remove_fillers("uh let me see").lower().split()
        assert "you know" not in remove_fillers("it is you know difficult")

    def test_does_not_eat_real_words(self):
        # "умный" contains "ум", "эмоция" contains "эм" — must survive
        assert "умный" in remove_fillers("умный человек")
        assert "эмоция" in remove_fillers("сильная эмоция")
        assert "summer" in remove_fillers("summer is here")
        assert "недоумение" in remove_fillers("полное недоумение")

    def test_single_a_kept(self):
        # одиночное "а" — союз, не филлер
        assert remove_fillers("а потом пошёл домой") == "а потом пошёл домой"


class TestCollapseDuplicates:
    def test_ru_stutter(self):
        assert collapse_duplicates("что что делать") == "что делать"

    def test_en_stutter(self):
        assert collapse_duplicates("I think think so") == "I think so"

    def test_with_comma(self):
        assert collapse_duplicates("проект, проект готов") == "проект готов"

    def test_legit_repetition_of_different_words_kept(self):
        assert collapse_duplicates("очень очень важно") == "очень важно"  # stutter collapsed
        assert collapse_duplicates("да нет наверное") == "да нет наверное"


class TestSpacingAndCaps:
    def test_space_before_punct(self):
        assert normalize_spacing("привет , мир !") == "привет, мир!"

    def test_missing_space_after_punct(self):
        assert normalize_spacing("раз.два") == "раз. два"

    def test_decimal_numbers_untouched(self):
        assert normalize_spacing("версия 3.14 вышла") == "версия 3.14 вышла"

    def test_capitalize_first_and_after_period(self):
        assert capitalize_sentences("привет. как дела") == "Привет. Как дела"

    def test_terminal_punctuation(self):
        assert ensure_terminal_punctuation("привет") == "привет."
        assert ensure_terminal_punctuation("привет!") == "привет!"


class TestFastCleanup:
    def test_full_ru(self):
        out = fast_cleanup("эм ну вот я хочу сказать что что проект готов")
        assert out == "Я хочу сказать что проект готов."

    def test_full_en(self):
        out = fast_cleanup("um so I think think the project is ready")
        assert out == "So I think the project is ready."

    def test_empty(self):
        assert fast_cleanup("") == ""
        assert fast_cleanup("   ") == ""

    def test_fillers_can_be_kept(self):
        out = fast_cleanup("эм привет", remove_fillers_enabled=False)
        assert "эм" in out.lower()

    def test_literal_keeps_everything(self):
        out = literal_cleanup("эм ну вот  привет")
        assert "эм" in out
        assert "  " not in out
