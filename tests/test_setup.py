import hashlib
import zipfile
from unittest.mock import patch

import pytest

import dlyso_runtime as runtime
import dlyso_setup as setup


def archive_fixture(tmp_path, content=b"checkpoint", extra=None):
    archive = tmp_path / "models.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("scripts/models/example.pt", content)
        if extra:
            z.writestr(extra, b"unexpected")
    return archive, {"models/example.pt": hashlib.sha256(b"checkpoint").hexdigest()}


def test_verified_install_and_repeat_without_download(tmp_path):
    archive, hashes = archive_fixture(tmp_path)
    target = tmp_path / "installed"
    setup.install_archive(archive, target, hashes)
    assert setup.verified(target, hashes)
    with (
        patch.object(setup, "model_manifest", return_value=hashes),
        patch.object(setup, "model_root", return_value=target),
    ):
        with patch.object(setup, "fetch_archive") as download:
            assert setup.setup_models() == target
            download.assert_not_called()


def test_bad_checksum_preserves_existing_model(tmp_path):
    archive, hashes = archive_fixture(tmp_path, b"corrupted")
    target = tmp_path / "installed"
    (target / "models").mkdir(parents=True)
    model = target / "models/example.pt"
    model.write_bytes(b"previous valid checkpoint")
    with pytest.raises(ValueError, match="checksum"):
        setup.install_archive(archive, target, hashes)
    assert model.read_bytes() == b"previous valid checkpoint"


def test_archive_rejects_unexpected_paths(tmp_path):
    archive, hashes = archive_fixture(tmp_path, extra="scripts/../../escaped.pt")
    with pytest.raises(ValueError, match="Unexpected"):
        setup.install_archive(archive, tmp_path / "installed", hashes)
    assert not (tmp_path / "escaped.pt").exists()


def test_installed_application_discovers_user_models(tmp_path, monkeypatch):
    monkeypatch.delenv("DLYSO_MODEL_ROOT", raising=False)
    monkeypatch.setattr(runtime, "__file__", str(tmp_path / "site-packages/dlyso_runtime.py"))
    monkeypatch.setattr(runtime, "data_root", lambda: tmp_path / "data")
    assert runtime.model_root() == tmp_path / "data/models" / runtime.VERSION / "scripts"
    monkeypatch.setenv("DLYSO_MODEL_ROOT", str(tmp_path / "explicit"))
    assert runtime.model_root() == tmp_path / "explicit"


def test_failed_download_leaves_no_completed_install(tmp_path, monkeypatch):
    _, hashes = archive_fixture(tmp_path)
    monkeypatch.setenv("DLYSO_MODEL_ROOT", str(tmp_path / "destination"))

    def interrupted(path):
        path.write_bytes(b"partial download")
        raise OSError("interrupted")

    with (
        patch.object(setup, "model_manifest", return_value=hashes),
        patch.object(setup, "fetch_archive", side_effect=interrupted),
    ):
        with pytest.raises(OSError, match="interrupted"):
            setup.setup_models()
    assert not (tmp_path / "destination/models/example.pt").exists()
    assert not list(tmp_path.glob(".download-*"))


def test_bootstrap_runs_setup_only_after_successful_package_install(monkeypatch):
    import install
    import subprocess
    import sys

    monkeypatch.setattr(sys, "argv", ["install.py", "--skip-dust"])
    with patch.object(install.subprocess, "run") as run:
        install.main()
    assert run.call_args_list[1].args[0] == [sys.executable, "-m", "dlyso_setup", "--skip-dust"]
    with patch.object(install.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "pip")) as run:
        with pytest.raises(subprocess.CalledProcessError):
            install.main()
    assert run.call_count == 1


@pytest.mark.parametrize('terminal', [True, False])
def test_download_progress_preserves_terminal_and_log_output(tmp_path, monkeypatch, terminal):
    import io
    from unittest.mock import MagicMock
    class Stream(io.StringIO):
        def isatty(self):
            return terminal
    stream = Stream()
    response = MagicMock(status_code=200, headers={'Content-Length': '6'})
    response.iter_content.return_value = [b'abc', b'def']
    session = MagicMock()
    session.__enter__.return_value = session
    session.get.return_value.__enter__.return_value = response
    monkeypatch.setattr(setup.requests, 'Session', lambda: session)
    monkeypatch.setattr(setup.sys, 'stdout', stream)
    output = tmp_path / 'download.zip'
    setup.fetch_archive(output)
    assert output.read_bytes() == b'abcdef'
    text = stream.getvalue()
    assert '(100%)' in text and text.endswith('\n')
    if terminal:
        assert '\r' in text and text.count('\n') == 1
    else:
        assert '\r' not in text
