"""Bounded HTTP requests and public archive failure summaries."""

from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def fetch_bytes(url: str) -> bytes:
    retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    with requests.Session() as session:
        # Public archive requests must not pick up machine-local login state.
        session.trust_env = False
        session.mount("https://", HTTPAdapter(max_retries=retry))
        response = session.get(url, timeout=(15, 120))
        response.raise_for_status()
        return response.content


def download_to(url: str, path: Path) -> None:
    data = fetch_bytes(url)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)


def report_stats(stats: dict) -> None:
    print("Download summary: " + ", ".join(f"{key}={value}" for key, value in sorted(stats.items())), flush=True)
    failed = sum(value for key, value in stats.items() if key in {"failed", "download_error", "csv_read_error"})
    if failed:
        raise SystemExit(f"{failed} target(s) failed. Retry the same project to retrieve missing data.")
