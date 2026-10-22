"""Credential resolution for every instackup tool.

Credentials are organized as ``service -> connection -> settings``::

    postgresql:
      default:
        host: db.internal
        user: etl
        password: ${PG_PASSWORD}
      analytics:
        url: postgresql://reader@analytics.internal:5432/warehouse

A :class:`CredentialStore` reads that structure from one or more *sources* and
deep-merges them, the first source taking precedence. The default store, built by
:meth:`CredentialStore.from_environment`, checks, in order:

1. ``INSTACKUP_<SERVICE>__<CONNECTION>__<KEY>`` environment variables;
2. a secret in AWS Secrets Manager named by ``INSTACKUP_AWS_SECRET_ID``;
3. a secret in GCP Secret Manager named by ``INSTACKUP_GCP_SECRET_NAME``;
4. a YAML/JSON file named by ``INSTACKUP_CREDENTIALS_FILE`` (or the legacy ``CREDENTIALS_HOME``).

None of them is required. Cloud tools fall back to the platform's own identity
(Google Application Default Credentials, the AWS default credential chain) when no
credentials are configured for the ``default`` connection, which is the recommended
setup for production workloads.

Service and connection names are case-insensitive. Setting names should be lowercase.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import threading
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml

from ._utils import missing_extra_message

__all__ = [
    "AWSSecretsManagerSource",
    "CredentialSource",
    "CredentialStore",
    "CredentialsError",
    "CredentialsNotFoundError",
    "EnvironmentSource",
    "FileSource",
    "GCPSecretManagerSource",
    "MappingSource",
    "get_credentials",
    "get_default_store",
    "set_default_store",
]

logger = logging.getLogger(__name__)

ENV_PREFIX = "INSTACKUP_"
ENV_SEPARATOR = "__"
CREDENTIALS_FILE_ENV = "INSTACKUP_CREDENTIALS_FILE"
LEGACY_CREDENTIALS_FILE_ENV = "CREDENTIALS_HOME"
AWS_SECRET_ID_ENV = "INSTACKUP_AWS_SECRET_ID"
GCP_SECRET_NAME_ENV = "INSTACKUP_GCP_SECRET_NAME"

# Top-level (non service/connection) settings that can be set with INSTACKUP_<NAME>.
TOP_LEVEL_ENV_SETTINGS = frozenset({"location"})

_ENV_REFERENCE = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^}]*))?\}")


class CredentialsError(Exception):
    """Raised when credentials are malformed or can't be loaded."""


class CredentialsNotFoundError(CredentialsError, KeyError):
    """Raised when required credentials are missing.

    Subclasses :class:`KeyError` because that's what instackup raised before 0.4.0.
    """

    def __str__(self) -> str:
        # KeyError.__str__ wraps the message in quotes; plain messages read better.
        return str(self.args[0]) if self.args else ""


@runtime_checkable
class CredentialSource(Protocol):
    """Anything that can produce a (possibly partial) credentials document."""

    def load(self) -> dict[str, Any]:
        """Return the credentials document. Called once per :class:`CredentialStore` load."""
        ...


class _Template(str):
    """A string from a credentials file that references environment variables.

    References are expanded only when the value is requested, so a file can mention
    variables that aren't set in environments that never use them.
    """

    __slots__ = ()


def parse_document(text: str, *, is_json: bool | None = None) -> dict[str, Any]:
    """Parse a YAML or JSON credentials document.

    JSON is detected from ``is_json`` or, when it's ``None``, from a leading "{".
    """
    if is_json is None:
        is_json = text.lstrip().startswith("{")
    try:
        data = json.loads(text) if is_json else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise CredentialsError(f"Credentials document is not valid {'JSON' if is_json else 'YAML'}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise CredentialsError("Credentials document must be a mapping at the top level.")
    return data


class MappingSource:
    """Credentials given directly as a Python mapping. Handy for tests and programmatic setup."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data = copy.deepcopy(dict(data))

    def load(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<{len(self._data)} keys>)"


class FileSource:
    """A YAML or JSON file, such as the legacy ``CREDENTIALS_HOME`` secrets file.

    String values may reference environment variables as ``${NAME}`` or
    ``${NAME:-default}``, so the file itself can be committed without secrets.
    References are expanded when a value is read; a value that references an unset
    variable (without a default) is treated as missing (``None``) and a warning is
    logged. Relative key-file paths in it (like ``service_account_file``) are
    resolved against the file's directory.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path).expanduser()

    @property
    def base_dir(self) -> Path:
        return self.path.resolve().parent

    def load(self) -> dict[str, Any]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise CredentialsError(f"Credentials file not found: {self.path}") from exc
        data = parse_document(text, is_json=self.path.suffix.lower() == ".json")
        return _mark_templates(data)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self.path)!r})"


class EnvironmentSource:
    """Credentials from ``INSTACKUP_<SERVICE>__<CONNECTION>__<KEY>[__<SUBKEY>...]`` variables.

    Example::

        INSTACKUP_POSTGRESQL__DEFAULT__PASSWORD=s3cret
        INSTACKUP_REDSHIFT__DEFAULT__MASTER_PASSWORD__HOST=cluster.example.com
        INSTACKUP_LOCATION=production

    All name parts are lowercased. Values are always strings.
    """

    def __init__(self, environ: Mapping[str, str] | None = None, prefix: str = ENV_PREFIX) -> None:
        self._environ = environ
        self.prefix = prefix

    def load(self) -> dict[str, Any]:
        environ = os.environ if self._environ is None else self._environ
        data: dict[str, Any] = {}
        for name, value in environ.items():
            if not name.upper().startswith(self.prefix):
                continue
            path = [part.lower() for part in name[len(self.prefix) :].split(ENV_SEPARATOR)]
            if len(path) == 1 and path[0] in TOP_LEVEL_ENV_SETTINGS:
                data[path[0]] = value
            elif len(path) >= 3 and all(path):
                node = data
                for part in path[:-1]:
                    child = node.setdefault(part, {})
                    if not isinstance(child, dict):
                        raise CredentialsError(
                            f"Environment variable {name} conflicts with another INSTACKUP_ variable."
                        )
                    node = child
                node[path[-1]] = value
            # Anything else (e.g. INSTACKUP_CREDENTIALS_FILE) is a setting, not a credential.
        return data

    def __repr__(self) -> str:
        return f"{type(self).__name__}(prefix={self.prefix!r})"


class AWSSecretsManagerSource:
    """A whole credentials document (JSON or YAML) stored as one AWS Secrets Manager secret.

    Uses the AWS default credential chain unless a ``boto3.Session`` is given.
    """

    def __init__(self, secret_id: str, *, region_name: str | None = None, session: Any = None) -> None:
        self.secret_id = secret_id
        self.region_name = region_name
        self._session = session

    def load(self) -> dict[str, Any]:
        session = self._session
        if session is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - depends on installed extras
                raise ImportError(missing_extra_message("aws")) from exc
            session = boto3.Session(region_name=self.region_name)
        client = session.client("secretsmanager", region_name=self.region_name)
        response = client.get_secret_value(SecretId=self.secret_id)
        text = response.get("SecretString")
        if text is None:
            text = bytes(response["SecretBinary"]).decode("utf-8")
        return parse_document(text)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.secret_id!r})"


class GCPSecretManagerSource:
    """A whole credentials document (JSON or YAML) stored as one GCP Secret Manager secret.

    ``name`` is ``projects/<project>/secrets/<secret>`` (latest version) or a full
    ``.../versions/<version>`` resource name. Uses Application Default Credentials
    unless a ``SecretManagerServiceClient`` is given.
    """

    def __init__(self, name: str, *, client: Any = None) -> None:
        self.name = name if "/versions/" in name else f"{name.rstrip('/')}/versions/latest"
        self._client = client

    def load(self) -> dict[str, Any]:
        client = self._client
        if client is None:
            try:
                from google.cloud import secretmanager
            except ImportError as exc:  # pragma: no cover - depends on installed extras
                raise ImportError(missing_extra_message("gcp")) from exc
            client = secretmanager.SecretManagerServiceClient()
        response = client.access_secret_version(name=self.name)
        return parse_document(response.payload.data.decode("utf-8"))

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r})"


class CredentialStore:
    """Merged view over one or more :class:`CredentialSource` objects.

    Sources are loaded lazily on first access and cached; call :meth:`reload` to
    read them again (e.g. after rotating a secret).
    """

    def __init__(self, sources: Iterable[CredentialSource]) -> None:
        self._sources: tuple[CredentialSource, ...] = tuple(sources)
        self._data: dict[str, Any] | None = None
        self._lock = threading.Lock()

    # -- Constructors -------------------------------------------------------

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> CredentialStore:
        """Build the default store from the process environment (see the module docstring)."""
        env = os.environ if environ is None else environ
        sources: list[CredentialSource] = [EnvironmentSource(env)]
        if secret_id := env.get(AWS_SECRET_ID_ENV):
            sources.append(AWSSecretsManagerSource(secret_id))
        if secret_name := env.get(GCP_SECRET_NAME_ENV):
            sources.append(GCPSecretManagerSource(secret_name))
        if path := env.get(CREDENTIALS_FILE_ENV) or env.get(LEGACY_CREDENTIALS_FILE_ENV):
            sources.append(FileSource(path))
        return cls(sources)

    @classmethod
    def from_file(cls, path: str | os.PathLike[str]) -> CredentialStore:
        return cls([FileSource(path)])

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> CredentialStore:
        return cls([MappingSource(data)])

    # -- Loading ------------------------------------------------------------

    @property
    def sources(self) -> tuple[CredentialSource, ...]:
        return self._sources

    @property
    def base_dir(self) -> Path | None:
        """Directory of the first file source, used to resolve relative key-file paths."""
        for source in self._sources:
            if isinstance(source, FileSource):
                return source.base_dir
        return None

    def reload(self) -> None:
        with self._lock:
            self._data = None

    def _merged(self) -> dict[str, Any]:
        with self._lock:
            if self._data is None:
                merged: dict[str, Any] = {}
                # Lowest priority first, so higher-priority sources overwrite.
                for source in reversed(self._sources):
                    _deep_update(merged, _normalize(source.load()))
                self._data = merged
            return self._data

    # -- Lookups ------------------------------------------------------------

    def get(self, service: str, connection: str = "default", *, required: bool = False) -> dict[str, Any] | None:
        """Settings for one connection of a service, or ``None`` if not configured.

        With ``required=True``, raises :class:`CredentialsNotFoundError` instead of returning ``None``.
        """
        connections = self._merged().get(service.lower())
        settings = connections.get(connection.lower()) if isinstance(connections, dict) else None
        if settings is None:
            if required:
                raise CredentialsNotFoundError(
                    f"No credentials found for service {service!r}, connection {connection!r}. "
                    f"Configured through: {', '.join(map(repr, self._sources)) or 'no sources'}."
                )
            return None
        if not isinstance(settings, dict):
            raise CredentialsError(f"Credentials for {service!r}/{connection!r} must be a mapping.")
        resolved: dict[str, Any] = _resolve_templates(copy.deepcopy(settings))
        return resolved

    def get_service(self, service: str) -> dict[str, dict[str, Any]]:
        """All connections configured for a service, keyed by connection name."""
        connections = self._merged().get(service.lower())
        if not isinstance(connections, dict):
            return {}
        return {name: settings for name in connections if (settings := self.get(service, name)) is not None}

    def get_value(self, key: str, default: Any = None) -> Any:
        """Any top-level value, e.g. ``get_value("location")`` or a custom section."""
        value = self._merged().get(key.lower(), default)
        return _resolve_templates(copy.deepcopy(value))

    def resolve_path(self, path: str | os.PathLike[str]) -> Path:
        """Resolve a key-file path; relative paths are taken from the credentials file's directory."""
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return candidate
        return (self.base_dir or Path.cwd()) / candidate

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self._sources)!r})"


# -- Default store ----------------------------------------------------------

_default_store: CredentialStore | None = None
_default_store_lock = threading.Lock()


def get_default_store() -> CredentialStore:
    """The process-wide store used by tools when no explicit credentials are given.

    Built from the environment on first use; replace it with :func:`set_default_store`.
    """
    global _default_store
    with _default_store_lock:
        if _default_store is None:
            _default_store = CredentialStore.from_environment()
        return _default_store


def set_default_store(store: CredentialStore | None) -> None:
    """Replace the process-wide store. ``None`` rebuilds it from the environment on next use."""
    global _default_store
    with _default_store_lock:
        _default_store = store


def get_credentials(service: str, connection: str = "default", *, required: bool = False) -> dict[str, Any] | None:
    """Shortcut for ``get_default_store().get(service, connection, required=required)``."""
    return get_default_store().get(service, connection, required=required)


def lookup_connection(
    service: str,
    connection: str,
    credentials: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Settings for a cloud connection, with the rules shared by the AWS and Google tools.

    Explicit ``credentials`` win. Otherwise the default store is consulted; a missing
    ``default`` connection returns ``None`` (meaning "use the platform's ambient
    credentials"), while a missing *named* connection is an error, so a typo can't
    silently connect to the wrong account.
    """
    if credentials is not None:
        return dict(credentials)
    return get_default_store().get(service, connection, required=connection.lower() != "default")


# -- Internals --------------------------------------------------------------


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    """Lowercase service names and connection names, the two case-insensitive levels."""
    normalized: dict[str, Any] = {}
    for service, connections in data.items():
        if isinstance(connections, dict):
            connections = {str(name).lower(): value for name, value in connections.items()}
        normalized[str(service).lower()] = connections
    return normalized


def _deep_update(target: dict[str, Any], updates: Mapping[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def _mark_templates(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _mark_templates(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_mark_templates(item) for item in value]
    if isinstance(value, str) and "${" in value:
        return _Template(value)
    return value


def _resolve_templates(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_templates(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_templates(item) for item in value]
    if isinstance(value, _Template):
        # An unset variable makes the whole value missing (None) rather than an error, so a
        # connection still works when only an unrelated setting (say, a password for
        # another auth method) references a variable that isn't set in this environment.
        missing = [match.group("name") for match in _ENV_REFERENCE.finditer(value) if _expand(match) is None]
        if missing:
            logger.warning("Credentials file references unset environment variables: %s", ", ".join(missing))
            return None
        return _ENV_REFERENCE.sub(lambda match: _expand(match) or "", value)
    return value


def _expand(match: re.Match[str]) -> str | None:
    """Value for one ``${NAME}`` / ``${NAME:-default}`` reference, or None if it's unset without a default."""
    # Same semantics as the shell: ":-" falls back when the variable is unset *or* empty.
    name, default = match.group("name"), match.group("default")
    value = os.environ.get(name)
    if value is not None and (value or default is None):
        return value
    return default
