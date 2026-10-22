# sql_tools
This is the documentation for the sql_tools module and all its contents, with usage examples.

[SQLiteTool](#sqlitetool) works with a plain `pip install instackup`. The other tools need the extra of their database driver:
- [PostgreSQLTool](#postgresqltool): `pip install 'instackup[postgresql]'`
- [MySQLTool](#mysqltool): `pip install 'instackup[mysql]'`

Database drivers are only imported when a connection is opened.

Connection settings (host, port, user, password, dbname...) come from the credential store, under the `postgresql` or `mysql` service and the chosen connection, which can be set with environment variables or a credentials file (see [credentials.md](credentials.md)). They can also be given directly with the _credentials_ parameter. Besides the driver's own keyword arguments, a `url` setting (e.g. `postgresql://user:pass@host:5432/db`) is accepted.

The tools log what they do with the `logging` module (logger names start with `instackup`) instead of printing it.

# Index
- [SQLTool](#sqltool)
  - [\_\_init\_\_(self, sql_type, filename=None, connection="default", \*, credentials=None)](#__init__self-sql_type-filenamenone-connectiondefault--credentialsnone)
  - [connect(self, fail_silently=False)](#connectself-fail_silentlyfalse)
  - [commit(self)](#commitself)
  - [rollback(self)](#rollbackself)
  - [close_connection(self)](#close_connectionself)
  - [execute_sql(self, command, fail_silently=False, \*, params=None)](#execute_sqlself-command-fail_silentlyfalse--paramsnone)
  - [query(self, sql_query, fetch_through_pandas=True, fail_silently=False, \*, params=None)](#queryself-sql_query-fetch_through_pandastrue-fail_silentlyfalse--paramsnone)
- [SQLiteTool](#sqlitetool)
  - [\_\_init\_\_(self, filename=None)](#__init__self-filenamenone)
  - [describe_table(self, table, fetch_through_pandas=True, fail_silently=False)](#describe_tableself-table-fetch_through_pandastrue-fail_silentlyfalse)
- [MySQLTool](#mysqltool)
  - [\_\_init\_\_(self, connection="default", \*, credentials=None)](#__init__self-connectiondefault--credentialsnone)
  - [describe_table(self, table, fetch_through_pandas=True, fail_silently=False)](#describe_tableself-table-fetch_through_pandastrue-fail_silentlyfalse-1)
- [PostgreSQLTool](#postgresqltool)
  - [\_\_init\_\_(self, connection="default", \*, credentials=None)](#__init__self-connectiondefault--credentialsnone-1)
  - [describe_table(self, table, schema="public", fetch_through_pandas=True, fail_silently=False)](#describe_tableself-table-schemapublic-fetch_through_pandastrue-fail_silentlyfalse)
  - [get_all_db_info(self, get_json_info=True, fetch_through_pandas=True, fail_silently=False)](#get_all_db_infoself-get_json_infotrue-fetch_through_pandastrue-fail_silentlyfalse)
- [quote_identifier(name, quote='"')](#quote_identifiername-quote)
- [parse_database_url(url)](#parse_database_urlurl)

# Module Contents
## SQLTool
This class is a base class for the different types of SQL databases. Other classes in this module ([SQLiteTool](#sqlitetool), [MySQLTool](#mysqltool) and [PostgreSQLTool](#postgresqltool)) build upon these attributes and methods.

This class implements the with statement, so there are 2 ways of using it.

**1st way:**

```python
from instackup.sql_tools import SQLTool

with SQLTool("SQLite") as db:
    # use db object to interact with a database
    df = db.query("SELECT 1 AS one")
```

When leaving the with block, the transaction is committed (or rolled back, if an exception was raised) and the connection is closed.

**2nd way:**

```python
from instackup.sql_tools import SQLTool

db = SQLTool("SQLite")
db.connect()

try:
    # use db object to interact with a database
    df = db.query("SELECT 1 AS one")
except Exception as e:
    db.rollback()
    raise e
else:
    db.commit()
finally:
    db.close_connection()
```

Easy to see that it is recommended (and easier) to use the first syntax.

Using a tool before connecting (e.g. calling query or commit) raises a `RuntimeError`.

### \_\_init\_\_(self, sql_type, filename=None, connection="default", \*, credentials=None)
Initialization takes the _sql_type_ parameter, which sets the kind of database it's going to access ("SQLite", "PostgreSQL" or "MySQL"), the _filename_ parameter, which is only used if the sql_type is "SQLite" (defaults to an in-memory database), and the _connection_ parameter, which selects which connection of the credential store to use.

The keyword-only _credentials_ parameter takes the connection settings directly (a dictionary), instead of reading them from the credential store. Raises a `KeyError` (`CredentialsNotFoundError`) if no settings are found for the connection.

It has no return value.

The \_\_init\_\_ method doesn't actually open the connection, but sets all values required by the connect method.

Usage example:
```python
from instackup.sql_tools import SQLTool

db = SQLTool("SQLite")

# or

db = SQLTool("PostgreSQL", connection="analytics")

# or

db = SQLTool("PostgreSQL", credentials={"url": "postgresql://etl:secret@localhost:5432/warehouse"})
```

### connect(self, fail_silently=False)
Creates the connection using the \_\_init\_\_ attributes and returns its own object, so it can be used in a with statement.

If _fail_silently_ parameter is set to True, database errors will be logged instead of raised, so they don't stop the code execution; in that case, None is returned.

Usage example:
```python
from instackup.sql_tools import SQLTool

db = SQLTool("SQLite")
db.connect()
# remember to close the connection later

# or

with SQLTool("PostgreSQL") as db:
    # Already connected, use db object in this context
    df = db.query("SELECT 1 AS one")
```

### commit(self)
Commits any pending transaction to the database. It has no extra parameter or return value.

Usage example:
```python
from instackup.sql_tools import SQLTool

db = SQLTool("PostgreSQL")
db.connect()
# Do stuff
db.commit()
# remember to close the connection later

# or

with SQLTool("SQLite") as db:
    # Already connected, use db object in this context

    # Do stuff

    # No need to explicitly commit as it will do when leaving this context, but nonetheless:
    db.commit()
```

### rollback(self)
Rolls back to the start of any pending transaction. It has no extra parameter or return value.

Usage example:
```python
from instackup.sql_tools import SQLTool

db = SQLTool("SQLite")
db.connect()

try:
    # Do stuff
    db.execute_sql("CREATE TABLE test (id integer)")
except Exception as e:
    db.rollback()
    raise e
else:
    db.commit()
finally:
    # remember to close the connection later
    db.close_connection()

# or

with SQLTool("PostgreSQL") as db:
    # Already connected, use db object in this context

    # Do stuff

    # No need to explicitly commit or rollback as it will do when leaving this context, but nonetheless:
    if meet_condition:
        db.commit()
    else:
        db.rollback()
```

### close_connection(self)
Closes the connection with the database. It has no extra parameter or return value.

Usage example:
```python
from instackup.sql_tools import SQLTool

db = SQLTool("PostgreSQL")
db.connect()

try:
    # Do stuff
    db.execute_sql("CREATE TABLE test (id integer)")
except Exception as e:
    db.rollback()
    raise e
else:
    db.commit()
finally:
    db.close_connection()

# or

with SQLTool("SQLite") as db:
    # Already connected, use db object in this context

    # Do stuff
    db.execute_sql("CREATE TABLE test (id integer)")

    # Will close the connection automatically when exiting this scope
```

### execute_sql(self, command, fail_silently=False, \*, params=None)
Executes a SQL _command_ (CREATE, UPDATE, DROP...). It has no return value.

If _fail_silently_ parameter is set to True, database errors will be logged instead of raised, so they don't stop the code execution.

The keyword-only _params_ parameter (a sequence or a mapping) has values that are bound by the database driver, so they don't need to be quoted or escaped in the command. Use the driver's placeholder style: `?` for SQLite and `%s` for PostgreSQL and MySQL.

Usage example:
```python
from instackup.sql_tools import SQLTool


sql_cmd = """CREATE TABLE test (
    id          integer NOT NULL CONSTRAINT firstkey PRIMARY KEY,
    username    varchar(40) UNIQUE NOT NULL,
    fullname    varchar(64) NOT NULL,
    created_at  TIMESTAMP NOT NULL,
    last_login  TIMESTAMP
);
"""


db = SQLTool("PostgreSQL")
db.connect()

try:
    # Execute the command
    db.execute_sql(sql_cmd)

    # Execute a command with parameters
    db.execute_sql(
        "INSERT INTO test (id, username, fullname, created_at) VALUES (%s, %s, %s, NOW())",
        params=(1, "jdoe", "John Doe"),
    )

except Exception as e:
    db.rollback()
    raise e
else:
    db.commit()
finally:
    # remember to close the connection later
    db.close_connection()

# or

with SQLTool("PostgreSQL") as db:
    # Already connected, use db object in this context

    # This command would throw an error (since the table already was created before),
    # but since fail_silently parameter is set to True, it'll log the exception
    # and let the code continue past this point.
    db.execute_sql(sql_cmd, fail_silently=True)

    # other code
```

### query(self, sql_query, fetch_through_pandas=True, fail_silently=False, \*, params=None)
Runs a query and returns the results.

If _fetch_through_pandas_ parameter is True, the results are returned as a Pandas DataFrame; otherwise, as a list of tuples, one per row, with values in the order of the SELECT columns.

If _fail_silently_ parameter is set to True, database errors will be logged instead of raised, so they don't stop the code execution; in that case, None is returned.

The keyword-only _params_ parameter works as in [execute_sql](#execute_sqlself-command-fail_silentlyfalse--paramsnone).

For PostgreSQL (and Redshift), backticks (BigQuery/MySQL style table quotes) are removed from the query, since they aren't supported by these databases.

Usage example:
```python
from instackup.sql_tools import SQLTool


sql_query = """SELECT * FROM users LIMIT 100"""


db = SQLTool("PostgreSQL")
db.connect()

try:
    # Returns a list of tuples containing the rows of the response
    table = db.query(sql_query, fetch_through_pandas=False, fail_silently=True)

    # Do something with table variable

except Exception as e:
    db.rollback()
    raise e
else:
    db.commit()
finally:
    # remember to close the connection later
    db.close_connection()

# or

with SQLTool("SQLite", filename="db.sqlite3") as db:
    # Already connected, use db object in this context

    # Returns a Pandas DataFrame
    df = db.query(sql_query)

    # Query with parameters (SQLite uses "?" placeholders)
    df = db.query("SELECT * FROM users WHERE id = ?", params=(1,))

    # other code
```

## SQLiteTool
This class handles most of the interaction needed with SQLite3 databases, so the base code becomes more readable and straightforward. This class inherits from [SQLTool](#sqltool), so its attributes and methods can (and will) be accessed from this class. Read the documentation of the base class for more info.

This class implements the with statement, so there are 2 ways of using it.

**1st way:**

```python
from instackup.sql_tools import SQLiteTool

with SQLiteTool() as sl:
    # use sl object to interact with SQLite database
    df = sl.query("SELECT 1 AS one")
```

**2nd way:**

```python
from instackup.sql_tools import SQLiteTool

sl = SQLiteTool()
sl.connect()

try:
    # use sl object to interact with SQLite database
    df = sl.query("SELECT 1 AS one")
except Exception as e:
    sl.rollback()
    raise e
else:
    sl.commit()
finally:
    sl.close_connection()
```

Easy to see that it is recommended (and easier) to use the first syntax.

### \_\_init\_\_(self, filename=None)
Initialization takes the _filename_ parameter, which selects which SQLite3 database file to use; if it's not set, creates a temporary in-memory database. It has no return value.

The \_\_init\_\_ method doesn't actually open the connection, but sets all values required by the connect method.

Usage example:
```python
from instackup.sql_tools import SQLiteTool

sl = SQLiteTool(filename="db.sqlite3")
```

### describe_table(self, table, fetch_through_pandas=True, fail_silently=False)
Special query that returns the column metadata of a specific _table_, from `PRAGMA table_info`: one row per column, with the cid, name, type, notnull, dflt_value and pk fields.

_fetch_through_pandas_ and _fail_silently_ parameters work as in the [query](#queryself-sql_query-fetch_through_pandastrue-fail_silentlyfalse--paramsnone) method.

Usage example:
```python
from instackup.sql_tools import SQLiteTool


sl = SQLiteTool()  # In-memory sqlite database
sl.connect()

try:
    sl.execute_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")

    # Returns a list of tuples containing the rows of the response
    table = sl.describe_table("users", fetch_through_pandas=False, fail_silently=True)

    # Do something with table variable

except Exception as e:
    sl.rollback()
    raise e
else:
    sl.commit()
finally:
    # remember to close the connection later
    sl.close_connection()

# or

with SQLiteTool(filename="db.sqlite3") as sl:
    # Already connected, use sl object in this context

    # Returns a Pandas DataFrame with the columns info of that specific table
    df = sl.describe_table("airflow_logs")

    # other code
```

## MySQLTool
This class handles most of the interaction needed with MySQL databases, so the base code becomes more readable and straightforward. This class inherits from [SQLTool](#sqltool), so its attributes and methods can (and will) be accessed from this class. Read the documentation of the base class for more info.

It needs the `mysql` extra: `pip install 'instackup[mysql]'`.

This class implements the with statement, so there are 2 ways of using it.

**1st way:**

```python
from instackup.sql_tools import MySQLTool

with MySQLTool() as my:
    # use my object to interact with MySQL database
    df = my.query("SELECT 1 AS one")
```

**2nd way:**

```python
from instackup.sql_tools import MySQLTool

my = MySQLTool()
my.connect()

try:
    # use my object to interact with MySQL database
    df = my.query("SELECT 1 AS one")
except Exception as e:
    my.rollback()
    raise e
else:
    my.commit()
finally:
    my.close_connection()
```

Easy to see that it is recommended (and easier) to use the first syntax.

### \_\_init\_\_(self, connection="default", \*, credentials=None)
Initialization takes the _connection_ parameter, which selects which connection of the `mysql` service in the credential store to use. The keyword-only _credentials_ parameter takes the connection settings directly instead. It has no return value.

The settings are passed to `mysql.connector.connect`. A `dbname` setting is passed as `database`, and a `url` setting (`mysql://user:pass@host:3306/db`) is split into host, port, user, password and database.

The \_\_init\_\_ method doesn't actually open the connection, but sets all values required by the connect method.

Usage example:
```python
from instackup.sql_tools import MySQLTool

my = MySQLTool(connection="default")

# or

my = MySQLTool(credentials={"host": "localhost", "user": "root", "password": "secret", "dbname": "mydb"})
```

### describe_table(self, table, fetch_through_pandas=True, fail_silently=False)
Returns the column metadata of a specific table (`DESCRIBE` statement). _table_ can be either `table` or `schema.table`.

_fetch_through_pandas_ and _fail_silently_ parameters work as in the [query](#queryself-sql_query-fetch_through_pandastrue-fail_silentlyfalse--paramsnone) method.

Usage example:
```python
from instackup.sql_tools import MySQLTool


my = MySQLTool()
my.connect()

try:
    # Returns a list of tuples containing the rows of the response
    table = my.describe_table("users", fetch_through_pandas=False, fail_silently=True)

    # Do something with table variable

except Exception as e:
    my.rollback()
    raise e
else:
    my.commit()
finally:
    # remember to close the connection later
    my.close_connection()

# or

with MySQLTool() as my:
    # Already connected, use my object in this context

    # Returns a Pandas DataFrame with the columns info of that specific schema.table
    df = my.describe_table("another_schema.airflow_logs")

    # other code
```

## PostgreSQLTool
This class handles most of the interaction needed with PostgreSQL databases, so the base code becomes more readable and straightforward. This class inherits from [SQLTool](#sqltool), so its attributes and methods can (and will) be accessed from this class. Read the documentation of the base class for more info.

It needs the `postgresql` extra: `pip install 'instackup[postgresql]'`.

This class implements the with statement, so there are 2 ways of using it.

**1st way:**

```python
from instackup.sql_tools import PostgreSQLTool

with PostgreSQLTool() as pg:
    # use pg object to interact with PostgreSQL database
    df = pg.query("SELECT 1 AS one")
```

**2nd way:**

```python
from instackup.sql_tools import PostgreSQLTool

pg = PostgreSQLTool()
pg.connect()

try:
    # use pg object to interact with PostgreSQL database
    df = pg.query("SELECT 1 AS one")
except Exception as e:
    pg.rollback()
    raise e
else:
    pg.commit()
finally:
    pg.close_connection()
```

Easy to see that it is recommended (and easier) to use the first syntax.

### \_\_init\_\_(self, connection="default", \*, credentials=None)
Initialization takes the _connection_ parameter, which selects which connection of the `postgresql` service in the credential store to use. The keyword-only _credentials_ parameter takes the connection settings directly instead. It has no return value.

The settings are passed to `psycopg2.connect` (libpq keywords such as dbname, user, password, host and port), and may include a `url` (or `dsn`), e.g. `postgresql://user:pass@host:5432/db`.

The \_\_init\_\_ method doesn't actually open the connection, but sets all values required by the connect method.

Usage example:
```python
import os
from instackup.sql_tools import PostgreSQLTool

pg = PostgreSQLTool(connection="default")

# or

pg = PostgreSQLTool(credentials={"url": os.environ["DATABASE_URL"]})
```

### describe_table(self, table, schema="public", fetch_through_pandas=True, fail_silently=False)
Special query that returns all INFORMATION_SCHEMA.COLUMNS metadata of a specific _table_ in the given _schema_.

_fetch_through_pandas_ and _fail_silently_ parameters work as in the [query](#queryself-sql_query-fetch_through_pandastrue-fail_silentlyfalse--paramsnone) method.

Usage example:
```python
from instackup.sql_tools import PostgreSQLTool


pg = PostgreSQLTool()
pg.connect()

try:
    # Returns a list of tuples containing the rows of the response (Table: public.users)
    table = pg.describe_table("users", fetch_through_pandas=False, fail_silently=True)

    # Do something with table variable

except Exception as e:
    pg.rollback()
    raise e
else:
    pg.commit()
finally:
    # remember to close the connection later
    pg.close_connection()

# or

with PostgreSQLTool() as pg:
    # Already connected, use pg object in this context

    # Returns a Pandas DataFrame with all schema info of that specific schema.table
    df = pg.describe_table("airflow_logs", schema="another_schema")

    # other code
```

### get_all_db_info(self, get_json_info=True, fetch_through_pandas=True, fail_silently=False)
Gets all database columns info, using an INFORMATION_SCHEMA.COLUMNS query.

Ignores the pg_stat_statements table and tables inside the pg_catalog and information_schema schemas.

If _get_json_info_ parameter is True, it adds the json_key and json_value_type columns, with one extra row for each key found in each json and jsonb column. Only JSON object values are expanded; other values (arrays, strings, numbers...) are skipped.

_fetch_through_pandas_ and _fail_silently_ parameters are passed directly to the _query_ method if _get_json_info_ parameter is set to False; if it's not, a DataFrame is always returned and errors are always raised.

Returns a DataFrame if either _get_json_info_ or _fetch_through_pandas_ parameters are set to True; otherwise returns a list of tuples, each representing a row, with their position in the same order as in the columns of the INFORMATION_SCHEMA.COLUMNS table.

Usage example:
```python
from instackup.sql_tools import PostgreSQLTool


pg = PostgreSQLTool()
pg.connect()

try:
    # Returns a list of tuples containing the rows of the response
    schema_info = pg.get_all_db_info(get_json_info=False, fetch_through_pandas=False, fail_silently=True)

    # Do something with schema_info variable

except Exception as e:
    pg.rollback()
    raise e
else:
    pg.commit()
finally:
    # remember to close the connection later
    pg.close_connection()

# or

with PostgreSQLTool() as pg:
    # Already connected, use pg object in this context

    # Returns a Pandas DataFrame with all schema info, including the keys inside JSON and JSONB fields
    df = pg.get_all_db_info()

    # other code
```

## quote_identifier(name, quote='"')
Quotes a SQL identifier (table, column...) with the _quote_ character, escaping any quote character inside it. Use ``quote="`"`` for MySQL.

Usage example:
```python
from instackup.sql_tools import quote_identifier

print(quote_identifier("my table"))           # output: >>> "my table"
print(quote_identifier("my table", quote="`"))  # output: >>> `my table`
```

## parse_database_url(url)
Splits a `scheme://user:password@host:port/database` URL into a dictionary of connection keyword arguments (host, port, user, password and database). User and password are URL-decoded and missing parts are left out.

Usage example:
```python
from instackup.sql_tools import parse_database_url

print(parse_database_url("mysql://etl:p%40ss@db.internal:3306/sales"))
# output: >>> {'host': 'db.internal', 'port': 3306, 'user': 'etl', 'password': 'p@ss', 'database': 'sales'}
```
