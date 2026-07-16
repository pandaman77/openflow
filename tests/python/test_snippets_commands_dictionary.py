"""Snippets, voice commands and personal dictionary tests."""

from pathlib import Path

from openflow_engine.commands import CommandDetector
from openflow_engine.dictionary import PersonalDictionary
from openflow_engine.snippets import SnippetStore


def make_store(tmp_path: Path) -> SnippetStore:
    store = SnippetStore(path=tmp_path / "snippets.json")
    store.add("мой календарь", "https://cal.com/kolya", folder="links")
    store.add("my address", "119002, Москва, ул. Арбат, 1")
    store.add("рабочая почта", "kolya@fondvera.ru")
    return store


class TestSnippets:
    def test_whole_utterance_exact(self, tmp_path):
        assert make_store(tmp_path).expand("мой календарь") == "https://cal.com/kolya"

    def test_whole_utterance_with_stt_punctuation(self, tmp_path):
        # STT adds period/capitalization — trigger must still fire
        assert make_store(tmp_path).expand("Мой календарь.") == "https://cal.com/kolya"

    def test_inline_expansion(self, tmp_path):
        out = make_store(tmp_path).expand("скинь мне ссылку мой календарь пожалуйста")
        assert "https://cal.com/kolya" in out
        assert "мой календарь" not in out

    def test_no_partial_word_match(self, tmp_path):
        store = SnippetStore(path=tmp_path / "s.json")
        store.add("адрес", "ул. Арбат")
        assert store.expand("адресат письма") == "адресат письма"

    def test_persistence(self, tmp_path):
        store = make_store(tmp_path)
        store.save()
        reloaded = SnippetStore(path=store.path)
        assert reloaded.expand("рабочая почта") == "kolya@fondvera.ru"

    def test_remove(self, tmp_path):
        store = make_store(tmp_path)
        assert store.remove("мой календарь") is True
        assert store.expand("мой календарь") == "мой календарь"


class TestCommands:
    def setup_method(self):
        self.det = CommandDetector()

    def test_ru_commands(self):
        assert self.det.detect("новый абзац").action == "new_paragraph"
        assert self.det.detect("Отмена.").action == "undo"
        assert self.det.detect("удали последнее предложение").action == "delete_last_sentence"

    def test_en_commands(self):
        assert self.det.detect("New paragraph").action == "new_paragraph"
        assert self.det.detect("delete previous sentence").action == "delete_last_sentence"

    def test_llm_transforms_flagged(self):
        match = self.det.detect("сделай короче")
        assert match.action == "make_shorter"
        assert match.args.get("llm") is True

    def test_dictation_containing_command_words_passes(self):
        # обычная диктовка не должна детектиться как команда
        assert self.det.detect("я начну с нового абзаца завтра") is None
        assert self.det.detect("please undo the damage they caused") is None

    def test_custom_command(self):
        det = CommandDetector(extra={"открой курсор": "open_cursor"})
        assert det.detect("Открой курсор").action == "open_cursor"


class TestDictionary:
    def test_replacements(self, tmp_path):
        d = PersonalDictionary(path=tmp_path / "dict.json")
        d.add_replacement("битрикс 24", "Bitrix24")
        d.add_replacement("виспер", "Whisper")
        out = d.apply_replacements("я настроил Битрикс 24 и виспер")
        assert "Bitrix24" in out and "Whisper" in out

    def test_replacement_not_inside_words(self, tmp_path):
        d = PersonalDictionary(path=tmp_path / "dict.json")
        d.add_replacement("кот", "cat")
        assert d.apply_replacements("который час") == "который час"

    def test_initial_prompt(self, tmp_path):
        d = PersonalDictionary(path=tmp_path / "dict.json")
        assert d.initial_prompt() is None
        d.add_word("Bitrix24")
        d.add_word("fondvera")
        assert d.initial_prompt() == "Bitrix24, fondvera"

    def test_persistence(self, tmp_path):
        d = PersonalDictionary(path=tmp_path / "dict.json")
        d.add_word("Гусар")
        d.add_replacement("гусар", "Гусар")
        d.save()
        d2 = PersonalDictionary(path=d.path)
        assert "Гусар" in d2.words
        assert d2.apply_replacements("привет гусар") == "привет Гусар"
