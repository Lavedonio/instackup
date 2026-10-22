"""Tests against real PostgreSQL and MySQL servers.

Skipped unless ``TEST_POSTGRESQL_URL`` / ``TEST_MYSQL_URL`` are set, e.g.::

    docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:17
    TEST_POSTGRESQL_URL=postgresql://postgres:postgres@localhost:5432/postgres pytest -m integration
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pandas as pd
import pytest

from instackup.sql_tools import MySQLTool, PostgreSQLTool

pytestmark = pytest.mark.integration

# Read at import time: the autouse fixture in conftest.py clears unrelated env vars per test.
POSTGRESQL_URL = os.environ.get("TEST_POSTGRESQL_URL")
MYSQL_URL = os.environ.get("TEST_MYSQL_URL")


@pytest.fixture
def table_name() -> str:
    return f"instackup_test_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def postgresql(monkeypatch: pytest.MonkeyPatch, table_name: str) -> Iterator[PostgreSQLTool]:
    if not POSTGRESQL_URL:
        pytest.skip("TEST_POSTGRESQL_URL not set")
    # Configured exactly like a production deployment would: through environment variables.
    monkeypatch.setenv("INSTACKUP_POSTGRESQL__DEFAULT__URL", POSTGRESQL_URL)
    with PostgreSQLTool() as db:
        yield db
    with PostgreSQLTool() as db:
        db.execute_sql(f'DROP TABLE IF EXISTS "{table_name}"')


@pytest.fixture
def mysql(monkeypatch: pytest.MonkeyPatch, table_name: str) -> Iterator[MySQLTool]:
    if not MYSQL_URL:
        pytest.skip("TEST_MYSQL_URL not set")
    monkeypatch.setenv("INSTACKUP_MYSQL__DEFAULT__URL", MYSQL_URL)
    with MySQLTool() as db:
        yield db
    with MySQLTool() as db:
        db.execute_sql(f"DROP TABLE IF EXISTS `{table_name}`")


def test_postgresql_round_trip(postgresql: PostgreSQLTool, table_name: str) -> None:
    postgresql.execute_sql(f'CREATE TABLE "{table_name}" (id SERIAL PRIMARY KEY, name TEXT NOT NULL, price NUMERIC)')
    postgresql.execute_sql(
        f'INSERT INTO "{table_name}" (name, price) VALUES (%s, %s), (%s, %s)', params=("a", 1.5, "b", None)
    )

    df = postgresql.query(f"SELECT name, price FROM `{table_name}` ORDER BY id")
    assert isinstance(df, pd.DataFrame)
    assert df["name"].tolist() == ["a", "b"]
    assert df["price"].iloc[0] == 1.5

    rows = postgresql.query(
        f'SELECT name FROM "{table_name}" WHERE name = %s', fetch_through_pandas=False, params=("b",)
    )
    assert rows == [("b",)]

    info = postgresql.describe_table(table_name)
    assert isinstance(info, pd.DataFrame)
    assert set(info["column_name"]) == {"id", "name", "price"}


def test_postgresql_json_schema_to_bigquery(postgresql: PostgreSQLTool, table_name: str) -> None:
    bigquery_tools = pytest.importorskip("instackup.bigquery_tools")
    postgresql.execute_sql(f'CREATE TABLE "{table_name}" (id INTEGER NOT NULL, payload JSONB, notes TEXT)')
    postgresql.execute_sql(
        f"""INSERT INTO "{table_name}" VALUES (1, '{{"a": "x", "b": 2}}', NULL), (2, '[1, 2]', 'array payload')"""
    )
    postgresql.commit()

    info = postgresql.get_all_db_info()
    assert isinstance(info, pd.DataFrame)
    table_info = info[info["table_name"] == table_name]
    assert sorted(table_info["json_key"]) == ["", "", "", "a", "b"]

    schema = bigquery_tools.BigQueryTool.convert_postgresql_table_schema(table_info)
    assert schema == {
        "fields": [
            {"type": "INTEGER", "name": "id", "mode": "REQUIRED"},
            {"type": "STRING", "name": "notes", "mode": "NULLABLE"},
            {
                "type": "RECORD",
                "name": "payload",
                "mode": "NULLABLE",
                "fields": [
                    {"type": "STRING", "name": "a", "mode": "NULLABLE"},
                    {"type": "NUMERIC", "name": "b", "mode": "NULLABLE"},
                ],
            },
        ]
    }


def test_mysql_round_trip(mysql: MySQLTool, table_name: str) -> None:
    mysql.execute_sql(f"CREATE TABLE `{table_name}` (id INT AUTO_INCREMENT PRIMARY KEY, `order` VARCHAR(20))")
    mysql.execute_sql(f"INSERT INTO `{table_name}` (`order`) VALUES (%s), (%s)", params=("first", "second"))

    df = mysql.query(f"SELECT `order` FROM `{table_name}` ORDER BY id")
    assert isinstance(df, pd.DataFrame)
    assert df["order"].tolist() == ["first", "second"]

    info = mysql.describe_table(table_name)
    assert isinstance(info, pd.DataFrame)
    assert info["Field"].tolist() == ["id", "order"]
