"""LlmDownloader: state machine, atomicity, no re-download of an existing file."""

import sys
import time
import types

from openflow_engine.llm_download import RECOMMENDED_FILE, LlmDownloader


class _FakeResponse:
    def __init__(self, chunks, total=None, fail_after=None):
        self._chunks = chunks
        self.headers = {"content-length": str(total if total is not None else sum(len(c) for c in chunks))}
        self._fail_after = fail_after

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        for i, chunk in enumerate(self._chunks):
            if self._fail_after is not None and i >= self._fail_after:
                raise IOError("connection reset")
            yield chunk

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _install_fake_requests(monkeypatch, response):
    fake = types.ModuleType("requests")
    fake.get = lambda url, stream, timeout: response
    monkeypatch.setitem(sys.modules, "requests", fake)


def _wait(dl, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if dl.status()["state"] in ("done", "error"):
            return dl.status()
        time.sleep(0.02)
    raise AssertionError(f"download did not finish: {dl.status()}")


def test_success_atomic(tmp_path, monkeypatch):
    _install_fake_requests(monkeypatch, _FakeResponse([b"a" * 10, b"b" * 10]))
    dl = LlmDownloader(tmp_path)
    assert dl.start() == {"ok": True}
    status = _wait(dl)
    assert status["state"] == "done"
    target = tmp_path / RECOMMENDED_FILE
    assert target.read_bytes() == b"a" * 10 + b"b" * 10
    assert status["path"] == str(target)
    assert not list(tmp_path.glob("*.part"))


def test_failure_cleans_partial(tmp_path, monkeypatch):
    _install_fake_requests(monkeypatch, _FakeResponse([b"a" * 10, b"b" * 10], fail_after=1))
    dl = LlmDownloader(tmp_path)
    dl.start()
    status = _wait(dl)
    assert status["state"] == "error"
    assert "connection reset" in status["error"]
    assert not (tmp_path / RECOMMENDED_FILE).exists()
    assert not list(tmp_path.glob("*.part"))


def test_incomplete_body_is_error(tmp_path, monkeypatch):
    _install_fake_requests(monkeypatch, _FakeResponse([b"a" * 10], total=999))
    dl = LlmDownloader(tmp_path)
    dl.start()
    assert _wait(dl)["state"] == "error"
    assert not (tmp_path / RECOMMENDED_FILE).exists()


def test_existing_file_short_circuits(tmp_path):
    (tmp_path / RECOMMENDED_FILE).write_bytes(b"model")
    dl = LlmDownloader(tmp_path)
    assert dl.start() == {"ok": True, "already_downloaded": True}
    assert dl.status()["state"] == "done"
