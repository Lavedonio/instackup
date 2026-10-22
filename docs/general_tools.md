# general_tools
This is the documentation for the general_tools module and all its contents, with usage examples.

This module needs no extra dependencies: a plain `pip install instackup` is enough.

# Index
- [fetch_credentials(service_name, \*args, \*\*kwargs)](#fetch_credentialsservice_name-args-kwargs)
- [code_location()](#code_location)
- [unicode_to_ascii(unicode_string)](#unicode_to_asciiunicode_string)
- [parse_remote_uri(uri, service)](#parse_remote_uriuri-service)

# Module Contents
## fetch_credentials(service_name, \*args, \*\*kwargs)
**Deprecated:** calling it emits a `DeprecationWarning`. Use `instackup.credentials.get_credentials(service, connection)` for a connection's settings, or `get_default_store().get_value(...)` for custom sections. Both also read environment variables and secret managers (see [credentials.md](credentials.md)).

Reads the secrets file set in the `CREDENTIALS_HOME` (or `INSTACKUP_CREDENTIALS_FILE`) environment variable and returns the section selected by the _service_name_ parameter. Extra positional and keyword arguments walk further down the structure, in the order given. If the service is "credentials_path", the path of the directory where the secrets file is located is returned instead.

Keys are case-sensitive, matching the file exactly. Raises a `KeyError` if neither environment variable is set.

Usage example:
```python
from instackup.credentials import get_credentials, get_default_store
from instackup.general_tools import fetch_credentials

# Recommended: settings of one connection of a service
postgresql_settings = get_credentials("postgresql", "default")

# Recommended: a custom section of the credentials
sftp_settings = get_default_store().get_value("SalesforceSFTP")

# Deprecated equivalents
print(fetch_credentials("PostgreSQL", "default"))
print(fetch_credentials("RedShift", "default", connection_type="cluster_credentials"))
print(fetch_credentials("SalesforceSFTP"))

# Getting the path of the directory where the secrets file is
print(fetch_credentials("credentials_path"))
```

## code_location()
Gets where the code is running. It can be "local", "production" or whatever fits the description of where the execution takes place.

The value is read from the `INSTACKUP_LOCATION` environment variable or the `Location` key of the credentials file (see [credentials.md](credentials.md)). Returns None if it isn't set.

Usage example:
```python
from instackup.general_tools import code_location

if code_location() == "local":
    debug = True  # set vars for when the code is executed locally
else:
    debug = False  # set vars for when the code is executed remotely
```

## unicode_to_ascii(unicode_string)
Replaces all non-ASCII chars in a string by the closest possible match.

This solution was inspired by this answer:
https://stackoverflow.com/a/517974/11981524

Usage example:
```python
from instackup.general_tools import unicode_to_ascii


raw_data = "ÑÇÀÁÂÃÈÉÊÍÒÓÔÙÚ ñçàáâãèéêíòóôùú"
ascii_data = unicode_to_ascii(raw_data)

print(ascii_data)  # output: >>> NCAAAAEEEIOOOUU ncaaaaeeeiooouu
```

## parse_remote_uri(uri, service)
Parses a Google Cloud Storage ("gs") or an Amazon S3 ("s3") URI into bucket and subfolder(s), returned as a tuple.

_service_ parameter can be either "gs" or "s3".

The subfolder, when present, always ends with a slash (`/`); it's an empty string if the URI has only the bucket.

Raises a `ValueError` if the URI isn't in the `<service>://<bucket>[/<subfolder>]` format.

Usage example:
```python
from instackup.general_tools import parse_remote_uri


### S3
s3_path = "s3://some_bucket/subfolder"
bucket_name, subfolder = parse_remote_uri(s3_path, "s3")

print(f"Bucket name: {bucket_name}")  # output: >>> Bucket name: some_bucket
print(f"Subfolder: {subfolder}")      # output: >>> Subfolder: subfolder/


### Storage
gs_path = "gs://some_bucket/"
bucket_name, subfolder = parse_remote_uri(gs_path, "gs")

print(f"Bucket name: {bucket_name}")  # output: >>> Bucket name: some_bucket
print(f"Subfolder: {subfolder}")      # output: >>> Subfolder:
```
