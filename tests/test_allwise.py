"""An unusable cutout is missing evidence, not a fatal acquisition failure."""

import numpy as np
import pytest

from scripts.getstamp import fetch_one
from scripts.download_support import report_stats


def fetch(tmp_path, **kwargs):
    return fetch_one(10, 20, tmp_path / "10_20.png", tmp_path / "10_20.done", 200, 200, 30, 0.5, 99.5, "AIT", **kwargs)


def test_quality_rejection_is_nonfatal_and_does_not_create_image(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.getstamp.hips2fits.query", lambda **kw: np.zeros((200, 200, 3), dtype=np.uint8))
    assert fetch(tmp_path) == "rejected"
    assert not (tmp_path / "10_20.png").exists()
    assert (tmp_path / "10_20.done").read_text() == "REJECTED: median test\n"
    report_stats({"ok": 183, "rejected": 3})


def test_old_median_failure_can_resume_without_network(tmp_path, monkeypatch):
    (tmp_path / "10_20.done").write_text("FAILED: median test\n")
    monkeypatch.setattr("scripts.getstamp.hips2fits.query", lambda **kw: pytest.fail("Unexpected repeat request"))
    assert fetch(tmp_path) == "rejected"
    assert (tmp_path / "10_20.done").read_text() == "REJECTED: median test\n"


def test_rejected_cutout_can_be_requested_again(tmp_path, monkeypatch):
    (tmp_path / "10_20.done").write_text("REJECTED: median test\n")
    monkeypatch.setattr("scripts.getstamp.hips2fits.query", lambda **kw: np.full((200, 200, 3), 100, dtype=np.uint8))
    assert fetch(tmp_path, retry_rejected=True) == "ok"
    assert (tmp_path / "10_20.png").exists()


def test_network_failure_remains_fatal_and_retryable(tmp_path, monkeypatch):
    calls = []

    def outage(**kwargs):
        calls.append(kwargs)
        raise TimeoutError("Archive unavailable")

    monkeypatch.setattr("scripts.getstamp.hips2fits.query", outage)
    assert fetch(tmp_path) == "failed"
    assert fetch(tmp_path) == "failed"
    assert len(calls) == 2
    with pytest.raises(SystemExit, match="1 target"):
        report_stats({"cached": 183, "rejected": 2, "failed": 1})
