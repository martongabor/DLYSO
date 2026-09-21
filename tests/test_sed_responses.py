"""Archive responses can be truncated even when the HTTP request succeeds."""

import io
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from astropy.table import Table

from scripts import sed_download_parallel as sed


def response_bytes():
    buffer = io.BytesIO()
    Table({"sed_freq": [1.0], "sed_flux": [2.0], "sed_filter": ["test"]}).write(buffer, format="votable")
    return buffer.getvalue()


def test_truncated_response_is_retried_before_saving(tmp_path, capsys):
    valid = response_bytes()
    output = tmp_path / "10_20.csv"
    with patch.object(sed, "fetch_bytes", side_effect=[valid[:-50], valid]) as fetch:
        with patch.object(sed.time, "sleep"):
            assert sed.download_one(10, 20, 2, output) == "ok"
    assert fetch.call_count == 2
    assert output.exists()
    assert output.with_suffix(".done").read_text() == "OK\n"
    assert "SED 10,20: invalid response (1/3)" in capsys.readouterr().out


def test_persistently_truncated_response_has_bounded_retries(tmp_path, capsys):
    output = tmp_path / "10_20.csv"
    with patch.object(sed, "fetch_bytes", return_value=response_bytes()[:-50]) as fetch:
        with patch.object(sed.time, "sleep"):
            assert sed.download_one(10, 20, 2, output) == "download_error"
    assert fetch.call_count == 3
    urls = [call.args[0] for call in fetch.call_args_list]
    assert len(set(urls)) == 3
    for url in urls:
        query = parse_qs(urlsplit(url).query)
        assert query["-c"][0].replace(" ", ",") == "10,20"
        assert float(query["-c.rs"][0]) == 2
    assert not output.exists()
    assert not output.with_suffix(".part").exists()
    assert "ValueError" in output.with_suffix(".done").read_text()
    assert "SED 10,20: download failed:" in capsys.readouterr().out


def test_non_photometry_table_is_not_cached(tmp_path):
    output = tmp_path / "10_20.csv"
    buffer = io.BytesIO()
    Table({"message": ["server error"]}).write(buffer, format="votable")
    with patch.object(sed, "fetch_bytes", return_value=buffer.getvalue()):
        with patch.object(sed.time, "sleep"):
            assert sed.download_one(10, 20, 2, output) == "download_error"
    assert not output.exists()
    assert "missing required photometry columns" in output.with_suffix(".done").read_text()
