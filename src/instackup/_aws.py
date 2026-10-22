"""AWS session handling shared by the S3 and Redshift tools."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._utils import missing_extra_message
from .credentials import lookup_connection

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError as exc:  # pragma: no cover - depends on installed extras
    raise ImportError(missing_extra_message("aws")) from exc

__all__ = ["BotoCoreError", "ClientError", "create_session"]


def create_session(connection: str = "default", credentials: Mapping[str, Any] | None = None) -> boto3.Session:
    """Create a boto3 session for a connection.

    Recognized settings: ``access_key``/``secret_key`` (legacy names, also accepted as
    ``aws_access_key_id``/``aws_secret_access_key``), ``session_token``, ``profile``
    and ``region``. Anything not set falls through to boto3's default credential
    chain (environment, shared config/SSO, container and instance roles), which is
    the recommended setup in production.
    """
    settings = lookup_connection("aws", connection, credentials) or {}

    def setting(*names: str) -> Any:
        return next((settings[name] for name in names if settings.get(name)), None)

    return boto3.Session(
        aws_access_key_id=setting("access_key", "aws_access_key_id"),
        aws_secret_access_key=setting("secret_key", "aws_secret_access_key"),
        aws_session_token=setting("session_token", "aws_session_token"),
        region_name=setting("region", "region_name"),
        profile_name=setting("profile", "profile_name"),
    )
