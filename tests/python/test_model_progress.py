"""Model-download progress: cache accounting and the watcher's ticks."""

from __future__ import annotations

import huggingface_hub.constants as hf_constants
import pytest

from openflow_engine import model_progress


@pytest.fixture()
def hf_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(hf_constants, "HF_HUB_CACHE", str(tmp_path))
    return tmp_path


def _blobs(cache, repo_id):
    path = cache / f"models--{repo_id.replace('/', '--')}" / "blobs"
    path.mkdir(parents=True)
    return path


def test_repo_for_model_knows_shipped_engines():
    assert model_progress.repo_for_model("nemo-parakeet-tdt-0.6b-v3") == (
        "istupakov/parakeet-tdt-0.6b-v3-onnx"
    )
    assert model_progress.repo_for_model("gigaam-v3-e2e-ctc") == "istupakov/gigaam-v3-onnx"
    assert model_progress.repo_for_model("no-such-model") is None


def test_downloaded_bytes_counts_finished_and_in_flight(hf_cache):
    repo = "istupakov/parakeet-tdt-0.6b-v3-onnx"
    blobs = _blobs(hf_cache, repo)
    (blobs / "abc123").write_bytes(b"x" * 100)
    (blobs / "def456.incomplete").write_bytes(b"y" * 50)

    assert model_progress.downloaded_bytes(repo) == 150


def test_downloaded_bytes_is_zero_before_any_download(hf_cache):
    assert model_progress.downloaded_bytes("istupakov/gigaam-v3-onnx") == 0


class _FakeTranscriber:
    engine = "parakeet"
    model_name = "nemo-parakeet-tdt-0.6b-v3"


def test_watcher_reports_start_and_finish(hf_cache):
    repo = "istupakov/parakeet-tdt-0.6b-v3-onnx"
    _blobs(hf_cache, repo).joinpath("blob.incomplete").write_bytes(b"z" * 42)
    seen: list[dict] = []

    with model_progress.watch(_FakeTranscriber(), seen.append):
        pass  # stands in for transcriber.load()

    assert len(seen) >= 2, "expected at least an opening and a closing tick"
    assert seen[0]["engine"] == "parakeet"
    assert seen[0]["downloaded"] == 42
    assert seen[0]["total"] == model_progress.DOWNLOAD_SIZES["parakeet"]
    assert seen[0]["done"] is False
    assert seen[-1]["done"] is True


def test_watcher_still_ticks_for_an_unknown_model(hf_cache):
    """Whisper repos aren't in the table: no byte count, but the tick must
    still fire — it is what keeps the shell from declaring the engine hung."""

    class Whisper:
        engine = "whisper"
        model_name = "small"

    seen: list[dict] = []
    with model_progress.watch(Whisper(), seen.append):
        pass

    assert seen, "watcher went silent for an unknown model"
    assert "downloaded" not in seen[0]
    assert seen[0]["engine"] == "whisper"


def test_watcher_survives_a_broken_callback(hf_cache):
    """A dead pipe on the shell side must never take the download with it."""

    def explode(_payload):
        raise RuntimeError("pipe closed")

    with model_progress.watch(_FakeTranscriber(), explode):
        pass  # must not raise


def test_no_callback_means_no_thread(hf_cache):
    watcher = model_progress.watch(_FakeTranscriber(), None)
    with watcher:
        pass
    assert watcher._thread is None
