from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call, sentinel

import pandas as pd
import pytest
from google.cloud import bigquery
from google.cloud.bigquery import AccessEntry, SchemaField
from google.cloud.exceptions import NotFound

from instackup import bigquery_tools
from instackup._google import GoogleAuth
from instackup.bigquery_tools import TABLE_LIST_ATTRIBUTES, BigQueryTool

PROJECT = "my-project"
TRANSFER_PATH = "projects/my-project/locations/us/transferConfigs/abc"


def table_ref(spec: str) -> bigquery.TableReference:
    return bigquery.TableReference.from_string(spec)


@pytest.fixture
def client() -> MagicMock:
    fake = MagicMock(name="bigquery.Client")
    fake.project = PROJECT
    fake._credentials = sentinel.credentials
    return fake


@pytest.fixture
def tool(client: MagicMock) -> BigQueryTool:
    return BigQueryTool(client=client)


@pytest.fixture
def missing_table(client: MagicMock) -> None:
    client.get_table.side_effect = NotFound("Table not found")


# -- Construction ---------------------------------------------------------------


def test_init_uses_the_injected_client(client: MagicMock) -> None:
    tool = BigQueryTool(client=client)

    assert tool.client is client
    assert tool.project is None


@pytest.mark.parametrize(
    ("args", "kwargs", "expected_call"),
    [
        ((), {}, call("default", None, use_config=True)),
        (
            ("analytics",),
            {"authenticate": False, "credentials": {"project_id": "proj-id"}},
            call("analytics", {"project_id": "proj-id"}, use_config=False),
        ),
    ],
)
def test_init_without_client_resolves_google_auth(
    monkeypatch: pytest.MonkeyPatch,
    to_gbq: MagicMock,
    args: tuple[str, ...],
    kwargs: dict[str, Any],
    expected_call: Any,
) -> None:
    project_info = {"id": "proj-id", "name": "Main", "number": 42}
    resolve = MagicMock(return_value=GoogleAuth(sentinel.resolved, "proj-id", project_info))
    client_cls = MagicMock(name="bigquery.Client")
    client_cls.return_value.project = "proj-id"
    monkeypatch.setattr(bigquery_tools, "resolve_google_auth", resolve)
    monkeypatch.setattr(bigquery_tools.bigquery, "Client", client_cls)

    tool = BigQueryTool(*args, **kwargs)

    assert resolve.call_args_list == [expected_call]
    client_cls.assert_called_once_with(project="proj-id", credentials=sentinel.resolved)
    assert tool.client is client_cls.return_value
    assert tool.project == project_info

    tool.upload(pd.DataFrame({"a": [1]}), "ds", "tbl")
    assert to_gbq.call_args.kwargs["credentials"] is sentinel.resolved


# -- Queries ----------------------------------------------------------------------


def test_query_returns_the_results_as_a_dataframe(tool: BigQueryTool, client: MagicMock) -> None:
    expected = pd.DataFrame({"x": [1]})
    client.query.return_value.to_dataframe.return_value = expected

    assert tool.query("SELECT 1 AS x") is expected
    client.query.assert_called_once_with("SELECT 1 AS x")


def test_query_propagates_errors(tool: BigQueryTool, client: MagicMock) -> None:
    client.query.side_effect = RuntimeError("bad query")

    with pytest.raises(RuntimeError, match="bad query"):
        tool.query("SELECT")


@pytest.mark.parametrize(
    ("kwargs", "disposition"),
    [
        ({}, "WRITE_TRUNCATE"),
        ({"writing_mode": "APPEND"}, "WRITE_APPEND"),
        ({"writing_mode": "empty"}, "WRITE_EMPTY"),
        ({"writing_mode": "Truncate"}, "WRITE_TRUNCATE"),
    ],
)
def test_query_and_save_results_into_existing_table(
    tool: BigQueryTool, client: MagicMock, kwargs: dict[str, str], disposition: str
) -> None:
    tool.query_and_save_results("SELECT 1", "ds", "tbl", **kwargs)

    client.get_table.assert_called_once_with(table_ref(f"{PROJECT}.ds.tbl"))
    (sql,), call_kwargs = client.query.call_args
    job_config = call_kwargs["job_config"]
    assert sql == "SELECT 1"
    assert job_config.destination == table_ref(f"{PROJECT}.ds.tbl")
    assert job_config.write_disposition == disposition
    client.query.return_value.result.assert_called_once_with()


def test_query_and_save_results_rejects_unknown_writing_mode(tool: BigQueryTool, client: MagicMock) -> None:
    with pytest.raises(ValueError, match="Unsupported writing_mode MERGE"):
        tool.query_and_save_results("SELECT 1", "ds", "tbl", writing_mode="MERGE")

    client.query.assert_not_called()


@pytest.mark.usefixtures("missing_table")
def test_unknown_writing_mode_is_rejected_even_for_new_tables(
    tool: BigQueryTool, client: MagicMock, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="Unsupported writing_mode"):
        tool.query_and_save_results("SELECT 1", "ds", "tbl", writing_mode="MERGE", create_table_if_needed=True)
    with pytest.raises(ValueError, match="Unsupported writing_mode"):
        tool.upload_from_gcs("ds", "tbl", "gs://b/f.csv", writing_mode="bogus", create_table_if_needed=True)
    client.query.assert_not_called()
    client.load_table_from_uri.assert_not_called()


@pytest.mark.usefixtures("missing_table")
def test_query_and_save_results_creates_missing_table_when_allowed(tool: BigQueryTool, client: MagicMock) -> None:
    tool.query_and_save_results("SELECT 1", "other-project.ds", "tbl", create_table_if_needed=True)

    job_config = client.query.call_args.kwargs["job_config"]
    assert job_config.destination == table_ref("other-project.ds.tbl")
    assert job_config.write_disposition is None
    client.query.return_value.result.assert_called_once_with()


@pytest.mark.usefixtures("missing_table")
def test_query_and_save_results_raises_not_found_for_missing_table(tool: BigQueryTool, client: MagicMock) -> None:
    with pytest.raises(NotFound, match="Table not found"):
        tool.query_and_save_results("SELECT 1", "ds", "tbl")

    client.query.assert_not_called()


# -- Datasets ---------------------------------------------------------------------


def test_list_datasets(tool: BigQueryTool, client: MagicMock) -> None:
    client.list_datasets.return_value = [SimpleNamespace(dataset_id="raw"), SimpleNamespace(dataset_id="mart")]

    assert tool.list_datasets() == ["raw", "mart"]


@pytest.mark.parametrize(
    ("dataset", "kwargs", "project", "location"),
    [
        ("new_ds", {}, PROJECT, "US"),
        ("other-project.new_ds", {"location": "EU"}, "other-project", "EU"),
    ],
)
def test_create_dataset(
    tool: BigQueryTool, client: MagicMock, dataset: str, kwargs: dict[str, str], project: str, location: str
) -> None:
    tool.create_dataset(dataset, **kwargs)

    (created,), _ = client.create_dataset.call_args
    assert (created.project, created.dataset_id, created.location) == (project, "new_ds", location)


def test_list_dataset_permissions(tool: BigQueryTool, client: MagicMock) -> None:
    entries = (AccessEntry("OWNER", "userByEmail", "owner@example.com"), AccessEntry("READER", "domain", "example.com"))
    client.get_dataset.return_value = SimpleNamespace(access_entries=entries)

    assert tool.list_dataset_permissions("ds") == list(entries)
    client.get_dataset.assert_called_once_with("ds")


@pytest.mark.parametrize(
    ("email_type", "entity_type"),
    [
        ("user", "userByEmail"),
        ("User", "userByEmail"),
        ("group", "groupByEmail"),
        ("GROUP", "groupByEmail"),
        ("userByEmail", "userByEmail"),
        ("groupByEmail", "groupByEmail"),
        ("domain", "domain"),
        ("iamMember", "iamMember"),
        ("specialGroup", "specialGroup"),
    ],
)
def test_add_dataset_permission(tool: BigQueryTool, client: MagicMock, email_type: str, entity_type: str) -> None:
    existing = AccessEntry("OWNER", "userByEmail", "owner@example.com")
    dataset = SimpleNamespace(access_entries=[existing])
    client.get_dataset.return_value = dataset

    tool.add_dataset_permission("ds", "READER", email_type, "someone@example.com")

    assert dataset.access_entries == [existing, AccessEntry("READER", entity_type, "someone@example.com")]
    client.update_dataset.assert_called_once_with(dataset, ["access_entries"])


@pytest.mark.parametrize(("email", "kept"), [("ALICE@example.COM", [1, 3]), ("nobody@example.com", [0, 1, 2, 3])])
def test_remove_dataset_permission(tool: BigQueryTool, client: MagicMock, email: str, kept: list[int]) -> None:
    entries = [
        AccessEntry("READER", "userByEmail", "Alice@Example.com"),
        AccessEntry("WRITER", "groupByEmail", "team@example.com"),
        AccessEntry("OWNER", "userByEmail", "alice@example.com"),
        AccessEntry(None, "view", {"projectId": "p", "datasetId": "d", "tableId": "v"}),
    ]
    dataset = SimpleNamespace(access_entries=list(entries))
    client.get_dataset.return_value = dataset

    tool.remove_dataset_permission("ds", email)

    assert dataset.access_entries == [entries[index] for index in kept]
    client.update_dataset.assert_called_once_with(dataset, ["access_entries"])


# -- Tables -----------------------------------------------------------------------


def _table(table_id: str, **attributes: Any) -> SimpleNamespace:
    values: dict[str, Any] = dict.fromkeys(TABLE_LIST_ATTRIBUTES)
    values.update({"table_id": table_id, "dataset_id": "ds", "table_type": "TABLE", **attributes})
    return SimpleNamespace(**values)


@pytest.fixture
def tables(client: MagicMock) -> None:
    client.list_tables.return_value = [_table("orders"), _table("users", table_type="VIEW")]


@pytest.mark.usefixtures("tables")
def test_list_tables_in_dataset_returns_every_attribute_by_default(tool: BigQueryTool, client: MagicMock) -> None:
    result = tool.list_tables_in_dataset("ds")

    client.list_tables.assert_called_once_with("ds")
    assert isinstance(result, dict)
    assert set(result) == set(TABLE_LIST_ATTRIBUTES)
    assert result["table_id"] == ["orders", "users"]
    assert result["table_type"] == ["TABLE", "VIEW"]


@pytest.mark.usefixtures("tables")
@pytest.mark.parametrize(
    ("return_type", "expected"),
    [
        ("dict", {"table_id": ["orders", "users"], "table_type": ["TABLE", "VIEW"]}),
        ("LIST", [{"table_id": "orders", "table_type": "TABLE"}, {"table_id": "users", "table_type": "VIEW"}]),
    ],
)
def test_list_tables_in_dataset_selected_attributes(tool: BigQueryTool, return_type: str, expected: Any) -> None:
    assert tool.list_tables_in_dataset("ds", get=["table_type", "table_id"], return_type=return_type) == expected


@pytest.mark.usefixtures("tables")
def test_list_tables_in_dataset_as_dataframe(tool: BigQueryTool) -> None:
    result = tool.list_tables_in_dataset("ds", get=("table_id", "table_type"), return_type="DataFrame")

    expected = pd.DataFrame({"table_id": ["orders", "users"], "table_type": ["TABLE", "VIEW"]})
    pd.testing.assert_frame_equal(result, expected, check_like=True)


@pytest.mark.usefixtures("tables")
@pytest.mark.parametrize("get", ["table_id", ["table_id"]])
@pytest.mark.parametrize("return_type", ["dict", "list", "dataframe"])
def test_list_tables_in_dataset_single_attribute_is_a_plain_list(
    tool: BigQueryTool, get: str | list[str], return_type: str
) -> None:
    assert tool.list_tables_in_dataset("ds", get=get, return_type=return_type) == ["orders", "users"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"get": ["table_id", "size"]}, "Item 'size' from get field is not a valid table parameter"),
        ({"return_type": "json"}, "Invalid return type"),
    ],
)
def test_list_tables_in_dataset_rejects_invalid_arguments(
    tool: BigQueryTool, client: MagicMock, kwargs: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        tool.list_tables_in_dataset("ds", **kwargs)

    client.list_tables.assert_not_called()


def test_list_tables_in_dataset_fails_for_missing_dataset(tool: BigQueryTool, client: MagicMock) -> None:
    client.list_tables.side_effect = NotFound("Dataset not found")

    with pytest.raises(NotFound, match="Dataset not found"):
        tool.list_tables_in_dataset("missing")


def test_get_table_schema_converts_nested_fields(tool: BigQueryTool, client: MagicMock) -> None:
    schema = [
        SchemaField("id", "INTEGER", mode="REQUIRED", description="Primary key"),
        SchemaField(
            "address",
            "RECORD",
            mode="REPEATED",
            fields=[
                SchemaField("city", "STRING"),
                SchemaField("geo", "RECORD", fields=[SchemaField("lat", "FLOAT")]),
            ],
        ),
    ]
    client.get_table.return_value = SimpleNamespace(schema=schema)

    result = tool.get_table_schema("other-project.ds", "tbl")

    client.get_table.assert_called_once_with(table_ref("other-project.ds.tbl"))
    assert result == {
        "fields": [
            {"name": "id", "type": "INTEGER", "mode": "REQUIRED", "description": "Primary key"},
            {
                "name": "address",
                "type": "RECORD",
                "mode": "REPEATED",
                "fields": [
                    {"name": "city", "type": "STRING", "mode": "NULLABLE"},
                    {
                        "name": "geo",
                        "type": "RECORD",
                        "mode": "NULLABLE",
                        "fields": [{"name": "lat", "type": "FLOAT", "mode": "NULLABLE"}],
                    },
                ],
            },
        ]
    }
    assert BigQueryTool._parse_schema(result) == schema


def test_create_empty_table(tool: BigQueryTool, client: MagicMock) -> None:
    tool.create_empty_table("ds", "tbl", {"fields": [{"name": "id", "type": "INTEGER", "mode": "REQUIRED"}]})

    (table,), _ = client.create_table.call_args
    assert table.reference == table_ref(f"{PROJECT}.ds.tbl")
    assert table.schema == [SchemaField("id", "INTEGER", mode="REQUIRED")]


# -- Schema parsing ----------------------------------------------------------------

SCHEMA_FIELDS = [
    {"name": "id", "type": "INTEGER", "mode": "REQUIRED", "description": "Primary key"},
    {"name": "name", "type": "STRING"},
    {"name": "nickname", "type": "STRING", "mode": None},
    {"name": "address", "type": "RECORD", "mode": "REPEATED", "fields": [{"name": "city", "type": "STRING"}]},
    {"name": "meta", "type": "struct", "fields": [{"name": "source", "type": "STRING"}]},
]
PARSED_SCHEMA = [
    SchemaField("id", "INTEGER", mode="REQUIRED", description="Primary key"),
    SchemaField("name", "STRING", mode="NULLABLE"),
    SchemaField("nickname", "STRING", mode="NULLABLE"),
    SchemaField("address", "RECORD", mode="REPEATED", fields=[SchemaField("city", "STRING")]),
    SchemaField("meta", "STRUCT", fields=[SchemaField("source", "STRING")]),
]


@pytest.mark.parametrize("schema", [SCHEMA_FIELDS, {"fields": SCHEMA_FIELDS}], ids=["list", "dict"])
def test_parse_schema(schema: Any) -> None:
    original = copy.deepcopy(schema)

    assert BigQueryTool._parse_schema(schema) == PARSED_SCHEMA
    assert schema == original


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ([{"type": "STRING"}], "Field incomplete"),
        ([{"name": "a"}], "Field incomplete"),
        ([{"name": "", "type": "STRING"}], "Field incomplete"),
        ([{"name": "rec", "type": "RECORD", "fields": [{"type": "STRING"}]}], "Field incomplete"),
        ([{"name": "rec", "type": "RECORD"}], "Field rec has RECORD type, but no associated nested fields"),
        ([{"name": "rec", "type": "STRUCT", "fields": []}], "Field rec has RECORD type"),
    ],
)
def test_parse_schema_rejects_invalid_fields(fields: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        BigQueryTool._parse_schema(fields)


# -- PostgreSQL schema conversion ------------------------------------------------------


def information_schema(rows: list[tuple[Any, ...]], *, table_name: str = "orders") -> pd.DataFrame:
    """INFORMATION_SCHEMA.COLUMNS-like rows, with ``json_key``/``json_value_type`` when rows have 5 items."""
    columns = ["column_name", "data_type", "is_nullable", "json_key", "json_value_type"][: len(rows[0])]
    return pd.DataFrame(rows, columns=columns).assign(table_catalog="db", table_schema="public", table_name=table_name)


JSON_COLUMNS = [
    ("id", "integer", "NO", None, None),
    ("payload", "jsonb", "YES", "", ""),
    ("payload", "jsonb", "YES", "count", "number"),
    ("payload", "jsonb", "YES", "items", "array"),
    ("payload", "jsonb", "YES", "name", "string"),
    ("payload", "jsonb", "YES", "other", "unknown"),
    ("settings", "json", "NO", "", ""),
]


def test_convert_postgresql_table_schema_maps_types_and_modes() -> None:
    df = information_schema(
        [
            ("name", "character varying", "YES"),
            ("id", "integer", "NO"),
            ("tags", "ARRAY", "NO"),
            ("location", "point", "YES"),
            ("created_at", "timestamp with time zone", "YES"),
            ("amount", "numeric", "NO"),
            ("is_active", "boolean", None),
        ]
    )

    assert BigQueryTool.convert_postgresql_table_schema(df) == {
        "fields": [
            {"type": "NUMERIC", "name": "amount", "mode": "REQUIRED"},
            {"type": "TIMESTAMP", "name": "created_at", "mode": "NULLABLE"},
            {"type": "INTEGER", "name": "id", "mode": "REQUIRED"},
            {"type": "BOOLEAN", "name": "is_active", "mode": "NULLABLE"},
            {"type": "STRING", "name": "location", "mode": "NULLABLE"},
            {"type": "STRING", "name": "name", "mode": "NULLABLE"},
            {"type": "STRING", "name": "tags", "mode": "REPEATED"},
        ]
    }


def test_convert_postgresql_table_schema_parses_json_columns_into_records() -> None:
    fields = BigQueryTool.convert_postgresql_table_schema(information_schema(JSON_COLUMNS))["fields"]

    assert [field["name"] for field in fields] == ["id", "payload", "settings"]
    id_field, payload, settings = fields
    assert id_field == {"type": "INTEGER", "name": "id", "mode": "REQUIRED"}
    assert (payload["type"], payload["mode"]) == ("RECORD", "NULLABLE")  # One JSON object per row
    assert payload["fields"] == [
        {"type": "NUMERIC", "name": "count", "mode": "NULLABLE"},
        {"type": "STRING", "name": "items", "mode": "REPEATED"},
        {"type": "STRING", "name": "name", "mode": "NULLABLE"},
        {"type": "STRING", "name": "other", "mode": "NULLABLE"},
    ]
    assert settings == {"type": "STRING", "name": "settings", "mode": "REQUIRED"}


def test_convert_postgresql_table_schema_json_key_with_mixed_types_becomes_string() -> None:
    rows = [
        ("payload", "jsonb", "YES", "", ""),
        ("payload", "jsonb", "YES", "v", "number"),
        ("payload", "jsonb", "YES", "v", "string"),
    ]
    (payload,) = BigQueryTool.convert_postgresql_table_schema(information_schema(rows))["fields"]
    assert payload["fields"] == [{"type": "STRING", "name": "v", "mode": "NULLABLE"}]


@pytest.mark.parametrize("rows", [JSON_COLUMNS, [row[:3] for row in JSON_COLUMNS]], ids=["json-info", "no-json-info"])
def test_convert_postgresql_table_schema_without_json_parsing(rows: list[tuple[Any, ...]]) -> None:
    assert BigQueryTool.convert_postgresql_table_schema(information_schema(rows), parse_json_columns=False) == {
        "fields": [
            {"type": "INTEGER", "name": "id", "mode": "REQUIRED"},
            {"type": "STRING", "name": "payload", "mode": "NULLABLE"},
            {"type": "STRING", "name": "settings", "mode": "REQUIRED"},
        ]
    }


def test_convert_postgresql_table_schema_needs_json_info_to_parse_json() -> None:
    df = information_schema([("id", "integer", "NO"), ("payload", "JSONB", "YES")])

    with pytest.raises(ValueError, match="'json_key' and 'json_value_type' are not part of given DataFrame"):
        BigQueryTool.convert_postgresql_table_schema(df)


@pytest.mark.parametrize("parse_json_columns", [True, False])
def test_convert_postgresql_table_schema_does_not_mutate_input(parse_json_columns: bool) -> None:
    df = information_schema(JSON_COLUMNS)
    original = df.copy()

    BigQueryTool.convert_postgresql_table_schema(df, parse_json_columns=parse_json_columns)

    pd.testing.assert_frame_equal(df, original)


@pytest.mark.parametrize(("parse_json_columns", "payload_type"), [(True, "RECORD"), (False, "STRING")])
def test_convert_multiple_postgresql_tables_schema(parse_json_columns: bool, payload_type: str) -> None:
    df = pd.concat(
        [
            information_schema([("email", "text", "YES", None, None)], table_name="users"),
            information_schema(JSON_COLUMNS, table_name="orders"),
        ],
        ignore_index=True,
    )
    original = df.copy()

    result = BigQueryTool.convert_multiple_postgresql_tables_schema(df, parse_json_columns=parse_json_columns)

    assert list(result) == ["db-public-orders", "db-public-users"]
    assert result["db-public-users"] == {"fields": [{"type": "STRING", "name": "email", "mode": "NULLABLE"}]}
    assert [field["type"] for field in result["db-public-orders"]["fields"]] == ["INTEGER", payload_type, "STRING"]
    pd.testing.assert_frame_equal(df, original)


def test_convert_multiple_postgresql_tables_schema_without_tables() -> None:
    df = information_schema([("id", "integer", "NO")]).iloc[0:0]

    assert BigQueryTool.convert_multiple_postgresql_tables_schema(df) == {}


# -- DataFrame helpers ---------------------------------------------------------------


@pytest.mark.parametrize("dtype", [None, object], ids=["default-str", "object"])
def test_convert_dataframe_to_numeric(dtype: type | None) -> None:
    df = pd.DataFrame({"qty": ["1", "2"], "price": ["1.5", "2.25"], "code": ["007", "008"]}, dtype=dtype)
    df["ratio"] = [0.5, 1.0]

    result = BigQueryTool.convert_dataframe_to_numeric(df, exclude_columns=["code"])

    assert result is df
    expected = pd.DataFrame(
        {
            "qty": [1, 2],
            "price": [1.5, 2.25],
            "code": pd.Series(["007", "008"], dtype=dtype),
            "ratio": [0.5, 1.0],
        }
    )
    pd.testing.assert_frame_equal(df, expected)


def test_convert_dataframe_to_numeric_excludes_a_single_column_name() -> None:
    df = BigQueryTool.convert_dataframe_to_numeric(
        pd.DataFrame({"code": ["007"], "qty": ["1"]}), exclude_columns="code"
    )
    assert df["code"].tolist() == ["007"]
    assert df["qty"].tolist() == [1]


def test_convert_dataframe_to_numeric_passes_kwargs_to_to_numeric() -> None:
    df = pd.DataFrame({"value": ["1", "n/a"]})

    BigQueryTool.convert_dataframe_to_numeric(df, errors="coerce")

    pd.testing.assert_series_equal(df["value"], pd.Series([1.0, float("nan")], name="value"))


def test_convert_dataframe_to_numeric_without_columns_to_convert() -> None:
    df = pd.DataFrame({"code": ["007"], "ratio": [0.5]})
    original = df.copy()

    assert BigQueryTool.convert_dataframe_to_numeric(df, exclude_columns={"code"}) is df
    pd.testing.assert_frame_equal(df, original)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Nome Completo", "nome_completo"),
        ("Ação", "acao"),
        ("Preço (R$)", "preco__r__"),
        ("2024 revenue", "_2024_revenue"),
        ("", "_"),
        (0, "_0"),
    ],
)
def test_clean_dataframe_column_names(name: Any, expected: str) -> None:
    df = pd.DataFrame({name: [1]})

    assert BigQueryTool.clean_dataframe_column_names(df).columns.tolist() == [expected]


def test_clean_dataframe_column_names_special_treatment() -> None:
    df = pd.DataFrame(columns=["Revenue %", "R&D"])

    result = BigQueryTool.clean_dataframe_column_names(df, special_treatment={"%": "pct", "&": "_and_"})

    assert result.columns.tolist() == ["revenue_pct", "r_and_d"]


def test_clean_dataframe_column_names_special_treatment_of_accented_chars() -> None:
    df = BigQueryTool.clean_dataframe_column_names(
        pd.DataFrame(columns=["Preço", "ação"]), special_treatment={"ç": "ss"}
    )
    assert df.columns.tolist() == ["presso", "assao"]


def test_clean_dataframe_column_names_returns_a_copy() -> None:
    df = pd.DataFrame({"Name": ["Ann"]})

    result = BigQueryTool.clean_dataframe_column_names(df)

    assert result is not df
    assert df.columns.tolist() == ["Name"]
    assert result["name"].tolist() == ["Ann"]


# -- Uploads --------------------------------------------------------------------------


@pytest.fixture
def to_gbq(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock(name="pandas_gbq.to_gbq")
    monkeypatch.setattr(bigquery_tools.pandas_gbq, "to_gbq", fake)
    return fake


def test_upload_cleans_columns_and_uses_tool_defaults(tool: BigQueryTool, to_gbq: MagicMock) -> None:
    df = pd.DataFrame({"Nome Completo": ["Ann"]})

    tool.upload(df, "ds", "people", if_exists="append")

    (uploaded, destination), kwargs = to_gbq.call_args
    assert uploaded.columns.tolist() == ["nome_completo"]
    assert destination == "ds.people"
    assert kwargs == {"if_exists": "append", "project_id": PROJECT, "credentials": sentinel.credentials}
    assert df.columns.tolist() == ["Nome Completo"]


def test_upload_caller_kwargs_win(tool: BigQueryTool, to_gbq: MagicMock) -> None:
    tool.upload(pd.DataFrame({"a": [1]}), "ds", "tbl", project_id="other", credentials=sentinel.other)

    assert to_gbq.call_args.kwargs == {"project_id": "other", "credentials": sentinel.other}


def test_upload_without_client_credentials(client: MagicMock, to_gbq: MagicMock) -> None:
    del client._credentials

    BigQueryTool(client=client).upload(pd.DataFrame({"a": [1]}), "ds", "tbl")

    assert to_gbq.call_args.kwargs == {"project_id": PROJECT}


def load_job_config(client: MagicMock) -> bigquery.LoadJobConfig:
    job_config: bigquery.LoadJobConfig = client.load_table_from_uri.call_args.kwargs["job_config"]
    return job_config


def test_upload_from_gcs_into_existing_table_with_csv_options(tool: BigQueryTool, client: MagicMock) -> None:
    tool.upload_from_gcs(
        "ds",
        "tbl",
        "gs://bucket/data/*.csv",
        header_rows=2,
        delimiter=";",
        encoding="ISO-8859-1",
        ignore_unknown_values=True,
        max_bad_records=5,
        writing_mode="truncate",
        schema=[{"name": "ignored", "type": "STRING"}],
    )

    (uri, destination), _ = client.load_table_from_uri.call_args
    job_config = load_job_config(client)
    assert uri == "gs://bucket/data/*.csv"
    assert destination == table_ref(f"{PROJECT}.ds.tbl")
    assert job_config.source_format == "CSV"
    assert (job_config.skip_leading_rows, job_config.field_delimiter, job_config.encoding) == (2, ";", "ISO-8859-1")
    assert (job_config.ignore_unknown_values, job_config.max_bad_records) == (True, 5)
    assert job_config.write_disposition == "WRITE_TRUNCATE"
    assert job_config.autodetect is None
    assert job_config.schema is None
    client.load_table_from_uri.return_value.result.assert_called_once_with()


@pytest.mark.parametrize(
    ("file_format", "source_format"),
    [
        ("avro", "AVRO"),
        ("csv", "CSV"),
        ("json", "NEWLINE_DELIMITED_JSON"),
        ("ORC", "ORC"),
        ("Parquet", "PARQUET"),
    ],
)
def test_upload_from_gcs_formats_append_by_default(
    tool: BigQueryTool, client: MagicMock, file_format: str, source_format: str
) -> None:
    tool.upload_from_gcs("ds", "tbl", "gs://bucket/file", file_format=file_format)

    job_config = load_job_config(client)
    assert job_config.source_format == source_format
    assert job_config.write_disposition == "WRITE_APPEND"


def test_upload_from_gcs_csv_options_apply_to_csv_only(tool: BigQueryTool, client: MagicMock) -> None:
    tool.upload_from_gcs("ds", "tbl", "gs://bucket/file.json", file_format="JSON", header_rows=3, delimiter="|")

    job_config = load_job_config(client)
    assert (job_config.skip_leading_rows, job_config.field_delimiter, job_config.encoding) == (None, None, None)


@pytest.mark.usefixtures("missing_table")
@pytest.mark.parametrize("file_format", ["CSV", "JSON"])
def test_upload_from_gcs_autodetects_schema_of_new_table(
    tool: BigQueryTool, client: MagicMock, file_format: str
) -> None:
    tool.upload_from_gcs(
        "ds", "tbl", "gs://bucket/file", file_format=file_format, writing_mode="TRUNCATE", create_table_if_needed=True
    )

    job_config = load_job_config(client)
    assert job_config.autodetect is True
    assert job_config.schema is None
    assert job_config.write_disposition is None


@pytest.mark.usefixtures("missing_table")
@pytest.mark.parametrize("file_format", ["CSV", "PARQUET"])
def test_upload_from_gcs_uses_given_schema_for_new_table(
    tool: BigQueryTool, client: MagicMock, file_format: str
) -> None:
    schema = {"fields": [{"name": "id", "type": "INTEGER", "mode": "REQUIRED"}]}

    tool.upload_from_gcs(
        "ds", "tbl", "gs://bucket/file", file_format=file_format, create_table_if_needed=True, schema=schema
    )

    job_config = load_job_config(client)
    assert job_config.schema == [SchemaField("id", "INTEGER", mode="REQUIRED")]
    assert job_config.autodetect is None


@pytest.mark.usefixtures("missing_table")
@pytest.mark.parametrize("file_format", ["AVRO", "ORC", "PARQUET"])
def test_upload_from_gcs_needs_schema_for_new_table_without_autodetection(
    tool: BigQueryTool, client: MagicMock, file_format: str
) -> None:
    with pytest.raises(ValueError, match="No schema given"):
        tool.upload_from_gcs("ds", "tbl", "gs://bucket/file", file_format=file_format, create_table_if_needed=True)

    client.load_table_from_uri.assert_not_called()


@pytest.mark.usefixtures("missing_table")
def test_upload_from_gcs_raises_not_found_for_missing_table(tool: BigQueryTool, client: MagicMock) -> None:
    with pytest.raises(NotFound, match="Table not found"):
        tool.upload_from_gcs("ds", "tbl", "gs://bucket/file")

    client.load_table_from_uri.assert_not_called()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"file_format": "xml"}, "Unsupported format XML"),
        ({"writing_mode": "MERGE"}, "Unsupported writing_mode MERGE"),
    ],
)
def test_upload_from_gcs_rejects_invalid_options(
    tool: BigQueryTool, client: MagicMock, kwargs: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        tool.upload_from_gcs("ds", "tbl", "gs://bucket/file", **kwargs)

    client.load_table_from_uri.assert_not_called()


def test_upload_from_file_sends_the_local_file(tool: BigQueryTool, client: MagicMock, tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    path.write_bytes(b'{"id": 1}\n')
    job = MagicMock(name="LoadJob")
    sent: dict[str, Any] = {}

    def load(source_file: Any, destination: bigquery.TableReference, *, job_config: Any) -> MagicMock:
        sent.update(file=source_file, content=source_file.read(), destination=destination, job_config=job_config)
        return job

    client.load_table_from_file.side_effect = load

    tool.upload_from_file("ds", "tbl", str(path), file_format="json", writing_mode="EMPTY")

    assert sent["content"] == b'{"id": 1}\n'
    assert sent["file"].name == str(path)
    assert sent["file"].closed
    assert sent["destination"] == table_ref(f"{PROJECT}.ds.tbl")
    assert sent["job_config"].source_format == "NEWLINE_DELIMITED_JSON"
    assert sent["job_config"].write_disposition == "WRITE_EMPTY"
    job.result.assert_called_once_with()


# -- Data Transfer Service --------------------------------------------------------------


@pytest.fixture
def transfer_service(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    service_cls = MagicMock(name="DataTransferServiceClient")
    service = service_cls.return_value
    service.common_project_path.side_effect = lambda project: f"projects/{project}"
    service.list_transfer_configs.return_value = [
        SimpleNamespace(name="projects/x/transferConfigs/daily", display_name="Daily load"),
        SimpleNamespace(name="projects/x/transferConfigs/hourly", display_name="Hourly load"),
    ]
    service.start_manual_transfer_runs.return_value = SimpleNamespace(
        runs=[SimpleNamespace(state=SimpleNamespace(name="PENDING"))]
    )
    monkeypatch.setattr(bigquery_tools.bigquery_datatransfer_v1, "DataTransferServiceClient", service_cls)
    return service_cls


def started_run_request(transfer_service: MagicMock) -> dict[str, Any]:
    request: dict[str, Any] = transfer_service.return_value.start_manual_transfer_runs.call_args.kwargs["request"]
    return request


def test_start_transfer_by_project_path(tool: BigQueryTool, transfer_service: MagicMock) -> None:
    assert tool.start_transfer(project_path=TRANSFER_PATH) == "PENDING"
    tool.start_transfer(project_path=TRANSFER_PATH)

    transfer_service.assert_called_once_with(credentials=sentinel.credentials)
    request = started_run_request(transfer_service)
    assert request["parent"] == TRANSFER_PATH
    assert isinstance(request["requested_run_time"], datetime)
    assert request["requested_run_time"].tzinfo is not None
    transfer_service.return_value.list_transfer_configs.assert_not_called()


@pytest.mark.parametrize("project_name", [None, "Main"])
def test_start_transfer_by_display_name_in_tool_project(
    tool: BigQueryTool, transfer_service: MagicMock, project_name: str | None
) -> None:
    tool.project = {"id": "main-id", "name": "Main", "number": 1}

    assert tool.start_transfer(project_name=project_name, transfer_name="Hourly load") == "PENDING"

    transfer_service.return_value.list_transfer_configs.assert_called_once_with(parent="projects/main-id")
    assert started_run_request(transfer_service)["parent"] == "projects/x/transferConfigs/hourly"


def test_start_transfer_looks_up_project_name_in_credential_store(
    tool: BigQueryTool, transfer_service: MagicMock, use_credentials: Any
) -> None:
    use_credentials(
        {
            "google": {
                "default": {"project_name": "Main", "project_id": "main-id"},
                "analytics": {"project_name": "Analytics", "project_id": "analytics-id"},
            }
        }
    )
    tool.project = {"id": "main-id", "name": "Main", "number": 1}

    tool.start_transfer(project_name="Analytics", transfer_name="Daily load")

    transfer_service.return_value.list_transfer_configs.assert_called_once_with(parent="projects/analytics-id")
    assert started_run_request(transfer_service)["parent"] == "projects/x/transferConfigs/daily"


@pytest.mark.usefixtures("transfer_service")
def test_start_transfer_unknown_project_name(tool: BigQueryTool, use_credentials: Any) -> None:
    use_credentials({"google": {"default": {"project_name": "Main", "project_id": "main-id"}}})

    with pytest.raises(KeyError, match="Project name not found in the credential store"):
        tool.start_transfer(project_name="Unknown", transfer_name="Daily load")


def test_start_transfer_unknown_display_name(tool: BigQueryTool, transfer_service: MagicMock) -> None:
    tool.project = {"id": "main-id", "name": "Main", "number": 1}

    with pytest.raises(NameError, match="No transfer with display name 'Weekly load' was found"):
        tool.start_transfer(transfer_name="Weekly load")

    transfer_service.return_value.start_manual_transfer_runs.assert_not_called()


@pytest.mark.usefixtures("transfer_service")
def test_start_transfer_defaults_to_the_client_project(tool: BigQueryTool, transfer_service: MagicMock) -> None:
    assert tool.project is None  # E.g. an injected client or Application Default Credentials

    assert tool.start_transfer(transfer_name="Hourly load") == "PENDING"

    transfer_service.return_value.list_transfer_configs.assert_called_once_with(parent=f"projects/{PROJECT}")


@pytest.mark.usefixtures("transfer_service")
@pytest.mark.parametrize("kwargs", [{}, {"project_name": "Main"}])
def test_start_transfer_needs_path_or_names(tool: BigQueryTool, kwargs: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="Specify either project and transfer names or transferConfig project path"):
        tool.start_transfer(**kwargs)
