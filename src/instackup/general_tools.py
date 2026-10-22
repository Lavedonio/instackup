"""General helpers: credentials access (legacy), string normalization and remote URI parsing."""

from __future__ import annotations

import json
import logging
import os
import unicodedata
import warnings
from typing import Any

import yaml

from .credentials import CREDENTIALS_FILE_ENV, LEGACY_CREDENTIALS_FILE_ENV, get_default_store

logger = logging.getLogger(__name__)


def fetch_credentials(service_name: str, *args: str, **kwargs: str) -> Any:
    """Read a section of the secrets file set in the ``CREDENTIALS_HOME`` environment variable.

    .. deprecated:: 0.4.0
        Use :func:`instackup.credentials.get_credentials` (or
        ``get_default_store().get_value(...)`` for custom sections), which also
        reads environment variables and secret managers.

    The service is selected by ``service_name``; extra positional and keyword
    arguments walk further down the structure, in the order given. If the service is
    "credentials_path", the directory where the secrets file is located is returned.
    Keys are case-sensitive, matching the file exactly.
    """
    warnings.warn(
        "fetch_credentials() is deprecated; use instackup.credentials.get_credentials() instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    secrets_path = os.environ.get(LEGACY_CREDENTIALS_FILE_ENV) or os.environ.get(CREDENTIALS_FILE_ENV)
    if secrets_path is None:
        raise KeyError(f'Environment Variable "{LEGACY_CREDENTIALS_FILE_ENV}" not found')

    if service_name == "credentials_path":
        return os.path.dirname(secrets_path)

    is_json = os.path.splitext(secrets_path)[1].lower() == ".json"
    with open(secrets_path, encoding="utf-8") as stream:
        secrets = json.load(stream) if is_json else yaml.safe_load(stream)

    value = secrets[service_name]
    for key in (*args, *kwargs.values()):
        value = value[key]
    return value


def code_location() -> Any:
    """Where the code is running, e.g. "local" or "production".

    Read from the ``INSTACKUP_LOCATION`` environment variable or the ``Location``
    key of the credentials file. Returns ``None`` if it isn't set.
    """
    return get_default_store().get_value("location")


def unicode_to_ascii(unicode_string: str) -> str:
    """Replace all non-ASCII chars in a string by the closest possible match.

    Inspired by https://stackoverflow.com/a/517974/11981524
    """
    nfkd_form = unicodedata.normalize("NFKD", unicode_string)
    return "".join(char for char in nfkd_form if not unicodedata.combining(char))


def parse_remote_uri(uri: str, service: str) -> tuple[str, str]:
    """Split a Google Cloud Storage ("gs") or Amazon S3 ("s3") URI into bucket and subfolder.

    The subfolder, when present, always ends with "/". Raises ``ValueError`` if the
    URI isn't of the form ``<service>://<bucket>[/<subfolder>]``.
    """
    service = service.lower()
    scheme, separator, rest = uri.partition("://")
    bucket, _, subfolder = rest.partition("/")

    if not separator or scheme.lower() != service or not bucket:
        raise ValueError(
            f"Invalid service type ({service}) in URI given '{uri}'! "
            f"Format should be like '{service}://<bucket>/<subfolder>/'"
        )

    if subfolder and not subfolder.endswith("/"):
        subfolder += "/"

    logger.debug("uri_service: %r, bucket: %r, subfolder: %r", scheme, bucket, subfolder)
    return bucket, subfolder
