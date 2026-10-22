"""Tools for SQL databases: SQLite, PostgreSQL and MySQL.

Database drivers are imported only when a connection is opened, so ``SQLiteTool``
works without the ``postgresql`` or ``mysql`` extras installed.
"""

from __future__ import annotations

import functools
import importlib
import logging
import sqlite3
from collections.abc import Mapping, Sequence
from types import ModuleType, TracebackType
from typing import Any, Self
from urllib.parse import unquote, urlsplit

import pandas as pd

from ._utils import missing_extra_message
from .credentials import get_default_store

logger = logging.getLogger(__name__)

QueryParams = Sequence[Any] | Mapping[str, Any]

# Databases that reject backtick-quoted identifiers; backticks are stripped from their queries.
_POSTGRESQL_FAMILY = frozenset({"PostgreSQL", "RedShift"})


class SQLTool:
    """Base class for the different types of SQL databases.

    Connection settings come from ``credentials`` when given, otherwise from the
    credential store under the ``sql_type`` service (e.g. ``postgresql.default``).
    Besides the driver's own keyword arguments, a ``url`` setting
    (``postgresql://user:pass@host:5432/db``) is accepted.
    """

    def __init__(
        self,
        sql_type: str,
        filename: str | None = None,
        connection: str = "default",
        *,
        credentials: Mapping[str, Any] | None = None,
    ) -> None:
        sql_credentials: dict[str, Any]
        if sql_type == "SQLite":
            sql_credentials = {}
            if filename is None:
                filename = ":memory:"
        elif credentials is not None:
            sql_credentials = dict(credentials)
        else:
            sql_credentials = get_default_store().get(sql_type, connection, required=True) or {}

        self.sql_type = sql_type
        self.filename = filename  # SQLite only
        self.connection_parameters = sql_credentials

        # Set when connected
        self.connection: Any = None
        self.cursor: Any = None

    def _open_connection(self) -> Any:
        if self.sql_type == "SQLite":
            return sqlite3.connect(self.filename or ":memory:")
        if self.sql_type == "MySQL":
            return _import_driver("mysql.connector", "mysql").connect(
                **_mysql_connection_kwargs(self.connection_parameters)
            )
        return _connect_postgresql(self.connection_parameters)

    def connect(self, fail_silently: bool = False) -> Self | None:
        """Open the connection.

        If ``fail_silently`` is True, errors are logged instead of raised and ``None`` is returned.
        """
        try:
            conn = self._open_connection()
        except _database_errors() as e:
            logger.exception("Failed to open database connection.")
            if not fail_silently:
                raise e
            logger.error("ATTENTION: Failing Silently")
            return None

        logger.info("Connected!")
        self.connection = conn
        self.cursor = conn.cursor()
        return self

    def commit(self) -> None:
        """Commit any pending transaction to the database."""
        self._require_connection().commit()
        logger.info("Transaction committed.")

    def rollback(self) -> None:
        """Roll back to the start of any pending transaction."""
        self._require_connection().rollback()
        logger.info("Rolled back current transaction.")

    def execute_sql(self, command: str, fail_silently: bool = False, *, params: QueryParams | None = None) -> None:
        """Execute a SQL command (CREATE, UPDATE, DROP...).

        ``params`` are bound by the driver; use the driver's placeholder style
        (``?`` for SQLite, ``%s`` for PostgreSQL and MySQL). If ``fail_silently`` is
        True, errors are logged instead of raised.
        """
        self._run(command, params, fail_silently=fail_silently, error_message="Error running command!")

    def query(
        self,
        sql_query: str,
        fetch_through_pandas: bool = True,
        fail_silently: bool = False,
        *,
        params: QueryParams | None = None,
    ) -> pd.DataFrame | list[tuple[Any, ...]] | None:
        """Run a query and return its results.

        Returns a DataFrame if ``fetch_through_pandas`` is True, otherwise a list of
        tuples, one per row, with values in the order of the SELECT columns. If
        ``fail_silently`` is True, errors are logged and ``None`` is returned.
        ``params`` work as in :meth:`execute_sql`.
        """
        if self.sql_type in _POSTGRESQL_FAMILY:
            # Backtick table quotes (BigQuery/MySQL style) can't be handled by PostgreSQL.
            sql_query = sql_query.replace("`", "")

        if not self._run(sql_query, params, fail_silently=fail_silently, error_message="Error running query!"):
            return None

        cursor = self.cursor
        if cursor.description is None:  # Statement didn't produce a result set
            rows: list[tuple[Any, ...]] = []
            columns: list[str] = []
        else:
            rows = [tuple(row) for row in cursor.fetchall()]
            columns = [column[0] for column in cursor.description]

        if not fetch_through_pandas:
            return rows
        return pd.DataFrame.from_records(rows, columns=columns, coerce_float=True)

    def _run(
        self,
        sql: str,
        params: QueryParams | None,
        *,
        fail_silently: bool,
        error_message: str,
        log_sql: bool = True,
    ) -> bool:
        """Execute a statement on the cursor, returning whether it succeeded."""
        self._require_connection()
        try:
            if params is None:
                self.cursor.execute(sql)
            else:
                self.cursor.execute(sql, params)
        except _database_errors() as e:
            logger.exception(error_message)
            if not fail_silently:
                raise e
            logger.error("ATTENTION: Failing Silently")
            return False

        if log_sql:
            logger.debug("Statement executed: %s", sql)
        return True

    def close_connection(self) -> None:
        """Close the connection with the database."""
        if self.connection is not None:
            self.connection.close()
            logger.info("Connection closed.")
        self.connection = None
        self.cursor = None

    def _require_connection(self) -> Any:
        if self.connection is None:
            raise RuntimeError("Not connected to the database. Call connect() first or use a 'with' block.")
        return self.connection

    def __enter__(self) -> Self:
        if self.connect() is None:  # pragma: no cover - connect() raises unless failing silently
            raise RuntimeError("Could not connect to the database.")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.connection is None:
            return
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close_connection()


class SQLiteTool(SQLTool):
    """Handles most of the interaction needed with SQLite3 databases."""

    def __init__(self, filename: str | None = None) -> None:
        super().__init__("SQLite", filename=filename)

    def describe_table(
        self, table: str, fetch_through_pandas: bool = True, fail_silently: bool = False
    ) -> pd.DataFrame | list[tuple[Any, ...]] | None:
        """Column metadata of a table (``PRAGMA table_info``): cid, name, type, notnull, dflt_value and pk."""
        sql_query = f"PRAGMA table_info({quote_identifier(table)})"
        return self.query(sql_query, fetch_through_pandas=fetch_through_pandas, fail_silently=fail_silently)


class MySQLTool(SQLTool):
    """Handles most of the interaction needed with MySQL databases."""

    def __init__(self, connection: str = "default", *, credentials: Mapping[str, Any] | None = None) -> None:
        super().__init__("MySQL", connection=connection, credentials=credentials)

    def describe_table(
        self, table: str, fetch_through_pandas: bool = True, fail_silently: bool = False
    ) -> pd.DataFrame | list[tuple[Any, ...]] | None:
        """Column metadata of a table (``DESCRIBE``). Accepts ``table`` or ``schema.table``."""
        table_name = ".".join(quote_identifier(part, quote="`") for part in table.split("."))
        return self.query(
            f"DESCRIBE {table_name}", fetch_through_pandas=fetch_through_pandas, fail_silently=fail_silently
        )


class PostgreSQLTool(SQLTool):
    """Handles most of the interaction needed with PostgreSQL databases."""

    def __init__(self, connection: str = "default", *, credentials: Mapping[str, Any] | None = None) -> None:
        super().__init__("PostgreSQL", connection=connection, credentials=credentials)

    def describe_table(
        self,
        table: str,
        schema: str = "public",
        fetch_through_pandas: bool = True,
        fail_silently: bool = False,
    ) -> pd.DataFrame | list[tuple[Any, ...]] | None:
        """All INFORMATION_SCHEMA.COLUMNS metadata of a table."""
        sql_query = "SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE table_schema = %s AND table_name = %s"
        return self.query(
            sql_query, fetch_through_pandas=fetch_through_pandas, fail_silently=fail_silently, params=(schema, table)
        )

    def get_all_db_info(
        self, get_json_info: bool = True, fetch_through_pandas: bool = True, fail_silently: bool = False
    ) -> pd.DataFrame | list[tuple[Any, ...]] | None:
        """All database columns info, from INFORMATION_SCHEMA.COLUMNS.

        Ignores the ``pg_stat_statements`` table and the ``pg_catalog`` and
        ``information_schema`` schemas.

        If ``get_json_info`` is True, adds the ``json_key`` and ``json_value_type``
        columns, with one extra row per key found in each json/jsonb column. In that
        case a DataFrame is always returned and errors are always raised; otherwise
        ``fetch_through_pandas`` and ``fail_silently`` are passed to :meth:`query`.
        """
        sql_query = (
            "SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE table_name != 'pg_stat_statements' "
            "AND table_schema NOT IN ('pg_catalog', 'information_schema')"
        )
        if not get_json_info:
            return self.query(sql_query, fetch_through_pandas=fetch_through_pandas, fail_silently=fail_silently)

        df = self._query_dataframe(sql_query)
        data_type_position = df.columns.get_loc("data_type")
        assert isinstance(data_type_position, int)
        df.insert(data_type_position + 1, "json_key", "")
        df.insert(data_type_position + 2, "json_value_type", "")

        # Only objects can be expanded by json(b)_each, so other values are skipped.
        json_query = """
            SELECT json_data.key, {fn}_typeof(json_data.value) AS json_value_data_type, COUNT(*)
            FROM {schema}.{table} AS t, {fn}_each(t.{column}) AS json_data
            WHERE {fn}_typeof(t.{column}) = 'object'
            GROUP BY 1, 2
            ORDER BY 1, 2
        """

        json_rows = []
        for _, row in df[df["data_type"].isin(["json", "jsonb"])].iterrows():
            keys_df = self._query_dataframe(
                json_query.format(
                    fn=row["data_type"],
                    schema=quote_identifier(row["table_schema"]),
                    table=quote_identifier(row["table_name"]),
                    column=quote_identifier(row["column_name"]),
                )
            )
            for _, key_row in keys_df.iterrows():
                json_row = row.copy()
                json_row["json_key"] = key_row["key"]
                json_row["json_value_type"] = key_row["json_value_data_type"]
                json_rows.append(json_row)

        if json_rows:
            df = pd.concat([df, pd.DataFrame(json_rows, columns=df.columns)], ignore_index=True)
        sort_columns = ["table_catalog", "table_schema", "table_name", "column_name", "data_type"]
        return df.sort_values(by=[*sort_columns, "json_key", "json_value_type"], ignore_index=True)

    def _query_dataframe(self, sql_query: str) -> pd.DataFrame:
        result = self.query(sql_query, fetch_through_pandas=True, fail_silently=False)
        assert isinstance(result, pd.DataFrame)
        return result


# -- Helpers -----------------------------------------------------------------


def quote_identifier(name: str, quote: str = '"') -> str:
    """Quote a SQL identifier (table, column...), escaping embedded quote characters."""
    return quote + str(name).replace(quote, quote * 2) + quote


@functools.cache
def _import_driver(module: str, extra: str) -> ModuleType:
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise ImportError(missing_extra_message(extra)) from exc


def _database_errors() -> tuple[type[Exception], ...]:
    """Base exception classes of the database drivers that are installed."""
    errors: list[type[Exception]] = [sqlite3.Error]
    for module, attribute in (("psycopg2", "Error"), ("mysql.connector", "Error")):
        try:
            errors.append(getattr(importlib.import_module(module), attribute))
        except ImportError:
            continue
    return tuple(errors)


def _clean(settings: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in settings.items() if value is not None}


def _connect_postgresql(settings: Mapping[str, Any]) -> Any:
    """Open a psycopg2 connection from settings with libpq keywords and/or a ``url``/``dsn``."""
    psycopg2 = _import_driver("psycopg2", "postgresql")
    kwargs = _clean(settings)
    dsn = kwargs.pop("url", None) or kwargs.pop("dsn", None)
    return psycopg2.connect(dsn, **kwargs)


def _mysql_connection_kwargs(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Translate instackup's MySQL settings into ``mysql.connector.connect`` keyword arguments."""
    kwargs = _clean(settings)
    if url := kwargs.pop("url", None):
        kwargs = {**parse_database_url(url), **kwargs}
    if "dbname" in kwargs:  # Name used by the credential templates; the driver expects "database".
        kwargs.setdefault("database", kwargs.pop("dbname"))
    if kwargs.get("port") not in (None, ""):
        kwargs["port"] = int(kwargs["port"])
    return kwargs


def parse_database_url(url: str) -> dict[str, Any]:
    """Split ``scheme://user:password@host:port/database`` into connection keyword arguments."""
    parts = urlsplit(url)
    settings = {
        "host": parts.hostname,
        "port": parts.port,
        "user": unquote(parts.username) if parts.username else None,
        "password": unquote(parts.password) if parts.password else None,
        "database": unquote(parts.path.lstrip("/")) or None,
    }
    return _clean(settings)
