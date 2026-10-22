from __future__ import annotations

import json
from pathlib import Path

import pytest

from instackup.general_tools import code_location, fetch_credentials, parse_remote_uri, unicode_to_ascii

SECRETS = {
    "Location": "local",
    "AWS": {"default": {"access_key": "key", "secret_key": "secret"}},
    "RedShift": {"default": {"cluster_credentials": {"host": "cluster"}, "master_password": {"host": "master"}}},
}


@pytest.fixture(params=["yml", "json"])
def secrets_file(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / f"secret.{request.param}"
    path.write_text(json.dumps(SECRETS), encoding="utf-8")  # JSON is valid YAML too
    monkeypatch.setenv("CREDENTIALS_HOME", str(path))
    return path


# -- fetch_credentials (deprecated) ------------------------------------------------


@pytest.mark.usefixtures("secrets_file")
def test_fetch_credentials_returns_sections() -> None:
    with pytest.deprecated_call():
        assert fetch_credentials("AWS") == SECRETS["AWS"]
    with pytest.deprecated_call():
        assert fetch_credentials("RedShift", "default", connection_type="master_password") == {"host": "master"}
    with pytest.deprecated_call():
        assert fetch_credentials(service_name="RedShift", connection="default") == SECRETS["RedShift"]["default"]


def test_fetch_credentials_path(secrets_file: Path) -> None:
    with pytest.deprecated_call():
        assert fetch_credentials("credentials_path") == str(secrets_file.parent)


def test_fetch_credentials_without_environment_variable() -> None:
    with pytest.deprecated_call(), pytest.raises(KeyError, match="CREDENTIALS_HOME"):
        fetch_credentials("AWS")


@pytest.mark.usefixtures("secrets_file")
def test_fetch_credentials_missing_service() -> None:
    with pytest.deprecated_call(), pytest.raises(KeyError):
        fetch_credentials("Google")


# -- code_location ----------------------------------------------------------------


@pytest.mark.usefixtures("secrets_file")
def test_code_location_from_file() -> None:
    assert code_location() == "local"


@pytest.mark.usefixtures("secrets_file")
def test_code_location_environment_variable_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSTACKUP_LOCATION", "production")
    assert code_location() == "production"


def test_code_location_not_set() -> None:
    assert code_location() is None


# -- unicode_to_ascii --------------------------------------------------------------


def test_unicode_to_ascii() -> None:
    """Converts every special character in Portuguese and Spanish to ASCII."""
    assert unicode_to_ascii("ÁÉÍÓÚÂÊÔÃÕÜÇÑáéíóúâêôãõüçñ") == "AEIOUAEOAOUCNaeiouaeoaoucn"
    assert unicode_to_ascii("plain text 123") == "plain text 123"


# -- parse_remote_uri --------------------------------------------------------------


@pytest.mark.parametrize("service", ["gs", "s3"])
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("sample_bucket", ("sample_bucket", "")),
        ("sample_bucket/", ("sample_bucket", "")),
        ("sample_bucket/sub1/sub2", ("sample_bucket", "sub1/sub2/")),
        ("sample_bucket/sub1/sub2/", ("sample_bucket", "sub1/sub2/")),
        ("sample_bucket/file.csv", ("sample_bucket", "file.csv/")),
    ],
)
def test_parse_remote_uri(service: str, path: str, expected: tuple[str, str]) -> None:
    assert parse_remote_uri(f"{service}://{path}", service) == expected


def test_parse_remote_uri_service_is_case_insensitive() -> None:
    assert parse_remote_uri("s3://bucket/a", "S3") == ("bucket", "a/")


@pytest.mark.parametrize(
    ("uri", "service"),
    [
        ("s3://sample_bucket", "gs"),
        ("gs://sample_bucket", "s3"),
        ("sample_bucket/folder", "gs"),
        ("gs:/sample_bucket", "gs"),
        ("gs://", "gs"),
        ("gs:///folder", "gs"),
    ],
)
def test_parse_remote_uri_invalid(uri: str, service: str) -> None:
    with pytest.raises(ValueError, match="Invalid service type"):
        parse_remote_uri(uri, service)
