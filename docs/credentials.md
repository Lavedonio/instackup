# Credentials

Every instackup tool needs to know how to authenticate. Since version 0.4.0, credentials can come from several places, so the same code runs on a laptop and in production without a plaintext secrets file.

# Index
- [How credentials are resolved](#how-credentials-are-resolved)
- [Recommended setup for production](#recommended-setup-for-production)
- [Settings reference](#settings-reference)
- [Environment variables](#environment-variables)
- [Credentials file](#credentials-file)
- [Secret managers](#secret-managers)
- [Passing credentials in code](#passing-credentials-in-code)
- [Migrating from CREDENTIALS_HOME](#migrating-from-credentials_home)

# How credentials are resolved

Credentials are organized as **service → connection → settings**:

```yaml
postgresql:          # service
  default:           # connection name
    host: db.internal
    user: etl
    password: ...
  analytics:         # another connection of the same service
    url: postgresql://reader@analytics.internal:5432/warehouse
```

Tools pick a connection with their `connection` parameter, which defaults to `"default"` (e.g. `PostgreSQLTool(connection="analytics")`). Service and connection names are case-insensitive, so the old `PostgreSQL`/`RedShift` spelling still works.

Settings are looked up in these sources, **first match wins**, and they're merged key by key (a file can hold the host and user while an environment variable provides the password):

1. `INSTACKUP_<SERVICE>__<CONNECTION>__<KEY>` [environment variables](#environment-variables);
2. an AWS Secrets Manager secret named by `INSTACKUP_AWS_SECRET_ID` ([secret managers](#secret-managers));
3. a GCP Secret Manager secret named by `INSTACKUP_GCP_SECRET_NAME`;
4. a YAML or JSON [credentials file](#credentials-file) named by `INSTACKUP_CREDENTIALS_FILE` (or the legacy `CREDENTIALS_HOME`).

None of them is required. When the **cloud** tools (BigQuery, Cloud Storage, Google Sheets, S3, Redshift's AWS calls) find no settings for the `default` connection, they use the platform's own identity:

- **Google**: [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials): Workload Identity on GKE, the attached service account on Cloud Run, Cloud Functions, Composer and Compute Engine, or `gcloud auth application-default login` on your machine.
- **AWS**: the [default credential chain](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html): IAM roles for ECS tasks, Lambda, EC2 and EKS (IRSA / Pod Identity), `AWS_*` environment variables, or `~/.aws` profiles and SSO.

A missing *named* connection (anything other than `default`) is always an error, so a typo can't silently fall back to a different account. Database tools (PostgreSQL, MySQL, Redshift) always need their settings.

# Recommended setup for production

1. **Don't use keys for cloud services.** Give the workload an identity (service account, IAM role) and configure nothing for Google/AWS. There's no secret to leak or rotate.
2. **Keep database passwords in a secret manager**, injected as environment variables by your platform (Kubernetes secrets, ECS/Cloud Run secret references, GitHub Actions secrets...) or loaded with `INSTACKUP_AWS_SECRET_ID` / `INSTACKUP_GCP_SECRET_NAME`.
3. **For Redshift `UNLOAD`, set an `iam_role`** so AWS keys are never embedded in SQL.
4. Non-secret settings (hosts, project IDs, database names) can live in a committed credentials file that references secrets as `${ENV_VAR}`.

# Settings reference

| Service | Connection settings |
|---|---|
| `google` | `project_id`, `project_name`, `project_number`; a key as `service_account_info` (JSON string or mapping) or `service_account_file` (path; `secret_filename` also accepted). No key → Application Default Credentials. |
| `aws` | `access_key`, `secret_key` (or `aws_access_key_id`, `aws_secret_access_key`), `session_token`, `profile`, `region`. None → AWS default credential chain. |
| `redshift` | `cluster_credentials` (`dbname`, `user`, `host`, `cluster_id`, `port`) for temporary IAM-based passwords, and/or `master_password` (`dbname`, `user`, `host`, `password`, `port`); `iam_role` for `UNLOAD`. AWS credentials come from the `aws` connection of the same name. |
| `postgresql` | Any [libpq connection parameter](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-PARAMKEYWORDS) (`host`, `port`, `dbname`, `user`, `password`, `sslmode`...) and/or a `url` (`postgresql://user:pass@host:5432/db`). |
| `mysql` | `host`, `port`, `user`, `password`, `dbname` (or `database`), any other [connector argument](https://dev.mysql.com/doc/connector-python/en/connector-python-connectargs.html), and/or a `url` (`mysql://user:pass@host:3306/db`). |
| `location` | Top-level value returned by `general_tools.code_location()`, e.g. `local` or `production`. |

Relative key-file paths are resolved against the credentials file's directory.

# Environment variables

Any setting can be given as `INSTACKUP_<SERVICE>__<CONNECTION>__<KEY>`, with **double underscores** between the parts (single underscores belong to names like `project_id`). Nested settings add more parts.

```bash
export INSTACKUP_POSTGRESQL__DEFAULT__HOST=db.internal
export INSTACKUP_POSTGRESQL__DEFAULT__PASSWORD=s3cret
export INSTACKUP_POSTGRESQL__ANALYTICS__URL=postgresql://reader:pw@analytics:5432/warehouse
export INSTACKUP_REDSHIFT__DEFAULT__MASTER_PASSWORD__PASSWORD=s3cret
export INSTACKUP_GOOGLE__DEFAULT__PROJECT_ID=my-project
export INSTACKUP_LOCATION=production
```

Variable names are case-insensitive and values are always strings. This is the most portable option for containers and CI.

# Credentials file

Point `INSTACKUP_CREDENTIALS_FILE` to a YAML or JSON file (see [secret_template.yml](../credentials/secret_template.yml)). String values can reference environment variables, using shell syntax:

```yaml
Location: production

PostgreSQL:
  default:
    host: db.internal
    user: etl
    password: ${PG_PASSWORD}            # Required variable
    sslmode: ${PG_SSLMODE:-require}     # With a default (used when unset or empty)
```

References are expanded only when a connection is used. A value that references an unset variable (without a default) is treated as missing and a warning is logged, so a file can mention variables that only some environments set.

With every secret behind a `${...}` reference, the file holds no secrets and can be committed or baked into an image.

# Secret managers

A whole credentials document, the same YAML or JSON as the file, can be stored as one secret:

```bash
# AWS Secrets Manager (uses the AWS default credential chain)
export INSTACKUP_AWS_SECRET_ID=prod/instackup

# GCP Secret Manager (uses Application Default Credentials). "versions/latest" is assumed.
export INSTACKUP_GCP_SECRET_NAME=projects/my-project/secrets/instackup
```

The secret is read once, on first use. Grant the workload's identity read access to that secret only. The GCP option needs the `gcp` extra; the AWS one needs `aws`.

# Passing credentials in code

Every tool accepts explicit settings, which skip the lookup entirely:

```python
from instackup.sql_tools import PostgreSQLTool

with PostgreSQLTool(credentials={"url": get_my_database_url()}) as db:
    df = db.query("SELECT 1")
```

The cloud tools also accept a ready SDK object, for anything the settings don't cover (impersonation, custom endpoints, retries...):

```python
import boto3
from google.cloud import bigquery
from instackup.bigquery_tools import BigQueryTool
from instackup.s3_tools import S3Tool

bq = BigQueryTool(client=bigquery.Client(project="my-project", credentials=my_credentials))
s3 = S3Tool(bucket="my-bucket", session=boto3.Session(profile_name="analytics"))
```

`GCloudStorageTool` takes `client=`, `GSheetsTool` takes `gspread_client=` and `RedShiftTool` takes `session=`.

To build the lookup chain yourself, replace the process-wide store:

```python
from instackup.credentials import CredentialStore, EnvironmentSource, FileSource, set_default_store

set_default_store(CredentialStore([EnvironmentSource(), FileSource("/etc/instackup/credentials.yml")]))
```

`instackup.credentials.get_credentials("postgresql", "analytics")` returns the resolved settings of a connection, and `get_default_store().get_value("my_section")` returns any custom top-level section, for your own code.

# Migrating from CREDENTIALS_HOME

Existing setups keep working: `CREDENTIALS_HOME` is still read, the old file format is valid, and `secret_filename` paths are still resolved next to the file. To move toward a production-ready setup:

1. Rename the variable to `INSTACKUP_CREDENTIALS_FILE` (optional).
2. Replace secret values with `${ENV_VAR}` references, or move them to environment variables or a secret manager.
3. Delete the `Google` / `AWS` sections where the platform provides an identity.
4. Replace `fetch_credentials(...)` calls, now deprecated, with `instackup.credentials.get_credentials(...)` (or `get_default_store().get_value(...)` for custom sections).

Behavior changes to be aware of:

- Tools no longer set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable. Each tool gets its own credentials, so connections with different service accounts can be used side by side.
- Without an `AWS`/`Google` section, tools used to fail; now they use the platform identity.
- `code_location()` returns `None` instead of raising `KeyError` when no location is configured.
