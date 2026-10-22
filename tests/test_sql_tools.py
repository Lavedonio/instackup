from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import mysql.connector
import pandas as pd
import psycopg2
import pytest

from instackup.credentials import CredentialsNotFoundError
from instackup.sql_tools import (
    MySQLTool,
    PostgreSQLTool,
    SQLiteTool,
    SQLTool,
    _mysql_connection_kwargs,
    parse_database_url,
    quote_identifier,
)


@pytest.fixture
def sqlite_db(tmp_path: Path) -> str:
    filename = str(tmp_path / "test.db")
    with SQLiteTool(filename) as db:
        db.execute_sql("CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT NOT NULL, score REAL)")
        db.execute_sql("INSERT INTO people (name, score) VALUES ('Ana', 9.5), ('Bruno', NULL)")
    return filename


# -- SQLite (real database) ----------------------------------------------------------


def test_sqlite_defaults_to_memory() -> None:
    assert SQLiteTool().filename == ":memory:"


def test_sqlite_query_as_dataframe(sqlite_db: str) -> None:
    with SQLiteTool(sqlite_db) as db:
        df = db.query("SELECT name, score FROM people ORDER BY id")
    assert isinstance(df, pd.DataFrame)
    assert df["name"].tolist() == ["Ana", "Bruno"]
    assert df["score"].iloc[0] == 9.5
    assert pd.isna(df["score"].iloc[1])


def test_sqlite_query_as_tuples_with_params(sqlite_db: str) -> None:
    with SQLiteTool(sqlite_db) as db:
        rows = db.query("SELECT id, name FROM people WHERE name = ?", fetch_through_pandas=False, params=("Bruno",))
    assert rows == [(2, "Bruno")]


def test_sqlite_query_keeps_backticks(sqlite_db: str) -> None:
    with SQLiteTool(sqlite_db) as db:
        assert db.query("SELECT `name` FROM `people` WHERE id = 1", fetch_through_pandas=False) == [("Ana",)]


def test_sqlite_query_without_result_set() -> None:
    with SQLiteTool() as db:
        df = db.query("CREATE TABLE t (a INTEGER)")
        assert isinstance(df, pd.DataFrame)
        assert df.empty
        assert db.query("CREATE TABLE u (a INTEGER)", fetch_through_pandas=False) == []


def test_sqlite_describe_table(sqlite_db: str) -> None:
    with SQLiteTool(sqlite_db) as db:
        info = db.describe_table("people")
    assert info["name"].tolist() == ["id", "name", "score"]
    assert info["type"].tolist() == ["INTEGER", "TEXT", "REAL"]
    assert info["notnull"].tolist() == [0, 1, 0]


def test_context_manager_commits(sqlite_db: str) -> None:
    with SQLiteTool(sqlite_db) as db:
        db.execute_sql("INSERT INTO people (name) VALUES (?)", params=("Carla",))
    with SQLiteTool(sqlite_db) as db:
        assert db.query("SELECT COUNT(*) FROM people", fetch_through_pandas=False) == [(3,)]


def test_context_manager_rolls_back_on_error(sqlite_db: str) -> None:
    db = SQLiteTool(sqlite_db)

    def insert_then_fail() -> None:
        with db:
            db.execute_sql("INSERT INTO people (name) VALUES ('Carla')")
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        insert_then_fail()
    assert db.connection is None
    with SQLiteTool(sqlite_db) as db:
        assert db.query("SELECT COUNT(*) FROM people", fetch_through_pandas=False) == [(2,)]


def test_manual_connection_lifecycle(sqlite_db: str) -> None:
    db = SQLiteTool(sqlite_db)
    assert db.connect() is db
    db.execute_sql("DELETE FROM people")
    db.rollback()
    db.commit()
    assert db.query("SELECT COUNT(*) FROM people", fetch_through_pandas=False) == [(2,)]
    db.close_connection()
    db.close_connection()  # Closing twice is harmless
    assert db.connection is None
    assert db.cursor is None


def test_errors_are_raised_by_default() -> None:
    with SQLiteTool() as db:
        with pytest.raises(sqlite3.OperationalError):
            db.query("SELECT * FROM missing")
        with pytest.raises(sqlite3.OperationalError):
            db.execute_sql("DROP TABLE missing")


def test_errors_can_fail_silently(caplog: pytest.LogCaptureFixture) -> None:
    with SQLiteTool() as db:
        assert db.query("SELECT * FROM missing", fail_silently=True) is None
        db.execute_sql("DROP TABLE missing", fail_silently=True)
    assert "Failing Silently" in caplog.text


def test_using_the_tool_before_connecting() -> None:
    db = SQLiteTool()
    with pytest.raises(RuntimeError, match="Not connected"):
        db.query("SELECT 1")
    with pytest.raises(RuntimeError, match="Not connected"):
        db.commit()


def test_connect_can_fail_silently(tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing" / "db.sqlite"
    assert SQLiteTool(str(missing_dir)).connect(fail_silently=True) is None
    with pytest.raises(sqlite3.OperationalError):
        SQLiteTool(str(missing_dir)).connect()


# -- PostgreSQL and MySQL (mocked drivers) -------------------------------------------


@pytest.fixture
def fake_cursor() -> MagicMock:
    cursor = MagicMock()
    cursor.description = [("id",), ("name",)]
    cursor.fetchall.return_value = [(1, "a")]
    return cursor


@pytest.fixture
def psycopg2_connect(monkeypatch: pytest.MonkeyPatch, fake_cursor: MagicMock) -> MagicMock:
    connect = MagicMock()
    connect.return_value.cursor.return_value = fake_cursor
    monkeypatch.setattr(psycopg2, "connect", connect)
    return connect


@pytest.fixture
def mysql_connect(monkeypatch: pytest.MonkeyPatch, fake_cursor: MagicMock) -> MagicMock:
    connect = MagicMock()
    connect.return_value.cursor.return_value = fake_cursor
    monkeypatch.setattr(mysql.connector, "connect", connect)
    return connect


def test_postgresql_uses_store_credentials(use_credentials, psycopg2_connect: MagicMock) -> None:
    use_credentials({"PostgreSQL": {"default": {"host": "db", "dbname": "app", "password": None, "port": 5432}}})
    PostgreSQLTool().connect()
    psycopg2_connect.assert_called_once_with(None, host="db", dbname="app", port=5432)


def test_postgresql_named_connection_with_url(use_credentials, psycopg2_connect: MagicMock) -> None:
    use_credentials({"postgresql": {"analytics": {"url": "postgresql://u:p@h/db", "sslmode": "require"}}})
    PostgreSQLTool(connection="analytics").connect()
    psycopg2_connect.assert_called_once_with("postgresql://u:p@h/db", sslmode="require")


def test_postgresql_explicit_credentials(psycopg2_connect: MagicMock) -> None:
    PostgreSQLTool(credentials={"dsn": "dbname=x"}).connect()
    psycopg2_connect.assert_called_once_with("dbname=x")


def test_missing_database_credentials(use_credentials) -> None:
    use_credentials({})
    with pytest.raises(CredentialsNotFoundError, match="PostgreSQL"):
        PostgreSQLTool()
    with pytest.raises(CredentialsNotFoundError, match="MySQL"):
        MySQLTool(connection="other")


def test_postgresql_strips_backticks(psycopg2_connect: MagicMock, fake_cursor: MagicMock) -> None:
    with PostgreSQLTool(credentials={}) as db:
        df = db.query("SELECT `id`, name FROM `t`")
    fake_cursor.execute.assert_called_once_with("SELECT id, name FROM t")
    assert df.to_dict("records") == [{"id": 1, "name": "a"}]


def test_postgresql_describe_table_is_parameterized(psycopg2_connect: MagicMock, fake_cursor: MagicMock) -> None:
    with PostgreSQLTool(credentials={}) as db:
        db.describe_table("people'; DROP TABLE x; --", schema="sales")
    sql, params = fake_cursor.execute.call_args.args
    assert "%s" in sql
    assert "DROP" not in sql
    assert params == ("sales", "people'; DROP TABLE x; --")


def test_driver_errors_respect_fail_silently(psycopg2_connect: MagicMock, fake_cursor: MagicMock) -> None:
    fake_cursor.execute.side_effect = psycopg2.ProgrammingError("bad")
    db = PostgreSQLTool(credentials={}).connect()
    assert db is not None
    assert db.query("SELECT 1", fail_silently=True) is None
    with pytest.raises(psycopg2.ProgrammingError):
        db.query("SELECT 1")


def test_mysql_connection_kwargs_translation(use_credentials, mysql_connect: MagicMock) -> None:
    use_credentials(
        {"MySQL": {"default": {"dbname": "mydb", "host": "h", "user": "root", "password": "", "port": "3306"}}}
    )
    MySQLTool().connect()
    mysql_connect.assert_called_once_with(database="mydb", host="h", user="root", password="", port=3306)


def test_mysql_describe_table_quotes_identifiers(mysql_connect: MagicMock, fake_cursor: MagicMock) -> None:
    with MySQLTool(credentials={}) as db:
        db.describe_table("shop.or`ders")
    fake_cursor.execute.assert_called_once_with("DESCRIBE `shop`.`or``ders`")


def test_base_class_dispatches_on_sql_type(mysql_connect: MagicMock) -> None:
    SQLTool("MySQL", credentials={"host": "h"}).connect()
    mysql_connect.assert_called_once_with(host="h")


# -- get_all_db_info -------------------------------------------------------------------


def test_get_all_db_info_adds_json_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    columns = pd.DataFrame(
        {
            "table_catalog": ["db", "db"],
            "table_schema": ["public", "public"],
            "table_name": ["t", "t"],
            "column_name": ["id", "payload"],
            "data_type": ["integer", "jsonb"],
            "is_nullable": ["NO", "YES"],
        }
    )
    json_keys = pd.DataFrame({"key": ["a", "b"], "json_value_data_type": ["string", "number"], "count": [3, 1]})
    queries: list[str] = []

    def fake_query(self: PostgreSQLTool, sql: str) -> pd.DataFrame:
        queries.append(sql)
        return columns if len(queries) == 1 else json_keys

    monkeypatch.setattr(PostgreSQLTool, "_query_dataframe", fake_query)
    result = PostgreSQLTool(credentials={}).get_all_db_info()

    assert 'FROM "public"."t" AS t, jsonb_each(t."payload")' in queries[1]
    assert result.columns.tolist() == [
        "table_catalog",
        "table_schema",
        "table_name",
        "column_name",
        "data_type",
        "json_key",
        "json_value_type",
        "is_nullable",
    ]
    assert result[["column_name", "json_key", "json_value_type"]].values.tolist() == [
        ["id", "", ""],
        ["payload", "", ""],
        ["payload", "a", "string"],
        ["payload", "b", "number"],
    ]


def test_get_all_db_info_without_json_info(psycopg2_connect: MagicMock, fake_cursor: MagicMock) -> None:
    with PostgreSQLTool(credentials={}) as db:
        assert db.get_all_db_info(get_json_info=False, fetch_through_pandas=False) == [(1, "a")]


# -- Helpers -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "mysql://user:p%40ss@db.example.com:3307/shop",
            {"host": "db.example.com", "port": 3307, "user": "user", "password": "p@ss", "database": "shop"},
        ),
        ("mysql://localhost", {"host": "localhost"}),
    ],
)
def test_parse_database_url(url: str, expected: dict[str, Any]) -> None:
    assert parse_database_url(url) == expected


def test_mysql_connection_kwargs_url_is_overridden_by_explicit_settings() -> None:
    assert _mysql_connection_kwargs({"url": "mysql://u:p@h:1/db", "password": "other", "dbname": None}) == {
        "host": "h",
        "port": 1,
        "user": "u",
        "password": "other",
        "database": "db",
    }


def test_quote_identifier() -> None:
    assert quote_identifier('we"ird') == '"we""ird"'
    assert quote_identifier("t", quote="`") == "`t`"
