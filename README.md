# Instackup

[![PyPI](https://img.shields.io/pypi/v/instackup)](https://pypi.org/project/instackup/)
[![Python versions](https://img.shields.io/pypi/pyversions/instackup)](https://pypi.org/project/instackup/)
[![CI](https://github.com/Lavedonio/instackup/actions/workflows/ci.yml/badge.svg)](https://github.com/Lavedonio/instackup/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/Lavedonio/instackup/blob/main/LICENSE)

This Python library is an open source way to standardize and simplify connections with cloud-based tools, databases and commonly used tools in data manipulation and analysis. It can help BI teams by having a unified source code for local development and testing as well as remote production (automated scheduled run) environments.

# Index

- [Current release](#current-release)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Credentials](#credentials)
- [Documentation](#documentation)
- [Development](#development)
- [Version logs](#version-logs)

# Current release
**Version 0.4.0 (beta)**: a modernization release with support for Python 3.11–3.15, current versions of every dependency, production-ready credentials (environment variables, secret managers and cloud platform identities), type hints and a full test suite. See [what changed](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.4.0-beta-current_release.md#version-040-beta), including the breaking changes.

# Installation
Instackup needs [Python 3.11 or newer](https://www.python.org/downloads/). Install it with the extras for the services you use:

    pip install 'instackup[gcp,postgresql]'

| Extra | Modules |
|---|---|
| `gcp` | `bigquery_tools`, `gcloudstorage_tools` (and GCP Secret Manager credentials) |
| `gsheets` | `gsheets_tools` |
| `aws` | `s3_tools` (and AWS Secrets Manager credentials) |
| `redshift` | `redshift_tools` |
| `postgresql` | `sql_tools.PostgreSQLTool` |
| `mysql` | `sql_tools.MySQLTool` |
| `all` | Everything above |

`sql_tools.SQLiteTool`, `general_tools` and `heroku_tools` work without extras.

# Quick start

```python
from instackup import BigQueryTool, PostgreSQLTool, S3Tool

# Databases: credentials come from environment variables, a secret manager or a credentials file
with PostgreSQLTool() as pg:
    orders = pg.query("SELECT * FROM orders WHERE created_at >= %s", params=("2026-01-01",))

# Cloud services: with nothing configured, the platform's own identity is used
bq = BigQueryTool()
bq.upload(orders, dataset="analytics", table="orders", if_exists="replace")

s3 = S3Tool(uri="s3://my-bucket/exports/")
s3.upload_file("report.csv")
```

The library logs through Python's standard `logging` module. To see what it's doing:

```python
import logging

logging.basicConfig(level=logging.INFO)
```

# Credentials
Tools look up credentials by service and connection name (`connection="default"` unless you pass another one), in this order:

1. `INSTACKUP_<SERVICE>__<CONNECTION>__<KEY>` environment variables, e.g. `INSTACKUP_POSTGRESQL__DEFAULT__PASSWORD`;
2. a credentials document stored in AWS Secrets Manager (`INSTACKUP_AWS_SECRET_ID`) or GCP Secret Manager (`INSTACKUP_GCP_SECRET_NAME`);
3. a YAML or JSON file set in `INSTACKUP_CREDENTIALS_FILE` (or the legacy `CREDENTIALS_HOME`), whose values can reference environment variables as `${NAME}`.

When Google or AWS credentials aren't configured, the tools use [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials) and the [AWS default credential chain](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html), the recommended setup in production (service accounts, Workload Identity, IAM roles).

A minimal local setup:

```yaml
# credentials.yml (use credentials/secret_template.yml as a starting point)
PostgreSQL:
  default:
    host: localhost
    dbname: postgres
    user: postgres
    password: ${POSTGRES_PASSWORD}
```

```bash
export INSTACKUP_CREDENTIALS_FILE="$HOME/.config/instackup/credentials.yml"
export POSTGRES_PASSWORD=...
gcloud auth application-default login  # For Google tools
aws sso login                          # For AWS tools
```

Read the [credentials guide](https://github.com/Lavedonio/instackup/blob/main/docs/credentials.md) for every option, production recommendations and how to migrate from `CREDENTIALS_HOME`.

# Documentation

- [Credentials guide](https://github.com/Lavedonio/instackup/blob/main/docs/credentials.md)
- [Architecture and design decisions](https://github.com/Lavedonio/instackup/blob/main/docs/architecture.md)
- Modules:
  - [bigquery_tools](https://github.com/Lavedonio/instackup/blob/main/docs/bigquery_tools.md#bigquery_tools): `BigQueryTool`, to query, load and manage BigQuery data, plus PostgreSQL to BigQuery schema conversion.
  - [gcloudstorage_tools](https://github.com/Lavedonio/instackup/blob/main/docs/gcloudstorage_tools.md#gcloudstorage_tools): `GCloudStorageTool`, to manage Google Cloud Storage files and folders.
  - [general_tools](https://github.com/Lavedonio/instackup/blob/main/docs/general_tools.md#general_tools): URI parsing, text normalization and the code location.
  - [gsheets_tools](https://github.com/Lavedonio/instackup/blob/main/docs/gsheets_tools.md#gsheets_tools): `GSheetsTool`, to read and write Google Sheets as DataFrames.
  - [heroku_tools](https://github.com/Lavedonio/instackup/blob/main/docs/heroku_tools.md#heroku_tools): `HerokuTool`, a Heroku CLI wrapper.
  - [redshift_tools](https://github.com/Lavedonio/instackup/blob/main/docs/redshift_tools.md#redshift_tools): `RedShiftTool`, for Redshift queries and UNLOAD to S3.
  - [s3_tools](https://github.com/Lavedonio/instackup/blob/main/docs/s3_tools.md#s3_tools): `S3Tool`, to manage S3 files and folders.
  - [sql_tools](https://github.com/Lavedonio/instackup/blob/main/docs/sql_tools.md#sql_tools): `SQLiteTool`, `PostgreSQLTool` and `MySQLTool`.

# Development
The project uses [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras          # Create .venv with every extra and the dev tools
uv run pytest                 # Unit tests
uv run ruff check             # Lint
uv run ruff format            # Format
uv run mypy                   # Type check
```

Integration tests run against real databases and are skipped unless their URLs are set:

```bash
docker run -d --rm -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:17-alpine
TEST_POSTGRESQL_URL=postgresql://postgres:postgres@localhost:5432/postgres uv run pytest -m integration
```

Every push and pull request runs the [CI workflow](https://github.com/Lavedonio/instackup/blob/main/.github/workflows/ci.yml). Publishing a GitHub release uploads the package to PyPI; see [releasing.md](https://github.com/Lavedonio/instackup/blob/main/docs/releasing.md).

# Version logs
See what changed in every version.

- Beta releases
  - [Version 0.4.0](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.4.0-beta-current_release.md#version-040-beta) (current release)
  - [Version 0.3.0](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.3.0-beta.md#version-030-beta)
  - [Version 0.2.6](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.2.6-beta.md#version-026-beta)
  - [Version 0.2.5](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.2.5-beta.md#version-025-beta)
  - [Version 0.2.4](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.2.4-beta.md#version-024-beta)
  - [Version 0.2.3](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.2.3-beta.md#version-023-beta)
  - [Version 0.2.2](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.2.2-beta.md#version-022-beta)
  - [Version 0.2.1](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.2.1-beta.md#version-021-beta)
  - [Version 0.2.0](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.2.0-beta.md#version-020-beta)
  - [Version 0.1.2](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.1.2-beta.md#version-012-beta)
  - [Version 0.1.1](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.1.1-beta.md#version-011-beta)
  - [Version 0.1.0](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.1.0-beta.md#version-010-beta)
- Alpha releases
  - [Version 0.0.6](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.0.6-alpha.md#version-006-alpha)
  - [Version 0.0.5](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.0.5-alpha.md#version-005-alpha)
  - [Version 0.0.4](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.0.4-alpha.md#version-004-alpha)
  - [Version 0.0.3](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.0.3-alpha.md#version-003-alpha)
  - [Version 0.0.2](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.0.2-alpha.md#version-002-alpha)
  - [Version 0.0.1](https://github.com/Lavedonio/instackup/blob/main/version_logs/v0.0.1-alpha.md#version-001-alpha)
