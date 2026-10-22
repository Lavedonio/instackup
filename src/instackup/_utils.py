"""Small internal helpers shared by the tool modules. Not part of the public API."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

EXTRA_INSTALL_HINT = "This feature needs optional dependencies. Install them with: pip install 'instackup[{extra}]'"


def missing_extra_message(extra: str) -> str:
    """Message for an ImportError raised when an optional dependency group is not installed."""
    return EXTRA_INSTALL_HINT.format(extra=extra)


def as_folder(path: str) -> str:
    """Ensure a non-empty remote path ends with a single "/" so it can be used as a key prefix."""
    if path and not path.endswith("/"):
        return path + "/"
    return path


def timestamped_dir_name(prefix: str) -> str:
    """Local directory name used when downloading a whole bucket, e.g. "bucket_2026-01-31T13h45m10"."""
    return f"{prefix}_{datetime.now():%Y-%m-%dT%Hh%Mm%S}"


def local_path_for(download_dir: Path, relative_key: str) -> Path | None:
    """Local path for a remote key inside ``download_dir``.

    Returns None when the key would land outside it (e.g. "../../etc/x"): object
    names are untrusted input and may contain ".." segments.
    """
    target = download_dir.joinpath(*relative_key.split("/"))
    if not target.resolve().is_relative_to(download_dir.resolve()):
        return None
    return target
