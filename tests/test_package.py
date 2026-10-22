from __future__ import annotations

import logging
import subprocess
import sys

import pytest

import instackup


def test_version_is_set() -> None:
    assert instackup.__version__
    assert instackup.__version__ != "0.0.0"


def test_tools_are_importable_from_the_package_root() -> None:
    from instackup.sql_tools import SQLiteTool

    assert instackup.SQLiteTool is SQLiteTool
    for name in instackup.__all__:
        assert getattr(instackup, name) is not None
    assert set(instackup.__all__) <= set(dir(instackup))


def test_unknown_attribute() -> None:
    with pytest.raises(AttributeError, match="no_such_tool"):
        _ = instackup.no_such_tool


def test_importing_the_package_does_not_import_cloud_sdks() -> None:
    code = (
        "import sys, instackup, instackup.credentials, instackup.general_tools; "
        "heavy = [m for m in ('boto3', 'google.cloud.bigquery', 'gspread', 'psycopg2', 'mysql.connector') "
        "if m in sys.modules]; print(heavy)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]"


def test_library_does_not_configure_logging() -> None:
    handlers = logging.getLogger("instackup").handlers
    assert handlers
    assert all(isinstance(handler, logging.NullHandler) for handler in handlers)
