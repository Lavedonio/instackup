# redshift_tools
This is the documentation for the redshift_tools module and all its contents, with usage examples.

This module needs the `redshift` extra: `pip install 'instackup[redshift]'`.

Credentials come from the credential store, which can be set with environment variables or a credentials file, or from the cloud platform identity (see [credentials.md](credentials.md)).

# Index
- [RedShiftTool](#redshifttool)
  - [\_\_init\_\_(self, connection="default", connect_by_cluster=True, \*, credentials=None, session=None, iam_role=None)](#__init__self-connectiondefault-connect_by_clustertrue--credentialsnone-sessionnone-iam_rolenone)
  - [session(self) @property](#sessionself-property)
  - [connect(self, fail_silently=False)](#connectself-fail_silentlyfalse)
  - [commit(self)](#commitself)
  - [rollback(self)](#rollbackself)
  - [close_connection(self)](#close_connectionself)
  - [execute_sql(self, command, fail_silently=False, \*, params=None)](#execute_sqlself-command-fail_silentlyfalse--paramsnone)
  - [query(self, sql_query, fetch_through_pandas=True, fail_silently=False, \*, params=None)](#queryself-sql_query-fetch_through_pandastrue-fail_silentlyfalse--paramsnone)
  - [describe_table(self, table, schema="public", fetch_through_pandas=True, fail_silently=False)](#describe_tableself-table-schemapublic-fetch_through_pandastrue-fail_silentlyfalse)
  - [get_all_db_info(self, get_json_info=True, fetch_through_pandas=True, fail_silently=False)](#get_all_db_infoself-get_json_infotrue-fetch_through_pandastrue-fail_silentlyfalse)
  - [unload_to_S3(self, redshift_query, s3_path, filename, unload_options="MANIFEST GZIP ALLOWOVERWRITE REGION 'us-east-2'", \*, iam_role=None)](#unload_to_s3self-redshift_query-s3_path-filename-unload_optionsmanifest-gzip-allowoverwrite-region-us-east-2--iam_rolenone)

# Module Contents
## RedShiftTool
This class handles most of the interaction needed with RedShift, so the base code becomes more readable and straightforward. It inherits from [PostgreSQLTool](sql_tools.md#postgresqltool), so its attributes and methods can (and will) be accessed from this class.

This class implements the with statement, so there are 2 ways of using it.

**1st way:**

```python
from instackup.redshift_tools import RedShiftTool

with RedShiftTool() as rs:
    # use rs object to interact with RedShift database
    df = rs.query("SELECT 1 AS one")
```

When leaving the with block, the transaction is committed (or rolled back, if an exception was raised) and the connection is closed.

**2nd way:**

```python
from instackup.redshift_tools import RedShiftTool

rs = RedShiftTool()
rs.connect()

try:
    # use rs object to interact with RedShift database
    df = rs.query("SELECT 1 AS one")
except Exception as e:
    rs.rollback()
    raise e
else:
    rs.commit()
finally:
    rs.close_connection()
```

Easy to see that it is recommended (and easier) to use the first syntax.

Using the tool before connecting (e.g. calling query or commit) raises a `RuntimeError`.

### \_\_init\_\_(self, connection="default", connect_by_cluster=True, \*, credentials=None, session=None, iam_role=None)
Initialization takes the _connection_ parameter, which selects which connection of the `redshift` service in the credential store to use, and the _connect_by_cluster_ parameter, which sets the connection type:
- True (default): uses the `cluster_credentials` settings (dbname, user, host, cluster_id and port). A temporary password is requested from the Redshift API (`GetClusterCredentials`) each time [connect](#connectself-fail_silentlyfalse) is called; it expires after 15 minutes, so call connect again to open a new connection after that.
- False: uses the `master_password` settings (dbname, user, host, password and port).

The port defaults to 5439. Raises a `KeyError` (`CredentialsNotFoundError`) if the connection has no settings for the chosen connection type.

The keyword-only parameters are:
- _credentials_: the connection settings given directly, either with the same nested structure (`cluster_credentials`/`master_password`) or just the flat settings of the chosen connection type;
- _session_: a ready `boto3.Session`, used instead of creating one (see the [session](#sessionself-property) property);
- _iam_role_: the ARN of the IAM role that authorizes [unload_to_S3](#unload_to_s3self-redshift_query-s3_path-filename-unload_optionsmanifest-gzip-allowoverwrite-region-us-east-2--iam_rolenone); defaults to the connection's `iam_role` setting.

AWS credentials are only needed to get the cluster credentials or to run an UNLOAD without an IAM role. AWS keys aren't kept as attributes of the tool anymore (there are no `access_key`/`secret_key` attributes); they stay in the session.

It has no return value.

The \_\_init\_\_ method doesn't actually open the connection, but sets all values required by the connect method.

Usage example:
```python
import os
from instackup.redshift_tools import RedShiftTool

rs = RedShiftTool()

# or

rs = RedShiftTool(connection="analytics", iam_role="arn:aws:iam::123456789012:role/redshift-unload")

# or

rs = RedShiftTool(
    connect_by_cluster=False,
    credentials={
        "host": "cluster.abc123.us-east-2.redshift.amazonaws.com",
        "dbname": "db",
        "user": "masteruser",
        "password": os.environ["REDSHIFT_PASSWORD"],
    },
)
```

### session(self) @property
Returns the `boto3.Session` used for the Redshift API (cluster credentials) and for the AWS credentials of [unload_to_S3](#unload_to_s3self-redshift_query-s3_path-filename-unload_optionsmanifest-gzip-allowoverwrite-region-us-east-2--iam_rolenone) when no IAM role is set.

It's the session given in \_\_init\_\_ or, if none was given, one created on first use from the `aws` settings with the same connection name as the tool or, if there are none, from the `default` AWS connection. Without any AWS settings, boto3's default credential chain is used (environment, shared config/SSO, container and instance roles).

Usage example:
```python
from instackup.redshift_tools import RedShiftTool

rs = RedShiftTool()

clusters = rs.session.client("redshift").describe_clusters()
```

### connect(self, fail_silently=False)
Creates the connection and returns its own object, so it can be used in a with statement. If _connect_by_cluster_ was set to True, it first requests temporary cluster credentials (stored in the _cluster_creds_ attribute).

If _fail_silently_ parameter is set to True, database and AWS errors will be logged instead of raised, so they don't stop the code execution; in that case, None is returned.

Usage example:
```python
from instackup.redshift_tools import RedShiftTool

rs = RedShiftTool()
rs.connect()
# remember to close the connection later

# or

with RedShiftTool() as rs:
    # Already connected, use rs object in this context
    df = rs.query("SELECT 1 AS one")
```

### commit(self)
Commits any pending transaction to the database. It has no extra parameter or return value.

Usage example:
```python
from instackup.redshift_tools import RedShiftTool

rs = RedShiftTool()
rs.connect()
# Do stuff
rs.commit()
# remember to close the connection later

# or

with RedShiftTool() as rs:
    # Already connected, use rs object in this context

    # Do stuff

    # No need to explicitly commit as it will do when leaving this context, but nonetheless:
    rs.commit()
```

### rollback(self)
Rolls back to the start of any pending transaction. It has no extra parameter or return value.

Usage example:
```python
from instackup.redshift_tools import RedShiftTool

rs = RedShiftTool()
rs.connect()

try:
    # Do stuff
    rs.execute_sql("CREATE TABLE test (id integer)")
except Exception as e:
    rs.rollback()
    raise e
else:
    rs.commit()
finally:
    # remember to close the connection later
    rs.close_connection()

# or

with RedShiftTool() as rs:
    # Already connected, use rs object in this context

    # Do stuff

    # No need to explicitly commit or rollback as it will do when leaving this context, but nonetheless:
    if meet_condition:
        rs.commit()
    else:
        rs.rollback()
```

### close_connection(self)
Closes the connection with the RedShift database. It has no extra parameter or return value.

Usage example:
```python
from instackup.redshift_tools import RedShiftTool

rs = RedShiftTool()
rs.connect()

try:
    # Do stuff
    rs.execute_sql("CREATE TABLE test (id integer)")
except Exception as e:
    rs.rollback()
    raise e
else:
    rs.commit()
finally:
    rs.close_connection()

# or

with RedShiftTool() as rs:
    # Already connected, use rs object in this context

    # Do stuff
    rs.execute_sql("CREATE TABLE test (id integer)")

    # Will close the connection automatically when exiting this scope
```

### execute_sql(self, command, fail_silently=False, \*, params=None)
Executes a SQL _command_ (CREATE, UPDATE, DROP...). It has no return value.

If _fail_silently_ parameter is set to True, database errors will be logged instead of raised, so they don't stop the code execution.

The keyword-only _params_ parameter (a sequence or a mapping) has values that are bound by the database driver (psycopg2), using `%s` placeholders in the command.

Usage example:
```python
from instackup.redshift_tools import RedShiftTool


sql_cmd = """CREATE TABLE test (
    id          integer NOT NULL PRIMARY KEY,
    username    varchar(40) UNIQUE NOT NULL,
    fullname    varchar(64) NOT NULL,
    created_at  TIMESTAMP NOT NULL,
    last_login  TIMESTAMP
);
"""


rs = RedShiftTool()
rs.connect()

try:
    # Execute the command
    rs.execute_sql(sql_cmd)

    # Execute a command with parameters
    rs.execute_sql(
        "INSERT INTO test (id, username, fullname, created_at) VALUES (%s, %s, %s, GETDATE())",
        params=(1, "jdoe", "John Doe"),
    )

except Exception as e:
    rs.rollback()
    raise e
else:
    rs.commit()
finally:
    # remember to close the connection later
    rs.close_connection()

# or

with RedShiftTool() as rs:
    # Already connected, use rs object in this context

    # This command would throw an error (since the table already was created before),
    # but since fail_silently parameter is set to True, it'll log the exception
    # and let the code continue past this point.
    rs.execute_sql(sql_cmd, fail_silently=True)

    # other code
```

### query(self, sql_query, fetch_through_pandas=True, fail_silently=False, \*, params=None)
Runs a query and returns the results.

If _fetch_through_pandas_ parameter is True, the results are returned as a Pandas DataFrame; otherwise, as a list of tuples, one per row, with values in the order of the SELECT columns.

If _fail_silently_ parameter is set to True, database errors will be logged instead of raised, so they don't stop the code execution; in that case, None is returned.

The keyword-only _params_ parameter works as in [execute_sql](#execute_sqlself-command-fail_silentlyfalse--paramsnone).

Backticks (BigQuery/MySQL style table quotes) are removed from the query, since RedShift doesn't support them.

Usage example:
```python
from instackup.redshift_tools import RedShiftTool


sql_query = """SELECT * FROM users LIMIT 100"""


rs = RedShiftTool()
rs.connect()

try:
    # Returns a list of tuples containing the rows of the response
    table = rs.query(sql_query, fetch_through_pandas=False, fail_silently=True)

    # Do something with table variable

except Exception as e:
    rs.rollback()
    raise e
else:
    rs.commit()
finally:
    # remember to close the connection later
    rs.close_connection()

# or

with RedShiftTool() as rs:
    # Already connected, use rs object in this context

    # Returns a Pandas DataFrame
    df = rs.query(sql_query)

    # Query with parameters
    df = rs.query("SELECT * FROM users WHERE id = %s", params=(1,))

    # other code
```

### describe_table(self, table, schema="public", fetch_through_pandas=True, fail_silently=False)
Special query that returns all INFORMATION_SCHEMA.COLUMNS metadata of a specific _table_ in the given _schema_.

_fetch_through_pandas_ and _fail_silently_ parameters work as in the [query](#queryself-sql_query-fetch_through_pandastrue-fail_silentlyfalse--paramsnone) method.

Usage example:
```python
from instackup.redshift_tools import RedShiftTool


rs = RedShiftTool()
rs.connect()

try:
    # Returns a list of tuples containing the rows of the response (Table: public.users)
    table = rs.describe_table("users", fetch_through_pandas=False, fail_silently=True)

    # Do something with table variable

except Exception as e:
    rs.rollback()
    raise e
else:
    rs.commit()
finally:
    # remember to close the connection later
    rs.close_connection()

# or

with RedShiftTool() as rs:
    # Already connected, use rs object in this context

    # Returns a Pandas DataFrame with all schema info of that specific schema.table
    df = rs.describe_table("airflow_logs", schema="another_schema")

    # other code
```

### get_all_db_info(self, get_json_info=True, fetch_through_pandas=True, fail_silently=False)
Gets all database columns info, using an INFORMATION_SCHEMA.COLUMNS query.

Ignores the pg_stat_statements table and tables inside the pg_catalog and information_schema schemas.

If _get_json_info_ parameter is True, it adds the json_key and json_value_type columns, with one extra row for each key found in each json and jsonb column. Only JSON object values are expanded.

_fetch_through_pandas_ and _fail_silently_ parameters are passed directly to the _query_ method if _get_json_info_ parameter is set to False; if it's not, a DataFrame is always returned and errors are always raised.

Returns a DataFrame if either _get_json_info_ or _fetch_through_pandas_ parameters are set to True; otherwise returns a list of tuples, each representing a row, with their position in the same order as in the columns of the INFORMATION_SCHEMA.COLUMNS table.

Usage example:
```python
from instackup.redshift_tools import RedShiftTool


rs = RedShiftTool()
rs.connect()

try:
    # Returns a list of tuples containing the rows of the response
    schema_info = rs.get_all_db_info(get_json_info=False, fetch_through_pandas=False, fail_silently=True)

    # Do something with schema_info variable

except Exception as e:
    rs.rollback()
    raise e
else:
    rs.commit()
finally:
    # remember to close the connection later
    rs.close_connection()

# or

with RedShiftTool() as rs:
    # Already connected, use rs object in this context

    # Returns a Pandas DataFrame with all schema info
    df = rs.get_all_db_info()

    # other code
```

### unload_to_S3(self, redshift_query, s3_path, filename, unload_options="MANIFEST GZIP ALLOWOVERWRITE REGION 'us-east-2'", \*, iam_role=None)
Executes an UNLOAD command in the RedShift database to copy the results of a query to S3. It has no return value.

Takes the parameters _redshift_query_ to grab the data, _s3_path_ to set the location of copied data, _filename_ as the custom prefix of the files (they're written to `<s3_path>/<filename>_*`) and _unload_options_.

The command is authorized with an IAM role, which is recommended: the keyword-only _iam_role_ parameter or, if not given, the role set in \_\_init\_\_ or in the connection's `iam_role` setting. Without a role, the AWS credentials of the [session](#sessionself-property) (access key, secret key and session token, if any) are embedded in the command, which is never logged. Raises a `KeyError` (`CredentialsNotFoundError`) if there's neither a role nor AWS credentials.

Errors are always raised.

Unload options can be better understood in this link: https://docs.aws.amazon.com/redshift/latest/dg/r_UNLOAD.html

Usage example:
```python
from instackup.redshift_tools import RedShiftTool


# Maybe you'll get this timestamp from other source
timestamp = "2019-11-29 19:31:42.766000+00:00"
extraction_query = f"SELECT * FROM schema.table WHERE tstamp = '{timestamp}'"

s3_path = "s3://redshift-data/unload/"
filename = "file"
unload_options = "DELIMITER '|' ESCAPE ADDQUOTES"


rs = RedShiftTool()
rs.connect()

try:
    # Unload data with custom options
    rs.unload_to_S3(extraction_query, s3_path, filename, unload_options)

except Exception as e:
    rs.rollback()
    raise e
else:
    rs.commit()
finally:
    # remember to close the connection later
    rs.close_connection()

# or

with RedShiftTool() as rs:
    # Already connected, use rs object in this context

    # Unload data without custom options (will overwrite), authorized by an IAM role
    rs.unload_to_S3(
        extraction_query, s3_path, filename, iam_role="arn:aws:iam::123456789012:role/redshift-unload"
    )

    # other code
```
