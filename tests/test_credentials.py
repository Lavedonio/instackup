from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

from instackup import credentials
from instackup.credentials import (
    AWSSecretsManagerSource,
    CredentialsError,
    CredentialsNotFoundError,
    CredentialStore,
    EnvironmentSource,
    FileSource,
    GCPSecretManagerSource,
    MappingSource,
    get_credentials,
    get_default_store,
    lookup_connection,
    parse_document,
    set_default_store,
)

from .conftest import CREDENTIAL_TEMPLATES


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# -- Documents and sources ------------------------------------------------------


def test_parse_document_detects_json_and_yaml() -> None:
    assert parse_document('{"a": {"b": 1}}') == {"a": {"b": 1}}
    assert parse_document("a:\n  b: 1\n") == {"a": {"b": 1}}
    assert parse_document("") == {}


@pytest.mark.parametrize(("text", "message"), [("a: [", "not valid YAML"), ("- 1\n- 2\n", "must be a mapping")])
def test_parse_document_rejects_invalid_documents(text: str, message: str) -> None:
    with pytest.raises(CredentialsError, match=message):
        parse_document(text)


@pytest.mark.parametrize(
    "template", ["secret_template.yml", "secret_template.json", "secret_blank.yml", "secret_blank.json"]
)
def test_credential_templates_are_valid(template: str) -> None:
    store = CredentialStore.from_file(CREDENTIAL_TEMPLATES / template)
    assert store.get_value("location") == "local"
    assert store.get("postgresql")["dbname"] == "postgres"
    assert set(store.get("redshift")) >= {"cluster_credentials", "master_password"}


def test_file_source_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CredentialsError, match="not found"):
        FileSource(tmp_path / "missing.yml").load()


def test_mapping_source_returns_copies() -> None:
    source = MappingSource({"aws": {"default": {"region": "us-east-1"}}})
    source.load()["aws"]["default"]["region"] = "changed"
    assert source.load()["aws"]["default"]["region"] == "us-east-1"


def test_environment_source_parses_nested_variables() -> None:
    environ = {
        "INSTACKUP_POSTGRESQL__DEFAULT__PASSWORD": "s3cret",
        "INSTACKUP_POSTGRESQL__ANALYTICS__URL": "postgresql://x",
        "INSTACKUP_REDSHIFT__DEFAULT__MASTER_PASSWORD__HOST": "cluster",
        "INSTACKUP_LOCATION": "production",
        "INSTACKUP_CREDENTIALS_FILE": "/ignored.yml",  # A setting, not a credential
        "INSTACKUP_ONLY__TWO": "ignored",
        "OTHER_VARIABLE": "ignored",
    }
    assert EnvironmentSource(environ).load() == {
        "postgresql": {"default": {"password": "s3cret"}, "analytics": {"url": "postgresql://x"}},
        "redshift": {"default": {"master_password": {"host": "cluster"}}},
        "location": "production",
    }


def test_environment_source_rejects_conflicting_variables() -> None:
    environ = {"INSTACKUP_AWS__DEFAULT__REGION": "x", "INSTACKUP_AWS__DEFAULT__REGION__NAME": "y"}
    with pytest.raises(CredentialsError, match="conflicts"):
        EnvironmentSource(environ).load()


# -- Store lookups ------------------------------------------------------------


def test_names_are_case_insensitive() -> None:
    store = CredentialStore.from_mapping({"PostgreSQL": {"Default": {"host": "db"}}, "Location": "local"})
    assert store.get("POSTGRESQL", "DEFAULT") == {"host": "db"}
    assert store.get_value("LOCATION") == "local"


def test_get_missing_connection() -> None:
    store = CredentialStore.from_mapping({"postgresql": {"default": {"host": "db"}}})
    assert store.get("postgresql", "other") is None
    assert store.get("mysql") is None
    with pytest.raises(CredentialsNotFoundError, match="'mysql'") as excinfo:
        store.get("mysql", required=True)
    assert isinstance(excinfo.value, KeyError)  # Backwards compatible with instackup < 0.4


def test_get_rejects_non_mapping_connection() -> None:
    store = CredentialStore.from_mapping({"postgresql": {"default": "oops"}})
    with pytest.raises(CredentialsError, match="must be a mapping"):
        store.get("postgresql")


def test_get_returns_copies() -> None:
    store = CredentialStore.from_mapping({"aws": {"default": {"region": "us-east-1"}}})
    store.get("aws")["region"] = "changed"
    assert store.get("aws") == {"region": "us-east-1"}


def test_get_service_and_get_value() -> None:
    store = CredentialStore.from_mapping(
        {
            "google": {"default": {"project_id": "a"}, "other": {"project_id": "b"}},
            "custom": {"anything": [1, 2]},
        }
    )
    assert store.get_service("google") == {"default": {"project_id": "a"}, "other": {"project_id": "b"}}
    assert store.get_service("missing") == {}
    assert store.get_value("custom") == {"anything": [1, 2]}
    assert store.get_value("missing", "fallback") == "fallback"


def test_sources_are_merged_with_first_source_winning(tmp_path: Path) -> None:
    file = write(
        tmp_path / "creds.yml", "PostgreSQL:\n  default:\n    host: db\n    user: etl\n    password: from-file\n"
    )
    environ = {"INSTACKUP_POSTGRESQL__DEFAULT__PASSWORD": "from-env"}
    store = CredentialStore([EnvironmentSource(environ), FileSource(file)])
    assert store.get("postgresql") == {"host": "db", "user": "etl", "password": "from-env"}


def test_sources_load_lazily_once_until_reload() -> None:
    source = MagicMock(spec=["load"])
    source.load.return_value = {"aws": {"default": {"region": "a"}}}
    store = CredentialStore([source])
    source.load.assert_not_called()

    store.get("aws")
    store.get("aws")
    assert source.load.call_count == 1

    source.load.return_value = {"aws": {"default": {"region": "b"}}}
    store.reload()
    assert store.get("aws") == {"region": "b"}


def test_resolve_path(tmp_path: Path) -> None:
    file_store = CredentialStore.from_file(write(tmp_path / "creds.yml", "{}"))
    assert file_store.base_dir == tmp_path.resolve()
    assert file_store.resolve_path("key.json") == tmp_path.resolve() / "key.json"
    absolute = tmp_path / "elsewhere" / "key.json"
    assert file_store.resolve_path(absolute) == absolute
    assert CredentialStore.from_mapping({}).resolve_path("key.json") == Path.cwd() / "key.json"


# -- Environment variable references in files ------------------------------------


def test_file_values_expand_environment_variables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_PASSWORD", "s3cret")
    monkeypatch.setenv("EMPTY_VALUE", "")
    file = write(
        tmp_path / "creds.yml",
        "postgresql:\n"
        "  default:\n"
        "    password: ${PG_PASSWORD}\n"
        "    url: postgresql://u:${PG_PASSWORD}@h/${DB_NAME:-db}\n"
        "    sslmode: ${EMPTY_VALUE:-require}\n"
        "    raw: ${EMPTY_VALUE}\n"
        "    hosts: ['${PG_PASSWORD}']\n",
    )
    assert CredentialStore.from_file(file).get("postgresql") == {
        "password": "s3cret",
        "url": "postgresql://u:s3cret@h/db",
        "sslmode": "require",
        "raw": "",
        "hosts": ["s3cret"],
    }


def test_unset_variables_make_the_value_missing(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    file = write(tmp_path / "creds.yml", "mysql:\n  default:\n    user: me\n    password: pa${UNSET}ss\n")
    assert CredentialStore.from_file(file).get("mysql") == {"user": "me", "password": None}
    assert "UNSET" in caplog.text


def test_values_from_other_sources_are_not_expanded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X", "expanded")
    store = CredentialStore([EnvironmentSource({"INSTACKUP_MYSQL__DEFAULT__PASSWORD": "pa${X}ss"})])
    assert store.get("mysql") == {"password": "pa${X}ss"}


# -- Secret managers ----------------------------------------------------------------


@mock_aws
@pytest.mark.usefixtures("aws_test_credentials")
def test_aws_secrets_manager_source() -> None:
    client = boto3.client("secretsmanager")
    client.create_secret(Name="instackup", SecretString=json.dumps({"MySQL": {"default": {"password": "pw"}}}))
    client.create_secret(Name="binary", SecretBinary=b"aws:\n  default:\n    region: eu-west-1\n")

    assert AWSSecretsManagerSource("instackup").load() == {"MySQL": {"default": {"password": "pw"}}}
    assert AWSSecretsManagerSource("binary", session=boto3.Session()).load() == {
        "aws": {"default": {"region": "eu-west-1"}}
    }


def test_gcp_secret_manager_source() -> None:
    client = MagicMock()
    client.access_secret_version.return_value = SimpleNamespace(payload=SimpleNamespace(data=b'{"aws": {}}'))

    assert GCPSecretManagerSource("projects/p/secrets/s", client=client).load() == {"aws": {}}
    client.access_secret_version.assert_called_once_with(name="projects/p/secrets/s/versions/latest")
    assert GCPSecretManagerSource("projects/p/secrets/s/versions/3").name == "projects/p/secrets/s/versions/3"


# -- Default store ----------------------------------------------------------------


def test_from_environment_sources(tmp_path: Path) -> None:
    store = CredentialStore.from_environment(
        {
            "INSTACKUP_AWS_SECRET_ID": "aws-secret",
            "INSTACKUP_GCP_SECRET_NAME": "projects/p/secrets/s",
            "INSTACKUP_CREDENTIALS_FILE": str(tmp_path / "new.yml"),
            "CREDENTIALS_HOME": str(tmp_path / "legacy.yml"),
        }
    )
    kinds = [type(source) for source in store.sources]
    assert kinds == [EnvironmentSource, AWSSecretsManagerSource, GCPSecretManagerSource, FileSource]
    assert store.sources[-1].path == tmp_path / "new.yml"

    legacy = CredentialStore.from_environment({"CREDENTIALS_HOME": str(tmp_path / "legacy.yml")})
    assert legacy.sources[-1].path == tmp_path / "legacy.yml"
    assert [type(source) for source in CredentialStore.from_environment({}).sources] == [EnvironmentSource]


def test_default_store_is_built_from_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = write(tmp_path / "creds.yml", "Location: remote\nAWS:\n  default:\n    region: x\n")
    monkeypatch.setenv("CREDENTIALS_HOME", str(file))

    assert get_default_store() is get_default_store()
    assert get_credentials("aws") == {"region": "x"}

    custom = CredentialStore.from_mapping({"aws": {"default": {"region": "y"}}})
    set_default_store(custom)
    assert get_default_store() is custom
    assert get_credentials("aws") == {"region": "y"}

    set_default_store(None)
    assert get_credentials("aws") == {"region": "x"}


def test_lookup_connection_rules(use_credentials) -> None:
    use_credentials({"aws": {"default": {"region": "x"}, "prod": {"region": "y"}}})
    assert lookup_connection("aws", "prod", None) == {"region": "y"}
    assert lookup_connection("aws", "anything", {"explicit": True}) == {"explicit": True}
    with pytest.raises(CredentialsNotFoundError):
        lookup_connection("aws", "staging", None)

    use_credentials({})
    assert lookup_connection("aws", "default", None) is None  # Use the platform's ambient credentials
    assert lookup_connection("aws", "DEFAULT", None) is None


def test_module_exports() -> None:
    for name in credentials.__all__:
        assert hasattr(credentials, name)
