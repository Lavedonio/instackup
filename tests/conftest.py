from __future__ import annotations

import os
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from instackup.credentials import CredentialStore, set_default_store

REPO_ROOT = Path(__file__).resolve().parent.parent
CREDENTIAL_TEMPLATES = REPO_ROOT / "credentials"

# Variables that change how instackup or cloud SDKs find credentials.
_ISOLATED_PREFIXES = ("INSTACKUP_", "AWS_", "GOOGLE_", "CLOUDSDK_")
_ISOLATED_NAMES = ("CREDENTIALS_HOME",)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Keep the developer's real credentials out of every test.

    Removes credential-related environment variables, points AWS config files to an
    empty location and resets the process-wide credential store before and after.
    """
    for name in list(os.environ):
        if name.startswith(_ISOLATED_PREFIXES) or name in _ISOLATED_NAMES:
            monkeypatch.delenv(name)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "aws_config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "aws_credentials"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")

    set_default_store(None)
    yield
    set_default_store(None)


@pytest.fixture
def use_credentials() -> Callable[[Mapping[str, Any]], CredentialStore]:
    """Install an in-memory credential store as the default one: ``use_credentials({...})``."""

    def install(data: Mapping[str, Any]) -> CredentialStore:
        store = CredentialStore.from_mapping(data)
        set_default_store(store)
        return store

    return install


@pytest.fixture
def aws_test_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake AWS credentials and region for moto-backed tests."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
