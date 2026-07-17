"""SmartCleaner.available(): a broken llama_cpp must disable smart, not crash."""

import sys

from openflow_engine.cleanup.llm import SmartCleaner


class _ExplodingFinder:
    """Meta-path hook that makes `import llama_cpp` raise OSError, mimicking
    a frozen bundle whose native lib directory is missing (WinError 3)."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "llama_cpp":
            raise OSError("[WinError 3] missing llama_cpp/lib")
        return None


def test_available_false_when_model_missing(tmp_path):
    assert SmartCleaner(str(tmp_path / "nope.gguf")).available() is False
    assert SmartCleaner(None).available() is False


def test_available_survives_broken_llama_cpp(tmp_path, monkeypatch):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"stub")
    monkeypatch.delitem(sys.modules, "llama_cpp", raising=False)
    finder = _ExplodingFinder()
    sys.meta_path.insert(0, finder)
    try:
        cleaner = SmartCleaner(str(gguf))
        assert cleaner.available() is False  # no exception escapes
        assert cleaner._load_failed is True  # and it latches off
    finally:
        sys.meta_path.remove(finder)
