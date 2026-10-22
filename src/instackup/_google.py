"""Google Cloud authentication shared by the BigQuery, Cloud Storage and Sheets tools."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._utils import missing_extra_message
from .credentials import get_default_store, lookup_connection

try:
    import google.auth
    from google.auth.credentials import Credentials
    from google.oauth2 import service_account
except ImportError as exc:  # pragma: no cover - depends on installed extras
    raise ImportError(missing_extra_message("gcp")) from exc


@dataclass(frozen=True)
class GoogleAuth:
    credentials: Credentials
    project_id: str | None
    # Legacy {"id", "name", "number"} dict exposed as the tools' ``project`` attribute.
    project_info: dict[str, Any] | None


def resolve_google_auth(
    connection: str = "default",
    credentials: Mapping[str, Any] | None = None,
    *,
    scopes: Sequence[str] | None = None,
    use_config: bool = True,
) -> GoogleAuth:
    """Build Google credentials for a connection.

    In order of preference: inline ``service_account_info`` (a dict or JSON string),
    a key file (``service_account_file``, or the legacy ``secret_filename``), and
    finally Application Default Credentials, which covers Workload Identity, the GCE /
    Cloud Run metadata server and ``gcloud auth application-default login``.
    ``use_config=False`` skips the credential store (explicit ``credentials`` are still used).
    """
    use_settings = use_config or credentials is not None
    settings = (lookup_connection("google", connection, credentials) if use_settings else None) or {}

    info = settings.get("service_account_info")
    key_file = settings.get("service_account_file") or settings.get("secret_filename")
    google_credentials: Credentials
    if info:
        info_dict = json.loads(info) if isinstance(info, str) else dict(info)
        google_credentials = service_account.Credentials.from_service_account_info(info_dict, scopes=scopes)
        default_project = info_dict.get("project_id")
    elif key_file:
        # Paths from the store are relative to the credentials file; explicit ones to the CWD.
        path = Path(key_file).expanduser() if credentials is not None else get_default_store().resolve_path(key_file)
        key_file_credentials = service_account.Credentials.from_service_account_file(str(path), scopes=scopes)
        google_credentials, default_project = key_file_credentials, key_file_credentials.project_id
    else:
        google_credentials, default_project = google.auth.default(scopes=scopes)

    project_id = settings.get("project_id") or default_project
    project_info = (
        {"id": project_id, "name": settings.get("project_name"), "number": settings.get("project_number")}
        if settings
        else None
    )
    return GoogleAuth(credentials=google_credentials, project_id=project_id, project_info=project_info)
