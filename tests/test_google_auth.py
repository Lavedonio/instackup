from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, sentinel

import pytest

from instackup import _google
from instackup._google import GoogleAuth, resolve_google_auth
from instackup.credentials import CredentialsNotFoundError, CredentialStore, set_default_store

SERVICE_ACCOUNT = {
    "type": "service_account",
    "project_id": "sa-project",
    "client_email": "loader@sa-project.iam.gserviceaccount.com",
}
SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)

UseCredentials = Callable[[Mapping[str, Any]], CredentialStore]


@pytest.fixture
def google_api(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Fakes for ADC and the two service-account constructors."""
    api = SimpleNamespace(
        adc=MagicMock(return_value=(sentinel.adc_credentials, "adc-project")),
        from_info=MagicMock(return_value=sentinel.info_credentials),
        file_credentials=SimpleNamespace(project_id="file-project"),
    )
    api.from_file = MagicMock(return_value=api.file_credentials)
    monkeypatch.setattr(_google.google.auth, "default", api.adc)
    monkeypatch.setattr(_google.service_account.Credentials, "from_service_account_info", api.from_info)
    monkeypatch.setattr(_google.service_account.Credentials, "from_service_account_file", api.from_file)
    return api


def key_file_used(google_api: SimpleNamespace) -> Path:
    google_api.from_file.assert_called_once()
    return Path(google_api.from_file.call_args.args[0])


def write_credentials_file(directory: Path, content: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "credentials.yaml"
    path.write_text(content)
    return path


# -- Inline service account info -----------------------------------------------


@pytest.mark.parametrize("info", [SERVICE_ACCOUNT, json.dumps(SERVICE_ACCOUNT)], ids=["dict", "json"])
def test_inline_service_account_info_from_store(
    google_api: SimpleNamespace, use_credentials: UseCredentials, info: Any
) -> None:
    use_credentials({"google": {"default": {"service_account_info": info}}})

    auth = resolve_google_auth()

    google_api.from_info.assert_called_once_with(SERVICE_ACCOUNT, scopes=None)
    google_api.adc.assert_not_called()
    assert auth.credentials is sentinel.info_credentials
    assert auth.project_id == "sa-project"


def test_project_settings_override_service_account_project(google_api: SimpleNamespace) -> None:
    auth = resolve_google_auth(
        credentials={
            "service_account_info": json.dumps(SERVICE_ACCOUNT),
            "project_id": "other-project",
            "project_name": "Other",
            "project_number": "123",
        }
    )

    assert auth.project_id == "other-project"
    assert auth.project_info == {"id": "other-project", "name": "Other", "number": "123"}


def test_inline_info_takes_precedence_over_key_file(google_api: SimpleNamespace) -> None:
    resolve_google_auth(credentials={"service_account_info": SERVICE_ACCOUNT, "service_account_file": "sa.json"})

    google_api.from_info.assert_called_once()
    google_api.from_file.assert_not_called()


def test_named_connection_from_store(google_api: SimpleNamespace, use_credentials: UseCredentials) -> None:
    use_credentials(
        {
            "google": {
                "default": {"project_id": "default-project"},
                "Analytics": {"service_account_info": SERVICE_ACCOUNT},
            }
        }
    )

    auth = resolve_google_auth("analytics")

    assert auth.credentials is sentinel.info_credentials
    assert auth.project_id == "sa-project"


# -- Key files -----------------------------------------------------------------


@pytest.mark.parametrize("setting", ["service_account_file", "secret_filename"])
def test_relative_key_file_from_store_resolves_against_credentials_file(
    google_api: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: str
) -> None:
    config_dir = tmp_path / "config"
    credentials_file = write_credentials_file(config_dir, f"google:\n  default:\n    {setting}: keys/sa.json\n")
    set_default_store(CredentialStore.from_file(credentials_file))
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")

    auth = resolve_google_auth()

    assert key_file_used(google_api).resolve() == (config_dir / "keys" / "sa.json").resolve()
    google_api.adc.assert_not_called()
    assert auth.credentials is google_api.file_credentials
    assert auth.project_id == "file-project"


def set_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # Used by expanduser() on Windows


def test_absolute_and_home_key_files_from_store(
    google_api: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_home(monkeypatch, tmp_path / "home")
    credentials_file = write_credentials_file(
        tmp_path / "config",
        f"google:\n  default:\n    service_account_file: ~/sa.json\n"
        f"  absolute:\n    service_account_file: {tmp_path / 'keys' / 'sa.json'}\n",
    )
    set_default_store(CredentialStore.from_file(credentials_file))

    resolve_google_auth()
    assert key_file_used(google_api) == tmp_path / "home" / "sa.json"

    google_api.from_file.reset_mock()
    resolve_google_auth("absolute")
    assert key_file_used(google_api) == tmp_path / "keys" / "sa.json"


@pytest.mark.parametrize("setting", ["service_account_file", "secret_filename"])
def test_relative_key_file_in_explicit_credentials_resolves_against_cwd(
    google_api: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: str
) -> None:
    credentials_file = write_credentials_file(
        tmp_path / "config", "google:\n  default:\n    service_account_file: keys/store.json\n"
    )
    set_default_store(CredentialStore.from_file(credentials_file))
    monkeypatch.chdir(tmp_path)

    auth = resolve_google_auth(credentials={setting: "keys/sa.json"})

    assert key_file_used(google_api).resolve() == (tmp_path / "keys" / "sa.json").resolve()
    assert auth.project_id == "file-project"
    assert auth.project_info == {"id": "file-project", "name": None, "number": None}


def test_explicit_key_file_expands_home(
    google_api: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_home(monkeypatch, tmp_path)

    resolve_google_auth(credentials={"service_account_file": "~/sa.json"})

    assert key_file_used(google_api) == tmp_path / "sa.json"


# -- Application Default Credentials -------------------------------------------


def test_falls_back_to_application_default_credentials(google_api: SimpleNamespace) -> None:
    auth = resolve_google_auth()

    google_api.adc.assert_called_once_with(scopes=None)
    google_api.from_info.assert_not_called()
    google_api.from_file.assert_not_called()
    assert auth == GoogleAuth(credentials=sentinel.adc_credentials, project_id="adc-project", project_info=None)


def test_application_default_credentials_with_configured_project(
    google_api: SimpleNamespace, use_credentials: UseCredentials
) -> None:
    use_credentials({"google": {"default": {"project_id": "configured", "project_name": "Configured"}}})

    auth = resolve_google_auth()

    assert auth == GoogleAuth(
        credentials=sentinel.adc_credentials,
        project_id="configured",
        project_info={"id": "configured", "name": "Configured", "number": None},
    )


def test_missing_named_connection_is_an_error(google_api: SimpleNamespace, use_credentials: UseCredentials) -> None:
    use_credentials({"google": {"default": {"service_account_info": SERVICE_ACCOUNT}}})

    with pytest.raises(CredentialsNotFoundError, match="service 'google', connection 'analytics'") as excinfo:
        resolve_google_auth("analytics")

    assert isinstance(excinfo.value, KeyError)
    google_api.adc.assert_not_called()


@pytest.mark.parametrize("connection", ["default", "missing"])
def test_use_config_false_skips_the_store(
    google_api: SimpleNamespace, use_credentials: UseCredentials, connection: str
) -> None:
    use_credentials({"google": {"default": {"service_account_info": SERVICE_ACCOUNT, "project_id": "configured"}}})

    auth = resolve_google_auth(connection, use_config=False)

    google_api.from_info.assert_not_called()
    assert auth == GoogleAuth(credentials=sentinel.adc_credentials, project_id="adc-project", project_info=None)


def test_explicit_credentials_are_used_even_without_config(google_api: SimpleNamespace) -> None:
    auth = resolve_google_auth(credentials={"service_account_info": SERVICE_ACCOUNT}, use_config=False)

    google_api.from_info.assert_called_once()
    google_api.adc.assert_not_called()
    assert auth.project_info is not None


@pytest.mark.parametrize(
    ("credentials", "api"),
    [
        ({"service_account_info": SERVICE_ACCOUNT}, "from_info"),
        ({"service_account_file": "/keys/sa.json"}, "from_file"),
        ({}, "adc"),
    ],
)
def test_scopes_are_passed_through(google_api: SimpleNamespace, credentials: dict[str, Any], api: str) -> None:
    resolve_google_auth(credentials=credentials, scopes=SCOPES)

    assert getattr(google_api, api).call_args.kwargs["scopes"] == SCOPES
