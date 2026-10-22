# Architecture

This document records the design decisions behind the 0.4.0 modernization and proposes further changes. For usage, see the [README](../README.md) and [credentials guide](credentials.md).

# Index
- [Goals](#goals)
- [Package layout](#package-layout)
- [Credentials](#credentials)
- [Dependencies](#dependencies)
- [Logging and side effects](#logging-and-side-effects)
- [Testing](#testing)
- [Release pipeline](#release-pipeline)
- [Proposed next steps](#proposed-next-steps)

# Goals

1. Run the same code locally and in production, **without plaintext credential files** in production.
2. Keep existing scripts working: same module, class and method names; new options are keyword-only.
3. Install only what you use, and work with the current Python and library releases.

# Package layout

```text
src/instackup/
├── __init__.py            # __version__ and lazy access to the tool classes
├── credentials.py         # Credential sources and the credential store (public)
├── general_tools.py       # Helpers + deprecated fetch_credentials
├── _google.py, _aws.py    # Shared authentication for the cloud tools (private)
├── _utils.py              # Small shared helpers (private)
├── bigquery_tools.py      # One module per integration, as before
├── gcloudstorage_tools.py
├── gsheets_tools.py
├── heroku_tools.py
├── redshift_tools.py
├── s3_tools.py
└── sql_tools.py
```

- **`src/` layout**: tests run against the installed package, not the source folder, which catches packaging mistakes.
- **Typed** (`py.typed`): every function has type hints, checked with mypy in CI.
- **Lazy imports**: `import instackup` doesn't import any cloud SDK; `from instackup import BigQueryTool` imports only that module. Database drivers are imported when a connection opens.

# Credentials

**Before:** every tool called `fetch_credentials()`, which read one YAML/JSON file from the path in `CREDENTIALS_HOME`. Google tools then set the process-wide `GOOGLE_APPLICATION_CREDENTIALS` variable, only if it wasn't set yet. That meant:

- production needed long-lived keys and passwords in a file on disk;
- there was no way to use a cloud platform's own identity (IAM roles, Workload Identity);
- a second Google connection silently reused the first one's service account;
- one missing section (e.g. no `AWS` block) broke tools that didn't need it.

**Now:** a `CredentialStore` merges several *sources* (environment variables, AWS Secrets Manager, GCP Secret Manager, a file), highest priority first. Tools ask the store for one `service`/`connection` and receive a plain dict.

```text
                 ┌───────────────────────┐
 env vars ──────►│                       │──► get("postgresql", "default") ──► PostgreSQLTool
 AWS SM ────────►│    CredentialStore    │
 GCP SM ────────►│ (lazy, merged, cached)│
 file + ${ENV} ─►│                       │──► get("google", "default") ──► None ──► ADC
                 └───────────────────────┘
```

Design choices:

- **Ambient identity first.** If the `default` connection of a cloud service isn't configured, tools use Google Application Default Credentials or the AWS default chain. Named connections must exist, so typos fail loudly.
- **Explicit beats implicit.** Every tool accepts `credentials=` (settings dict) and, for cloud tools, a ready SDK object (`client=`, `session=`, `gspread_client=`). This is also how tests inject fakes.
- **Files without secrets.** `${VAR}` / `${VAR:-default}` references let a committed file describe connections while secrets come from the environment. References are expanded only when used.
- **Pluggable.** A source is any object with `load() -> dict`. Adding Vault or Azure Key Vault is one small class.
- **Backwards compatible.** `CREDENTIALS_HOME`, the old file format and capitalized service names still work; `fetch_credentials` is deprecated, not removed.

# Dependencies

| Change | Why |
|---|---|
| Python ≥ 3.11 | 3.10 reaches end of life in October 2026; pandas 3 needs 3.11. CI covers 3.11–3.15. |
| Optional extras (`aws`, `gcp`, `gsheets`, `postgresql`, `mysql`, `redshift`, `all`) | The base install was ~100 packages, including every cloud SDK. Now only `pandas` and `PyYAML` are required. |
| Lower bounds instead of pins | `grpcio==1.34.0`, `gspread==3.6.0`, `gcsfs==0.7.1` and `psycopg2-binary==2.8.6` made the package impossible to install next to anything modern. CI also tests the lowest allowed versions. |
| Dropped `gcsfs`, `oauth2client` | `gcsfs` was only used implicitly by `pd.read_csv("gs://...")`; files are now read through the authenticated client. `oauth2client` has been deprecated since 2017; google-auth replaces it. |
| `pandas_gbq.to_gbq` instead of `DataFrame.to_gbq` | Removed in pandas 3. |
| BigQuery Data Transfer v3 API | `project_path()` and the positional request style were removed. |

# Logging and side effects

The library used to create a `logs/` folder next to the installed package and attach file handlers at import time. That fails on read-only filesystems (containers, Lambda), writes inside `site-packages`, and takes logging configuration away from the application. Now every module uses `logging.getLogger(__name__)`, the package adds only a `NullHandler`, and `print` calls became log records. Configure logging in your application, e.g. `logging.basicConfig(level=logging.INFO)`.

# Testing

- **Unit tests** cover every module with fakes injected through the constructors; S3, Secrets Manager and Redshift use [moto](https://github.com/getmoto/moto). No test touches a real cloud.
- **Integration tests** (`tests/integration`, marker `integration`) run against real PostgreSQL and MySQL. CI starts them as service containers; locally they're skipped unless `TEST_POSTGRESQL_URL` / `TEST_MYSQL_URL` are set.
- An autouse fixture strips credential environment variables so tests never pick up a developer's real credentials.

# Release pipeline

`.github/workflows/ci.yml` runs on every push and pull request: ruff (lint + format), mypy, tests on Python 3.11–3.15 (plus macOS and Windows), a lowest-dependencies run, integration tests and a build check.

`.github/workflows/release.yml` runs when a GitHub release is published. It reruns CI, builds the sdist and wheel with the version taken from the git tag (hatch-vcs, so there's no version to bump by hand), checks that tag and version match, publishes to PyPI with Trusted Publishing (OIDC, no stored token, with attestations), and attaches the files to the release. It can also be started manually to publish a dev build to TestPyPI. Setup steps are in [releasing.md](releasing.md).

# Proposed next steps

Not implemented, roughly in priority order:

1. **Release as 1.0.0** once 0.4.0 has been used for a while. Python ≥ 3.11, optional extras and the credentials changes are breaking enough that a major version communicates them better than a minor one.
2. **SQLAlchemy engine for the SQL tools.** One code path for PostgreSQL, MySQL, Redshift (via `sqlalchemy-redshift`) and SQLite, connection pooling, `pandas.read_sql`/`to_sql` without warnings, and a natural place for `url` settings. It would replace the hand-written driver dispatch in `sql_tools`.
3. **psycopg 3** instead of psycopg2 once Redshift support is confirmed (psycopg2 is in maintenance mode).
4. **Generated API docs** (MkDocs + mkdocstrings) from the docstrings, published to GitHub Pages, replacing the hand-maintained `docs/*_tools.md`.
5. **Split stateful "cursor" APIs.** `S3Tool`/`GCloudStorageTool` keep a current bucket/subfolder/file, so most methods depend on earlier calls. Methods that take an explicit `uri` would be easier to reason about and to use concurrently.
6. **Drop `heroku_tools`** unless it's still used. It's a thin wrapper over the Heroku CLI, and Heroku has no free tier anymore.
7. **More credential sources** as needed: HashiCorp Vault, Azure Key Vault, 1Password Connect.
