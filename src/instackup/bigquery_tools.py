"""Google BigQuery tool."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ._google import resolve_google_auth
from ._utils import missing_extra_message
from .credentials import get_default_store
from .general_tools import unicode_to_ascii

try:
    import pandas_gbq
    from google.cloud import bigquery, bigquery_datatransfer_v1
    from google.cloud.exceptions import NotFound
except ImportError as exc:  # pragma: no cover - depends on installed extras
    raise ImportError(missing_extra_message("gcp")) from exc

logger = logging.getLogger(__name__)

SchemaFields = list[dict[str, Any]]
Schema = Mapping[str, Any] | Sequence[Mapping[str, Any]]

# PostgreSQL reference: https://www.postgresql.org/docs/current/datatype.html
# BigQuery reference: https://cloud.google.com/bigquery/docs/reference/standard-sql/data-types
POSTGRES_TO_BIGQUERY_TYPE_CONVERTER = {
    # Boolean
    "boolean": "BOOLEAN",
    # Bytes
    "bigserial": "BYTES",
    "bit": "BYTES",
    "bit varying": "BYTES",
    "bytea": "BYTES",
    # Date
    "date": "DATE",
    # Float
    "double precision": "FLOAT",
    "real": "FLOAT",
    # Integer
    "bigint": "INTEGER",
    "integer": "INTEGER",
    # Numeric
    "decimal": "NUMERIC",
    "money": "NUMERIC",
    "numeric": "NUMERIC",
    # String
    "array": "STRING",
    "character": "STRING",
    "character varying": "STRING",
    "json": "STRING",
    "jsonb": "STRING",
    "oid": "STRING",
    "text": "STRING",
    "user-defined": "STRING",
    "uuid": "STRING",
    # Time
    "time": "TIME",
    "time with time zone": "TIME",
    "time without time zone": "TIME",
    # Timestamp
    "timestamp": "TIMESTAMP",
    "timestamp with time zone": "TIMESTAMP",
    "timestamp without time zone": "TIMESTAMP",
}

# Based on this conversion table: https://miro.medium.com/max/1052/1*3lUW3r6VLR-woQv2t-sT-g.png
JSON_TO_BIGQUERY_TYPE_CONVERTER = {
    "string": "STRING",
    "number": "NUMERIC",
    "integer": "INTEGER",
    "real": "FLOAT",
    "boolean": "BOOLEAN",
    "array": "STRING",
    "object": "STRING",
    "null": "STRING",
}

TABLE_LIST_ATTRIBUTES = (
    "clustering_fields",
    "created",
    "dataset_id",
    "expires",
    "friendly_name",
    "full_table_id",
    "labels",
    "partition_expiration",
    "partitioning_type",
    "project",
    "reference",
    "table_id",
    "table_type",
    "time_partitioning",
    "view_use_legacy_sql",
)

WRITE_DISPOSITIONS = {
    "APPEND": bigquery.WriteDisposition.WRITE_APPEND,
    "EMPTY": bigquery.WriteDisposition.WRITE_EMPTY,
    "TRUNCATE": bigquery.WriteDisposition.WRITE_TRUNCATE,
}

SOURCE_FORMATS = {
    "AVRO": bigquery.SourceFormat.AVRO,
    "CSV": bigquery.SourceFormat.CSV,
    "JSON": bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    "ORC": bigquery.SourceFormat.ORC,
    "PARQUET": bigquery.SourceFormat.PARQUET,
}


class BigQueryTool:
    """Handles most of the interaction needed with BigQuery.

    Authenticates with the ``google.<connection>`` settings in the credential store
    (or ``credentials``), falling back to Application Default Credentials. With
    ``authenticate=False`` the store is skipped (explicit ``credentials`` still apply). A ready
    ``google.cloud.bigquery.Client`` can be passed as ``client`` instead.
    """

    def __init__(
        self,
        connection: str = "default",
        authenticate: bool = True,
        *,
        credentials: Mapping[str, Any] | None = None,
        client: bigquery.Client | None = None,
    ) -> None:
        # Following the official docs: https://cloud.google.com/bigquery/docs/reference/libraries
        project = None
        google_credentials = getattr(client, "_credentials", None)
        if client is None:
            logger.debug("Initiating BigQuery Client")
            auth = resolve_google_auth(connection, credentials, use_config=authenticate)
            client = bigquery.Client(project=auth.project_id, credentials=auth.credentials)
            project = auth.project_info
            google_credentials = auth.credentials

        self.client = client
        self.transfer_client: Any = None
        self.project = project
        self._google_credentials = google_credentials

    # -- Helpers -------------------------------------------------------------

    def _table_ref(self, dataset: str, table: str) -> bigquery.TableReference:
        """Reference to ``dataset.table`` (``dataset`` may be ``project.dataset``)."""
        return bigquery.TableReference.from_string(f"{dataset}.{table}", default_project=self.client.project)

    def _check_destination(
        self, dataset: str, table_ref: bigquery.TableReference, create_table_if_needed: bool
    ) -> bool:
        """Whether the table exists; raises ``NotFound`` if it doesn't and can't be created."""
        try:
            self.client.get_table(table_ref)
        except NotFound:
            if create_table_if_needed:
                return False
            logger.error("Dataset doesn't exist." if dataset not in self.list_datasets() else "Table doesn't exist.")
            raise
        return True

    @staticmethod
    def _write_disposition(writing_mode: str) -> str:
        try:
            return WRITE_DISPOSITIONS[writing_mode.upper()]
        except KeyError:
            raise ValueError(
                f"Unsupported writing_mode {writing_mode}. Modes available: {list(WRITE_DISPOSITIONS)}"
            ) from None

    @staticmethod
    def _wait_for(job: Any) -> None:
        logger.info("Starting job %s", job.job_id)
        start_time = time.monotonic()
        job.result()  # Waits for the job to complete.
        logger.info("Job finished in %.2f seconds.", time.monotonic() - start_time)

    # -- Queries -------------------------------------------------------------

    def query(self, sql_query: str) -> pd.DataFrame:
        """Run a query and return the results as a DataFrame."""
        logger.debug("Initiating query: %s", sql_query)
        try:
            result = self.client.query(sql_query).to_dataframe()
        except Exception:
            logger.exception("Query failed")
            raise
        logger.debug("Query returned successfully.")
        return result

    def query_and_save_results(
        self,
        sql_query: str,
        dest_dataset: str,
        dest_table: str,
        writing_mode: str = "TRUNCATE",
        create_table_if_needed: bool = False,
    ) -> None:
        """Run a query and save its results in a table.

        ``writing_mode`` applies when the table already exists:

        - APPEND: appends the data to the table;
        - EMPTY: fails with a 'duplicate' error if the table contains data;
        - TRUNCATE (default): overwrites the table data.

        If the table doesn't exist, it's created when ``create_table_if_needed`` is
        True; otherwise ``NotFound`` is raised.
        """
        write_disposition = self._write_disposition(writing_mode)
        table_ref = self._table_ref(dest_dataset, dest_table)
        job_config = bigquery.QueryJobConfig(destination=table_ref)
        if self._check_destination(dest_dataset, table_ref, create_table_if_needed):
            job_config.write_disposition = write_disposition

        self._wait_for(self.client.query(sql_query, job_config=job_config))

    # -- Datasets ------------------------------------------------------------

    def list_datasets(self) -> list[str]:
        """Names of all datasets in the project."""
        return [ds.dataset_id for ds in self.client.list_datasets()]

    def create_dataset(self, dataset: str, location: str = "US") -> None:
        """Create a new dataset."""
        new_dataset = bigquery.Dataset(f"{self.client.project}.{dataset}" if "." not in dataset else dataset)
        new_dataset.location = location
        created = self.client.create_dataset(new_dataset)
        logger.info("Created dataset %s", created.full_dataset_id)

    def list_dataset_permissions(self, dataset: str) -> list[bigquery.AccessEntry]:
        """All access entries of a dataset."""
        return list(self.client.get_dataset(dataset).access_entries)

    def add_dataset_permission(self, dataset: str, role: str, email_type: str, email: str) -> None:
        """Grant ``role`` on a dataset.

        ``email_type`` is one of 'domain', 'groupByEmail' (or 'group'), 'iamMember',
        'specialGroup', 'userByEmail' (or 'user') or 'view'.
        """
        dataset_ref = self.client.get_dataset(dataset)
        aliases = {"user": "userByEmail", "group": "groupByEmail"}
        entity_type = aliases.get(email_type.lower(), email_type)

        entries = list(dataset_ref.access_entries)
        entries.append(bigquery.AccessEntry(role=role, entity_type=entity_type, entity_id=email))
        dataset_ref.access_entries = entries
        self.client.update_dataset(dataset_ref, ["access_entries"])

    def remove_dataset_permission(self, dataset: str, email: str) -> None:
        """Remove every access entry of ``email`` from a dataset. Nothing changes if there's no match."""
        dataset_ref = self.client.get_dataset(dataset)
        dataset_ref.access_entries = [
            entry
            for entry in dataset_ref.access_entries
            if not (isinstance(entry.entity_id, str) and entry.entity_id.lower() == email.lower())
        ]
        self.client.update_dataset(dataset_ref, ["access_entries"])

    # -- Tables --------------------------------------------------------------

    def list_tables_in_dataset(
        self, dataset: str, get: str | Iterable[str] | None = None, return_type: str = "dict"
    ) -> dict[str, list[Any]] | list[dict[str, Any]] | list[Any] | pd.DataFrame:
        """List the tables in a dataset. Fails if the dataset doesn't exist.

        ``get`` selects which attributes to return (one name or a collection, see
        ``TABLE_LIST_ATTRIBUTES``); when it's a single attribute, a plain list of its
        values is returned regardless of ``return_type``. Otherwise ``return_type`` is:

        - dict: one list of values per attribute, in the same table order;
        - list: one dictionary per table;
        - dataframe: a DataFrame with one row per table.
        """
        if get is None:
            attributes = list(TABLE_LIST_ATTRIBUTES)
        else:
            attributes = [get] if isinstance(get, str) else list(get)
            for item in attributes:
                if item not in TABLE_LIST_ATTRIBUTES:
                    raise ValueError(f"Item '{item}' from get field is not a valid table parameter.")
            attributes = [name for name in TABLE_LIST_ATTRIBUTES if name in attributes]

        return_type = return_type.lower()
        if return_type not in ("dict", "list", "dataframe"):
            raise ValueError("Invalid return type. Valid options are 'dict', 'list' or 'dataframe'.")

        rows = [{name: getattr(table, name) for name in attributes} for table in self.client.list_tables(dataset)]

        if len(attributes) == 1:
            logger.debug("Only one column, returning a single list value.")
            return [row[attributes[0]] for row in rows]
        if return_type == "list":
            return rows
        columns = {name: [row[name] for row in rows] for name in attributes}
        return pd.DataFrame(columns) if return_type == "dataframe" else columns

    def get_table_schema(self, dataset: str, table: str) -> dict[str, SchemaFields]:
        """Schema of a table as a ``{"fields": [...]}`` dictionary, the format used by the BigQuery API and CLI."""
        schema_fields = self.client.get_table(self._table_ref(dataset, table)).schema
        return {"fields": [_schema_field_to_dict(field) for field in schema_fields]}

    def create_empty_table(self, dataset: str, table: str, schema: Schema) -> None:
        """Create an empty table at ``dataset.table`` with the given schema (see :meth:`upload_from_gcs`)."""
        new_table = bigquery.Table(self._table_ref(dataset, table), schema=self._parse_schema(schema))
        created = self.client.create_table(new_table)
        logger.info("Created table %s", created.full_table_id)

    # -- Schema and DataFrame conversions ---------------------------------------

    @staticmethod
    def convert_postgresql_table_schema(
        dataframe: pd.DataFrame, parse_json_columns: bool = True
    ) -> dict[str, SchemaFields]:
        """Convert the INFORMATION_SCHEMA.COLUMNS rows of one PostgreSQL table into a BigQuery schema.

        The DataFrame is usually built with ``PostgreSQLTool.describe_table`` or
        ``PostgreSQLTool.get_all_db_info``. If ``parse_json_columns`` is True, json and
        jsonb columns become RECORD fields built from the ``json_key`` and
        ``json_value_type`` columns (which must exist if there are JSON columns);
        otherwise they become STRING fields.

        Returns ``{"fields": [...]}`` sorted by field name.
        """
        df = dataframe.copy()
        has_json_columns = df["data_type"].str.lower().isin(["json", "jsonb"]).any()
        has_json_info = {"json_key", "json_value_type"}.issubset(df.columns)

        if parse_json_columns and has_json_columns and not has_json_info:
            raise ValueError("'json_key' and 'json_value_type' are not part of given DataFrame.")
        if not parse_json_columns and has_json_info:
            # Keep only the column rows, not the extra rows describing JSON keys.
            df = df[df["json_key"].fillna("") == ""].drop(columns=["json_key", "json_value_type"])

        fields: SchemaFields = []
        added_columns: set[str] = set()
        for _, row in df.iterrows():
            column_name = row["column_name"]
            if column_name in added_columns:
                continue
            added_columns.add(column_name)
            data_type = str(row["data_type"]).lower()

            if parse_json_columns and data_type in ("json", "jsonb"):
                json_rows = df[(df["column_name"] == column_name) & (df["json_key"].fillna("") != "")]
                key_types: dict[str, set[str]] = {}
                for _, json_row in json_rows.iterrows():
                    key_types.setdefault(json_row["json_key"], set()).add(str(json_row["json_value_type"]).lower())
                if key_types:
                    fields.append(
                        {
                            "type": "RECORD",
                            "name": column_name,
                            "mode": "NULLABLE",  # One JSON object per row
                            "fields": [_json_key_field(key, types) for key, types in key_types.items()],
                        }
                    )
                    continue
                # A RECORD needs at least one field, so JSON columns without known keys stay as STRING.

            if data_type == "array":
                mode = "REPEATED"
            else:
                mode = "REQUIRED" if str(row.get("is_nullable", "YES")).upper() == "NO" else "NULLABLE"
            fields.append(
                {
                    "type": POSTGRES_TO_BIGQUERY_TYPE_CONVERTER.get(data_type, "STRING"),
                    "name": column_name,
                    "mode": mode,
                }
            )

        return {"fields": sorted(fields, key=lambda field: field["name"])}

    @staticmethod
    def convert_multiple_postgresql_tables_schema(
        dataframe: pd.DataFrame, parse_json_columns: bool = True
    ) -> dict[str, dict[str, SchemaFields]]:
        """Like :meth:`convert_postgresql_table_schema`, for a DataFrame with one or more tables.

        Returns a dictionary keyed by ``<table_catalog>-<table_schema>-<table_name>``.
        """
        if dataframe.empty:
            return {}
        table_refs = dataframe[["table_catalog", "table_schema", "table_name"]].astype(str).agg("-".join, axis=1)
        return {
            table_ref: BigQueryTool.convert_postgresql_table_schema(
                dataframe[table_refs == table_ref], parse_json_columns=parse_json_columns
            )
            for table_ref in sorted(set(table_refs))
        }

    @staticmethod
    def convert_dataframe_to_numeric(
        dataframe: pd.DataFrame, exclude_columns: str | Iterable[str] = (), **kwargs: Any
    ) -> pd.DataFrame:
        """Convert all string columns to numbers, except those in ``exclude_columns``.

        The DataFrame is changed in place and also returned. ``kwargs`` go to
        ``pandas.to_numeric``.
        """
        excluded = {exclude_columns} if isinstance(exclude_columns, str) else set(exclude_columns)
        string_columns = dataframe.select_dtypes(include=["object", "string"]).columns
        cols = [col for col in string_columns if col not in excluded]
        if cols:
            dataframe[cols] = dataframe[cols].apply(pd.to_numeric, **kwargs)
        return dataframe

    @staticmethod
    def clean_dataframe_column_names(
        dataframe: pd.DataFrame,
        allowed_chars: str = "abcdefghijklmnopqrstuvwxyz0123456789",
        special_treatment: Mapping[str, str] | None = None,
    ) -> pd.DataFrame:
        """Return a copy of the DataFrame with column names that BigQuery accepts.

        Names are lowercased. Characters in ``special_treatment`` are replaced by their
        mapped value; the others are converted to ASCII, and any character not in
        ``allowed_chars`` becomes an underscore. Names can't start with a digit, so
        those get a leading underscore. Different names may end up the same.
        """
        special_treatment = special_treatment or {}
        column_map = {}
        for raw_name in dataframe.columns:
            clean_name = "".join(
                special_treatment[char]
                if char in special_treatment
                else "".join(c if c in allowed_chars else "_" for c in unicode_to_ascii(char))
                for char in str(raw_name).lower()
            )
            if not clean_name or clean_name[0].isdigit():
                clean_name = "_" + clean_name
            column_map[raw_name] = clean_name

        logger.debug("column_map = %s", column_map)
        return dataframe.rename(columns=column_map)

    # -- Uploads -------------------------------------------------------------

    def upload(self, dataframe: pd.DataFrame, dataset: str, table: str, **kwargs: Any) -> None:
        """Clean the DataFrame column names and load it into ``dataset.table``.

        ``kwargs`` go to ``pandas_gbq.to_gbq``; by default it uses this tool's project
        and credentials. Like ``to_gbq``, it fails if the table exists unless
        ``if_exists="append"`` or ``"replace"`` is given.
        """
        dataframe = self.clean_dataframe_column_names(dataframe)
        kwargs.setdefault("project_id", self.client.project)
        if self._google_credentials is not None:
            kwargs.setdefault("credentials", self._google_credentials)

        logger.info("Starting upload...")
        pandas_gbq.to_gbq(dataframe, f"{dataset}.{table}", **kwargs)

    @classmethod
    def _parse_schema(cls, schema: Schema) -> list[bigquery.SchemaField]:
        """Convert a JSON-style schema into ``SchemaField`` objects for the BigQuery API."""
        fields = schema["fields"] if isinstance(schema, Mapping) else schema

        job_schema = []
        for column_info in fields:
            if not column_info.get("name") or not column_info.get("type"):
                raise ValueError("Field incomplete. Doesn't have name and/or type parameters.")
            mode = column_info.get("mode") or "NULLABLE"

            nested_fields: tuple[bigquery.SchemaField, ...] = ()
            if str(column_info["type"]).upper() in ("RECORD", "STRUCT"):
                if not column_info.get("fields"):
                    raise ValueError(f"Field {column_info['name']} has RECORD type, but no associated nested fields")
                nested_fields = tuple(cls._parse_schema(column_info["fields"]))

            optional: dict[str, Any] = {}
            if column_info.get("description") is not None:
                optional["description"] = column_info["description"]
            job_schema.append(
                bigquery.SchemaField(
                    column_info["name"], column_info["type"], mode=mode, fields=nested_fields, **optional
                )
            )
        return job_schema

    def _prepare_load_job(
        self,
        dataset: str,
        table: str,
        file_format: str = "CSV",
        header_rows: int = 1,
        delimiter: str = ",",
        encoding: str = "UTF-8",
        ignore_unknown_values: bool = False,
        max_bad_records: int = 0,
        writing_mode: str = "APPEND",
        create_table_if_needed: bool = False,
        schema: Schema | None = None,
    ) -> tuple[bigquery.LoadJobConfig, bigquery.TableReference]:
        """Job configuration shared by :meth:`upload_from_gcs` and :meth:`upload_from_file`."""
        write_disposition = self._write_disposition(writing_mode)
        file_format = file_format.upper()
        try:
            source_format = SOURCE_FORMATS[file_format]
        except KeyError:
            raise ValueError(f"Unsupported format {file_format}. Formats available: {list(SOURCE_FORMATS)}") from None

        job_config = bigquery.LoadJobConfig(
            source_format=source_format,
            ignore_unknown_values=ignore_unknown_values,
            max_bad_records=max_bad_records,
        )
        if file_format == "CSV":
            job_config.skip_leading_rows = header_rows
            job_config.field_delimiter = delimiter
            job_config.encoding = encoding

        table_ref = self._table_ref(dataset, table)
        if self._check_destination(dataset, table_ref, create_table_if_needed):
            job_config.write_disposition = write_disposition
        elif schema is not None:
            job_config.schema = self._parse_schema(schema)
        elif file_format in ("CSV", "JSON"):
            job_config.autodetect = True
        else:
            raise ValueError("No schema given. Schema autodetection is supported only for CSV and JSON file formats.")

        return job_config, table_ref

    def upload_from_gcs(
        self,
        dataset: str,
        table: str,
        gs_path: str,
        file_format: str = "CSV",
        header_rows: int = 1,
        delimiter: str = ",",
        encoding: str = "UTF-8",
        ignore_unknown_values: bool = False,
        max_bad_records: int = 0,
        writing_mode: str = "APPEND",
        create_table_if_needed: bool = False,
        schema: Schema | None = None,
    ) -> None:
        """Load data from Google Cloud Storage (``gs_path``, wildcards allowed) into ``dataset.table``.

        - ``file_format``: 'AVRO', 'CSV' (default), 'JSON' (newline-delimited), 'ORC' or 'PARQUET'.
        - ``header_rows``, ``delimiter`` and ``encoding`` ('UTF-8' or 'ISO-8859-1') apply to CSV only.
        - ``ignore_unknown_values``: ignore values not in the table schema instead of
          treating those records as bad.
        - ``max_bad_records``: maximum number of bad records allowed before failing (default 0).
        - ``writing_mode``: 'APPEND' (default), 'EMPTY' or 'TRUNCATE'; applies when the table exists.
        - ``create_table_if_needed``: create the table instead of raising ``NotFound``.
        - ``schema``: list of field dictionaries, or ``{"fields": [...]}`` as in a JSON
          schema file. Only needed to create the table from AVRO, ORC or PARQUET files;
          otherwise it's autodetected.
        """
        job_config, table_ref = self._prepare_load_job(
            dataset=dataset,
            table=table,
            file_format=file_format,
            header_rows=header_rows,
            delimiter=delimiter,
            encoding=encoding,
            ignore_unknown_values=ignore_unknown_values,
            max_bad_records=max_bad_records,
            writing_mode=writing_mode,
            create_table_if_needed=create_table_if_needed,
            schema=schema,
        )
        self._wait_for(self.client.load_table_from_uri(gs_path, table_ref, job_config=job_config))

    def upload_from_file(
        self,
        dataset: str,
        table: str,
        file_location: str,
        file_format: str = "CSV",
        header_rows: int = 1,
        delimiter: str = ",",
        encoding: str = "UTF-8",
        ignore_unknown_values: bool = False,
        max_bad_records: int = 0,
        writing_mode: str = "APPEND",
        create_table_if_needed: bool = False,
        schema: Schema | None = None,
    ) -> None:
        """Load data from a local file into ``dataset.table``. Options are the same as :meth:`upload_from_gcs`."""
        job_config, table_ref = self._prepare_load_job(
            dataset=dataset,
            table=table,
            file_format=file_format,
            header_rows=header_rows,
            delimiter=delimiter,
            encoding=encoding,
            ignore_unknown_values=ignore_unknown_values,
            max_bad_records=max_bad_records,
            writing_mode=writing_mode,
            create_table_if_needed=create_table_if_needed,
            schema=schema,
        )
        with open(file_location, "rb") as source_file:
            load_job = self.client.load_table_from_file(source_file, table_ref, job_config=job_config)
        self._wait_for(load_job)

    # -- Data Transfer Service ----------------------------------------------------

    def start_transfer(
        self, project_path: str | None = None, project_name: str | None = None, transfer_name: str | None = None
    ) -> str:
        """Start a manual run of a BigQuery Data Transfer and return its state (e.g. "PENDING").

        Either give the transfer config resource name as ``project_path``
        (``projects/<id>/locations/<loc>/transferConfigs/<config>``), or the
        ``transfer_name`` (display name), optionally with the ``project_name`` of a
        Google connection in the credential store (defaults to this tool's project).
        """
        if self.transfer_client is None:
            self.transfer_client = bigquery_datatransfer_v1.DataTransferServiceClient(
                credentials=self._google_credentials
            )

        if project_path is None:
            if transfer_name is None:
                logger.error("Specify either project and transfer names or transferConfig project path.")
                raise ValueError("Specify either project and transfer names or transferConfig project path.")
            project_id = self._project_id_for(project_name)

            parent = self.transfer_client.common_project_path(project_id)
            matches = [
                config.name
                for config in self.transfer_client.list_transfer_configs(parent=parent)
                if config.display_name == transfer_name
            ]
            if not matches:
                logger.error("No transfer with display name %r was found.", transfer_name)
                raise NameError(f"No transfer with display name {transfer_name!r} was found.")
            project_path = matches[0]

        response = self.transfer_client.start_manual_transfer_runs(
            request={"parent": project_path, "requested_run_time": datetime.now(UTC)}
        )
        state: str = response.runs[0].state.name
        return state

    def _project_id_for(self, project_name: str | None) -> str:
        """Project ID for a project name, looked up in this tool's project and the credential store."""
        if project_name is None:
            return str(self.project["id"] if self.project and self.project["id"] else self.client.project)
        if self.project is not None and project_name == self.project["name"]:
            return str(self.project["id"])

        for settings in get_default_store().get_service("google").values():
            if settings.get("project_name") == project_name:
                return str(settings["project_id"])

        message = (
            "Project name not found in the credential store. "
            "Add it to the credentials or use the project_path parameter instead."
        )
        logger.error(message)
        raise KeyError(message)


def _json_key_field(key: str, json_types: set[str]) -> dict[str, Any]:
    """Schema field for a JSON key; keys seen with more than one value type become STRING."""
    if len(json_types) > 1:
        return {"type": "STRING", "name": key, "mode": "NULLABLE"}
    (json_type,) = json_types
    return {
        "type": JSON_TO_BIGQUERY_TYPE_CONVERTER.get(json_type, "STRING"),
        "name": key,
        "mode": "REPEATED" if json_type == "array" else "NULLABLE",
    }


def _schema_field_to_dict(field: bigquery.SchemaField) -> dict[str, Any]:
    column_schema: dict[str, Any] = {"name": field.name, "type": field.field_type, "mode": field.mode}
    # Only added if they contain relevant information
    if field.description is not None:
        column_schema["description"] = field.description
    if field.fields:
        column_schema["fields"] = [_schema_field_to_dict(nested) for nested in field.fields]
    return column_schema
