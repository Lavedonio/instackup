# bigquery_tools
This is the documentation for the bigquery_tools module and all its contents, with usage examples.

This module needs the `gcp` extra: `pip install 'instackup[gcp]'`.

Credentials come from environment variables, a credentials file or the cloud platform identity (see [credentials.md](credentials.md)).

# Index
- [Global Variables](#global-variables)
- [BigQueryTool](#bigquerytool)
  - [\_\_init\_\_(self, connection="default", authenticate=True, \*, credentials=None, client=None)](#__init__self-connectiondefault-authenticatetrue--credentialsnone-clientnone)
  - [query(self, sql_query)](#queryself-sql_query)
  - [query_and_save_results(self, sql_query, dest_dataset, dest_table, writing_mode="TRUNCATE", create_table_if_needed=False)](#query_and_save_resultsself-sql_query-dest_dataset-dest_table-writing_modetruncate-create_table_if_neededfalse)
  - [list_datasets(self)](#list_datasetsself)
  - [create_dataset(self, dataset, location="US")](#create_datasetself-dataset-locationus)
  - [list_dataset_permissions(self, dataset)](#list_dataset_permissionsself-dataset)
  - [add_dataset_permission(self, dataset, role, email_type, email)](#add_dataset_permissionself-dataset-role-email_type-email)
  - [remove_dataset_permission(self, dataset, email)](#remove_dataset_permissionself-dataset-email)
  - [list_tables_in_dataset(self, dataset, get=None, return_type="dict")](#list_tables_in_datasetself-dataset-getnone-return_typedict)
  - [get_table_schema(self, dataset, table)](#get_table_schemaself-dataset-table)
  - [convert_postgresql_table_schema(dataframe, parse_json_columns=True) @staticmethod](#convert_postgresql_table_schemadataframe-parse_json_columnstrue-staticmethod)
  - [convert_multiple_postgresql_tables_schema(dataframe, parse_json_columns=True) @staticmethod](#convert_multiple_postgresql_tables_schemadataframe-parse_json_columnstrue-staticmethod)
  - [convert_dataframe_to_numeric(dataframe, exclude_columns=(), \*\*kwargs) @staticmethod](#convert_dataframe_to_numericdataframe-exclude_columns-kwargs-staticmethod)
  - [clean_dataframe_column_names(dataframe, allowed_chars="abcdefghijklmnopqrstuvwxyz0123456789", special_treatment=None) @staticmethod](#clean_dataframe_column_namesdataframe-allowed_charsabcdefghijklmnopqrstuvwxyz0123456789-special_treatmentnone-staticmethod)
  - [upload(self, dataframe, dataset, table, \*\*kwargs)](#uploadself-dataframe-dataset-table-kwargs)
  - [create_empty_table(self, dataset, table, schema)](#create_empty_tableself-dataset-table-schema)
  - [upload_from_gcs(self, dataset, table, gs_path, file_format="CSV", header_rows=1, delimiter=",", encoding="UTF-8", ignore_unknown_values=False, max_bad_records=0, writing_mode="APPEND", create_table_if_needed=False, schema=None)](#upload_from_gcsself-dataset-table-gs_path-file_formatcsv-header_rows1-delimiter-encodingutf-8-ignore_unknown_valuesfalse-max_bad_records0-writing_modeappend-create_table_if_neededfalse-schemanone)
  - [upload_from_file(self, dataset, table, file_location, file_format="CSV", header_rows=1, delimiter=",", encoding="UTF-8", ignore_unknown_values=False, max_bad_records=0, writing_mode="APPEND", create_table_if_needed=False, schema=None)](#upload_from_fileself-dataset-table-file_location-file_formatcsv-header_rows1-delimiter-encodingutf-8-ignore_unknown_valuesfalse-max_bad_records0-writing_modeappend-create_table_if_neededfalse-schemanone)
  - [start_transfer(self, project_path=None, project_name=None, transfer_name=None)](#start_transferself-project_pathnone-project_namenone-transfer_namenone)

# Module Contents
## Global Variables
There are some global variables that can be accessed and edited by the user. Those are:
- **POSTGRES_TO_BIGQUERY_TYPE_CONVERTER**: Dictionary that is used to convert the column types from PostgreSQL to BigQuery Standard SQL. Types not in it become STRING.
- **JSON_TO_BIGQUERY_TYPE_CONVERTER**: Dictionary that is used to convert the value types from JSON fields into BigQuery Standard SQL. Types not in it become STRING.
- **TABLE_LIST_ATTRIBUTES**: Tuple with the table attributes that can be returned by the [list_tables_in_dataset](#list_tables_in_datasetself-dataset-getnone-return_typedict) method.
- **WRITE_DISPOSITIONS**: Dictionary with the supported writing modes ('APPEND', 'EMPTY' and 'TRUNCATE') and their BigQuery write dispositions.
- **SOURCE_FORMATS**: Dictionary with the supported file formats ('AVRO', 'CSV', 'JSON', 'ORC' and 'PARQUET') and their BigQuery source formats.

## BigQueryTool
This class handles most of the interaction needed with BigQuery, so the base code becomes more readable and straightforward.

In the methods that take a _dataset_ name, it can also be given as `project.dataset` to use a dataset from another project.

### \_\_init\_\_(self, connection="default", authenticate=True, \*, credentials=None, client=None)
The initialization process sets the BigQuery client (the _client_ attribute).

The client authenticates with the `google` service settings of the _connection_ parameter in the credential store (a service account key file or info, and the project). Without them, Application Default Credentials are used (e.g. Workload Identity, the Cloud Run/Compute Engine metadata server or `gcloud auth application-default login`). A named connection other than "default" must exist in the credential store.

The _authenticate_ parameter sets whether the credential store is used. If set to False, Application Default Credentials are used directly, which might be desired if the environment is already authenticated, for example in a Google Cloud Composer environment.

The keyword-only _credentials_ parameter takes the `google` settings directly (used even if _authenticate_ is False), and the keyword-only _client_ parameter takes a ready `google.cloud.bigquery.Client`.

The _project_ attribute is a dictionary with the "id", "name" and "number" of the project from the settings, or None if there are no settings (or a client was given).

Usage example:
```python
from instackup.bigquery_tools import BigQueryTool


bq = BigQueryTool()

# or, with another connection from the credential store

bq = BigQueryTool(connection="analytics")

# or, using Application Default Credentials directly

bq = BigQueryTool(authenticate=False)
```

### query(self, sql_query)
Runs a SQL query and returns the results as a Pandas DataFrame. Errors are logged and raised.

Usage example:
```python
from instackup.bigquery_tools import BigQueryTool


bq = BigQueryTool()

sql_query = """SELECT * FROM `project_name.dataset.table`"""
df = bq.query(sql_query)
```

### query_and_save_results(self, sql_query, dest_dataset, dest_table, writing_mode="TRUNCATE", create_table_if_needed=False)
Executes a query and saves the result in a table. It has no return value.

_writing_mode_ parameter determines how the data is going to be written in BigQuery.
Does not apply if the table doesn't exist. Can be one of 3 types (defaults to 'TRUNCATE'):
- APPEND: If the table already exists, BigQuery appends the data to the table.
- EMPTY: If the table already exists and contains data, a 'duplicate' error
         is returned in the job result.
- TRUNCATE: If the table already exists, BigQuery overwrites the table data.

An invalid _writing_mode_ raises a `ValueError`, even when the table is going to be created.

If _create_table_if_needed_ is set to False and the table doesn't exist, it'll raise a `NotFound` error. Defaults to False.

Usage example:
```python
from instackup.bigquery_tools import BigQueryTool


# Enter valid values here
dest_dataset = "dataset"
dest_table = "some_other_table"
sql_query = """SELECT * FROM `project_name.dataset.table`"""

bq = BigQueryTool()

bq.query_and_save_results(sql_query, dest_dataset, dest_table, create_table_if_needed=True)
```

### list_datasets(self)
Returns a list with all dataset names inside the project.

Usage example:
```python
from instackup.bigquery_tools import BigQueryTool


bq = BigQueryTool()

datasets = bq.list_datasets()

print(f"There are {len(datasets)} datasets, which are listed below:\n")
for ds in datasets:
    print(ds)
```

### create_dataset(self, dataset, location="US")
Creates a new dataset in the given _location_. It has no return value.

Usage example:
```python
from instackup.bigquery_tools import BigQueryTool


bq = BigQueryTool()

bq.create_dataset("google_analytics_reports")
bq.create_dataset("other_project.google_analytics_reports", location="southamerica-east1")
```

### list_dataset_permissions(self, dataset)
Returns a list with all the permissions (`google.cloud.bigquery.AccessEntry` objects) of the given dataset.

Usage example:
```python
from instackup.bigquery_tools import BigQueryTool


dataset = "dataset"  # Enter a valid dataset name

bq = BigQueryTool()

print("Current permissions:")
print(bq.list_dataset_permissions(dataset))
```

### add_dataset_permission(self, dataset, role, email_type, email)
Adds a permission to a dataset, given its predefined role, email_type and email. It has no return value.

email_type parameter can be one of the following:
- 'domain'
- 'groupByEmail'
- 'group' (same as 'groupByEmail')
- 'iamMember'
- 'specialGroup'
- 'userByEmail'
- 'user' (same as 'userByEmail')
- 'view'

Usage example:
```python
from instackup.bigquery_tools import BigQueryTool


dataset = "dataset"  # Enter a valid dataset name
email = "some_email_group@company.com"  # Enter a valid email
email_type = "group"
role = "READER"


bq = BigQueryTool()

bq.add_dataset_permission(dataset, role, email_type, email)

print("New permissions:")
print(bq.list_dataset_permissions(dataset))
```

### remove_dataset_permission(self, dataset, email)
Removes every permission of the given email (entity_id, case-insensitive) from a dataset. It has no return value.
Nothing changes if there's no match.

Usage example:
```python
from instackup.bigquery_tools import BigQueryTool


dataset = "dataset"  # Enter a valid dataset name
email = "someone@company.com"  # Enter a valid email


bq = BigQueryTool()

bq.remove_dataset_permission(dataset, email)

print("New permissions:")
print(bq.list_dataset_permissions(dataset))
```

### list_tables_in_dataset(self, dataset, get=None, return_type="dict")
Lists all tables inside a dataset. Will fail if the dataset doesn't exist.

_get_ parameter can be a string or a list of strings. If only one attribute is selected,
it will return a list of values of that attribute of all tables
(this case overrides the return_type parameter). If it's not set, all attributes are returned.

Valid _get_ parameters (the TABLE_LIST_ATTRIBUTES global variable) are:
["clustering_fields", "created", "dataset_id", "expires", "friendly_name",
"full_table_id", "labels", "partition_expiration", "partitioning_type", "project",
"reference", "table_id", "table_type", "time_partitioning", "view_use_legacy_sql"]

_return_type_ parameter can be 1 out of 3 types and sets how the result will be returned:
- dict: dictionary of lists, i.e., each key has a list of all tables values for that attribute.
        The same index for different attributes refers to the same table;
- list: list of dictionaries, i.e., each item in the list is a dictionary with all the attributes
        of the respective table;
- dataframe: Pandas DataFrame, with one row per table.

An invalid _get_ or _return_type_ value raises a `ValueError`.

Usage example:
```python
from instackup.bigquery_tools import BigQueryTool


bq = BigQueryTool()

dataset = "dataset"  # Enter a valid dataset name

tables = bq.list_tables_in_dataset(dataset, get="table_id")  # Getting only table name

print(f"There are {len(tables)} tables in {dataset}, which are listed below:\n")
for tb in tables:
    print(tb)

# Getting all table info
df = bq.list_tables_in_dataset(dataset, return_type="dataframe")
print(df)
```

### get_table_schema(self, dataset, table)
Gets schema information from the given _dataset_ and _table_ and returns a properly formatted dictionary, `{"fields": [...]}`, the format used by the BigQuery API and CLI.

Each field is a dictionary with its name, type, mode and, if set, description. Nested fields (from RECORD columns) are also dictionaries, inside the "fields" key of their column.

Usage example:
```python
import json
from instackup.bigquery_tools import BigQueryTool


bq = BigQueryTool()

dataset = "dataset"  # Enter a valid dataset name
table = "table"      # Enter a valid table name

schema = bq.get_table_schema(dataset, table)

with open("data.json", "w") as fp:
    json.dump(schema, fp, sort_keys=True, indent=4)
```

### convert_postgresql_table_schema(dataframe, parse_json_columns=True) @staticmethod
Receives a Pandas DataFrame containing schema information (INFORMATION_SCHEMA.COLUMNS rows) from exactly one table from a PostgreSQL db and converts it to a BigQuery schema format that can be used to upload data. The DataFrame is usually built with the [PostgreSQLTool](sql_tools.md#postgresqltool) describe_table or get_all_db_info methods.

It's a static method, so it can be called on the class itself.

Column types are converted with the POSTGRES_TO_BIGQUERY_TYPE_CONVERTER global variable. Columns with is_nullable "NO" are REQUIRED, the others are NULLABLE; arrays are REPEATED.

If _parse_json_columns_ is set to False, it'll ignore json and jsonb keys, setting those columns as STRING.

If it is set to True, it'll look for json and jsonb keys and value types in the json_key and json_value_type columns, respectively, in the DataFrame, and turn each JSON column into a RECORD with one field per key (keys with more than one value type become STRING). JSON columns without known keys become STRING. If there are JSON columns and those 2 columns don't exist, this method raises a `ValueError`.

Returns a dictionary containing the BigQuery formatted schema (`{"fields": [...]}`), sorted by field name.

Usage example:
```python
import json
from instackup.bigquery_tools import BigQueryTool
from instackup.sql_tools import PostgreSQLTool


# Getting the PostgreSQL schema
with PostgreSQLTool(connection="prod_db") as pg:
    df = pg.describe_table("users")

# Converting the schema from PostgreSQL format to BigQuery format
# (describe_table doesn't get the JSON keys, so JSON columns are set as STRING)
schema = BigQueryTool.convert_postgresql_table_schema(df, parse_json_columns=False)

# Saving schema
with open("data.json", "w") as fp:
    json.dump(schema, fp, sort_keys=True, indent=4)
```

### convert_multiple_postgresql_tables_schema(dataframe, parse_json_columns=True) @staticmethod
Receives a Pandas DataFrame containing schema information from one or more tables from a PostgreSQL db and converts it to a BigQuery schema format that can be used to upload data. Each table is converted as in the [convert_postgresql_table_schema](#convert_postgresql_table_schemadataframe-parse_json_columnstrue-staticmethod) method.

It's a static method, so it can be called on the class itself.

Returns a dictionary containing the table "full name" (`<table_catalog>-<table_schema>-<table_name>`) and its respective BigQuery formatted schema as key-value pairs.

Usage example:
```python
import os
import json
from instackup.bigquery_tools import BigQueryTool
from instackup.sql_tools import PostgreSQLTool


# Getting the PostgreSQL schema from all tables in the DB
with PostgreSQLTool(connection="prod_db") as pg:
    df = pg.get_all_db_info()

# Converting all the schemas from PostgreSQL format to BigQuery format
schemas = BigQueryTool.convert_multiple_postgresql_tables_schema(df)

# Saving schemas
os.makedirs("schemas", exist_ok=True)
for name, schema in schemas.items():
    with open(os.path.join("schemas", f"{name}.json"), "w") as fp:
        json.dump(schema, fp, sort_keys=True, indent=4)
```

### convert_dataframe_to_numeric(dataframe, exclude_columns=(), \*\*kwargs) @staticmethod
Transforms all string type columns into numbers, except those in the _exclude_columns_ list. The DataFrame is changed in place and also returned.

It's a static method, so it can be called on the class itself.

_\*\*kwargs_ are passed directly to the _pandas.to_numeric_ method.
The complete documentation of this method can be found here:
https://pandas.pydata.org/docs/reference/api/pandas.to_numeric.html

Usage example:
```python
import pandas as pd
from instackup.bigquery_tools import BigQueryTool


# You can often find these kind of data when reading from a file
df = pd.DataFrame({"col.1": ["1", "2"], "col.2": ["3", "junk"], "col.3": ["string1", "string2"]})

df = BigQueryTool.convert_dataframe_to_numeric(df, exclude_columns=["col.3"], errors="coerce")
print(df)

# output:
#
#    col.1  col.2    col.3
# 0      1    3.0  string1
# 1      2    NaN  string2
```

### clean_dataframe_column_names(dataframe, allowed_chars="abcdefghijklmnopqrstuvwxyz0123456789", special_treatment=None) @staticmethod
Returns a copy of the _dataframe_ with column names that only contain chars allowed in BigQuery table column names.

It's a static method, so it can be called on the class itself.

Names are lowercased. The _special_treatment_ dictionary substitutes the characters in its keys by their values. The other characters are converted to ASCII, and if a character is not in the _allowed_chars_ string parameter, it'll be replaced by an underscore (\_). Names can't start with a digit, so those get a leading underscore. Note that different names may end up the same.

Usage example:
```python
import pandas as pd
from instackup.bigquery_tools import BigQueryTool


# You can often find these kind of data when reading from a file
df = pd.DataFrame({"col.1": ["1", "2"], "col.2": ["3", "junk"], "col.3!": ["string1", "string2"]})

df = BigQueryTool.clean_dataframe_column_names(df, special_treatment={"!": "_factorial"})
print(df)

# output:
#
#   col_1 col_2 col_3_factorial
# 0     1     3         string1
# 1     2  junk         string2
```

### upload(self, dataframe, dataset, table, \*\*kwargs)
Cleans the dataframe column names (with the [clean_dataframe_column_names](#clean_dataframe_column_namesdataframe-allowed_charsabcdefghijklmnopqrstuvwxyz0123456789-special_treatmentnone-staticmethod) method) and inserts its rows into the _dataset_._table_ table in BigQuery.

_\*\*kwargs_ are passed directly to the pandas_gbq.to_gbq function, which by default uses this tool's project and credentials. Note that pandas_gbq fails if the table already exists, unless `if_exists="append"` or `if_exists="replace"` is passed.
The complete documentation of this function can be found here:
https://googleapis.dev/python/pandas-gbq/latest/api.html#pandas_gbq.to_gbq

Usage example:
```python
import pandas as pd
from instackup.bigquery_tools import BigQueryTool


fixed_data = {
    "col1": [1, 2],
    "col2": [0.5, 0.75],
}

df = pd.DataFrame(fixed_data)

dataset = "some_dataset_name"
table = "some_table_name"

bq = BigQueryTool()
bq.upload(df, dataset, table, if_exists="append")
```

### create_empty_table(self, dataset, table, schema)
Creates an empty table at the _dataset_._table_ location, based on the _schema_ given (in the same format as the _schema_ parameter of the [upload_from_gcs](#upload_from_gcsself-dataset-table-gs_path-file_formatcsv-header_rows1-delimiter-encodingutf-8-ignore_unknown_valuesfalse-max_bad_records0-writing_modeappend-create_table_if_neededfalse-schemanone) method). It has no return value.

Usage example:
```python
from instackup.bigquery_tools import BigQueryTool


schema = {
    "fields": [
        {
            "type": "INTEGER",
            "name": "id",
            "mode": "NULLABLE"
        },
        {
            "type": "STRING",
            "name": "name",
            "mode": "NULLABLE"
        }
    ]
}

dataset = "some_dataset_name"
table = "some_table_name"

bq = BigQueryTool()
bq.create_empty_table(dataset, table, schema)
```

### upload_from_gcs(self, dataset, table, gs_path, file_format="CSV", header_rows=1, delimiter=",", encoding="UTF-8", ignore_unknown_values=False, max_bad_records=0, writing_mode="APPEND", create_table_if_needed=False, schema=None)
Uploads data from Google Cloud Storage directly to BigQuery. It has no return value.

_dataset_ and _table_ parameters determine the destination of the upload.
_gs_path_ parameter is the file location in Google Cloud Storage (wildcards are allowed).
All 3 of them are required string parameters.

_file_format_ can be either 'AVRO', 'CSV', 'JSON' (newline-delimited), 'ORC' or 'PARQUET'. Defaults to 'CSV'. Any other value raises a `ValueError`.
_header_rows_, _delimiter_ and _encoding_ are only used when _file_format_ is 'CSV'.

_header_rows_ parameter determines the length in rows of the CSV header in the file given.
Should be 0 if there are no headers in the file. Defaults to 1.

_delimiter_ determines the string character used to delimit the data. Defaults to ','.

_encoding_ tells the file encoding. Can be either 'UTF-8' or 'ISO-8859-1' (latin-1). Defaults to 'UTF-8'.

_ignore_unknown_values_ indicates if it should allow extra values that are not represented in the table schema. If True, the extra values are ignored. If False, records with extra columns are treated as bad records. Defaults to False.

_max_bad_records_ is the maximum number of bad records allowed; if it exceeds this value, it'll raise an error. Defaults to 0 (i.e. all values must be valid).

_writing_mode_ parameter determines how the data is going to be written in BigQuery.
Does not apply if the table doesn't exist. Can be 1 out of 3 types (defaults to 'APPEND'):
- APPEND: If the table already exists, BigQuery appends the data to the table.
- EMPTY: If the table already exists and contains data, a 'duplicate' error
         is returned in the job result.
- TRUNCATE: If the table already exists, BigQuery overwrites the table data.

An invalid _writing_mode_ raises a `ValueError`, even when the table is going to be created.

If _create_table_if_needed_ is set to False and the table doesn't exist, it'll raise a `NotFound` error. Defaults to False.

_schema_ is either a list of dictionaries containing the schema information or a dictionary encapsulating the previous list with a key of 'fields'. This latter format can be found when directly importing the schema info from a JSON generated file. It's only used when creating the table: if the _file_format_ is either 'CSV' or 'JSON' it can be omitted (the schema is autodetected), but for the other formats it's required.

Usage example:
```python
import json
from instackup.bigquery_tools import BigQueryTool


# Enter valid values here
dataset = "sandbox"
table = "test"
gs_path = "gs://some-bucket/some-subfolder/test.json"

# schema must be in the same format of the output of get_table_schema method.
with open("data.json", "r") as fp:
    schema = json.load(fp)

bq = BigQueryTool()
bq.upload_from_gcs(dataset, table, gs_path, file_format="JSON", create_table_if_needed=True, schema=schema)
```

### upload_from_file(self, dataset, table, file_location, file_format="CSV", header_rows=1, delimiter=",", encoding="UTF-8", ignore_unknown_values=False, max_bad_records=0, writing_mode="APPEND", create_table_if_needed=False, schema=None)
Uploads data from a local file to BigQuery. It has no return value.

_dataset_ and _table_ parameters determine the destination of the upload.
_file_location_ parameter is either the file full or relative path in the local computer.
All 3 of them are required string parameters.

_file_format_ can be either 'AVRO', 'CSV', 'JSON' (newline-delimited), 'ORC' or 'PARQUET'. Defaults to 'CSV'. Any other value raises a `ValueError`.
_header_rows_, _delimiter_ and _encoding_ are only used when _file_format_ is 'CSV'.

_header_rows_ parameter determines the length in rows of the CSV header in the file given.
Should be 0 if there are no headers in the file. Defaults to 1.

_delimiter_ determines the string character used to delimit the data. Defaults to ','.

_encoding_ tells the file encoding. Can be either 'UTF-8' or 'ISO-8859-1' (latin-1). Defaults to 'UTF-8'.

_ignore_unknown_values_ indicates if it should allow extra values that are not represented in the table schema. If True, the extra values are ignored. If False, records with extra columns are treated as bad records. Defaults to False.

_max_bad_records_ is the maximum number of bad records allowed; if it exceeds this value, it'll raise an error. Defaults to 0 (i.e. all values must be valid).

_writing_mode_ parameter determines how the data is going to be written in BigQuery.
Does not apply if the table doesn't exist. Can be 1 out of 3 types (defaults to 'APPEND'):
- APPEND: If the table already exists, BigQuery appends the data to the table.
- EMPTY: If the table already exists and contains data, a 'duplicate' error
         is returned in the job result.
- TRUNCATE: If the table already exists, BigQuery overwrites the table data.

An invalid _writing_mode_ raises a `ValueError`, even when the table is going to be created.

If _create_table_if_needed_ is set to False and the table doesn't exist, it'll raise a `NotFound` error. Defaults to False.

_schema_ is either a list of dictionaries containing the schema information or a dictionary encapsulating the previous list with a key of 'fields'. This latter format can be found when directly importing the schema info from a JSON generated file. It's only used when creating the table: if the _file_format_ is either 'CSV' or 'JSON' it can be omitted (the schema is autodetected), but for the other formats it's required.

Usage example:
```python
import json
from instackup.bigquery_tools import BigQueryTool


# Enter valid values here
dataset = "sandbox"
table = "test"
file_location = "test.csv"

# schema must be in the same format of the output of get_table_schema method.
with open("data.json", "r") as fp:
    schema = json.load(fp)

bq = BigQueryTool()
bq.upload_from_file(dataset, table, file_location, create_table_if_needed=True, schema=schema)
```

### start_transfer(self, project_path=None, project_name=None, transfer_name=None)
Takes either a transfer config path or a transfer name (and, optionally, a project name) to trigger a manual run of a transfer in the BigQuery Data Transfer Service. Returns the state name of the run (e.g. 'PENDING').

_project_path_ is the transfer config resource name, i.e. `projects/<id>/locations/<location>/transferConfigs/<config>`. Transfers in any location are supported.

_transfer_name_ is the transfer display name. It's looked up in the project of the _project_name_ parameter, a project name set in the credential store (`project_name` setting of the `google` service); if it's not set, this tool's project is used (the configured `project_id` or, otherwise, the client's project). Raises a `ValueError` if neither _project_path_ nor _transfer_name_ is given, a `KeyError` if the project name isn't found in the credential store and a `NameError` if no transfer has that display name.

API documentation: https://cloud.google.com/python/docs/reference/bigquerydatatransfer/latest

Usage example:
```python
from instackup.bigquery_tools import BigQueryTool


transfer_config = "projects/000000000000/locations/us/transferConfigs/00000000-0000-0000-0000-000000000000"

bq = BigQueryTool()

use_project_path = True
print("Starting transfer...")

# Both options do the same thing
if use_project_path:
    state_response = bq.start_transfer(project_path=transfer_config)
else:
    state_response = bq.start_transfer(project_name="project_name", transfer_name="transfer_name")

print(f"Transfer status: {state_response}")
```
