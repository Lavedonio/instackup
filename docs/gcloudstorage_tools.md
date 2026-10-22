# gcloudstorage_tools
This is the documentation for the gcloudstorage_tools module and all its contents, with usage examples.

This module needs the `gcp` extra: `pip install 'instackup[gcp]'`.

Credentials come from environment variables, a credentials file or the cloud platform identity (see [credentials.md](credentials.md)).

# Index
- [GCloudStorageTool](#gcloudstoragetool)
  - [\_\_init\_\_(self, uri=None, bucket=None, subfolder="", filename=None, connection="default", authenticate=True, \*, credentials=None, client=None)](#__init__self-urinone-bucketnone-subfolder-filenamenone-connectiondefault-authenticatetrue--credentialsnone-clientnone)
  - [bucket(self) @property](#bucketself-property)
  - [blob(self) @property](#blobself-property)
  - [uri(self) @property](#uriself-property)
  - [set_bucket(self, bucket)](#set_bucketself-bucket)
  - [set_subfolder(self, subfolder)](#set_subfolderself-subfolder)
  - [select_file(self, filename)](#select_fileself-filename)
  - [list_all_buckets(self)](#list_all_bucketsself)
  - [get_bucket_info(self, bucket=None)](#get_bucket_infoself-bucketnone)
  - [get_file_info(self, filename=None, info=None)](#get_file_infoself-filenamenone-infonone)
  - [list_contents(self, yield_results=False)](#list_contentsself-yield_resultsfalse)
  - [rename_file(self, new_filename)](#rename_fileself-new_filename)
  - [rename_subfolder(self, new_subfolder)](#rename_subfolderself-new_subfolder)
  - [upload_file(self, filename, remote_path=None)](#upload_fileself-filename-remote_pathnone)
  - [upload_subfolder(self, folder_path)](#upload_subfolderself-folder_path)
  - [upload_from_dataframe(self, dataframe, file_format="CSV", filename=None, overwrite=False, \*\*kwargs)](#upload_from_dataframeself-dataframe-file_formatcsv-filenamenone-overwritefalse-kwargs)
  - [download_file(self, download_to=None, remote_filename=None, replace=False)](#download_fileself-download_tonone-remote_filenamenone-replacefalse)
  - [download_subfolder(self, download_to=None)](#download_subfolderself-download_tonone)
  - [download_on_dataframe(self, \*\*kwargs)](#download_on_dataframeself-kwargs)
  - [download_as_string(self, remote_filename=None, encoding="UTF-8")](#download_as_stringself-remote_filenamenone-encodingutf-8)
  - [delete_file(self)](#delete_fileself)
  - [delete_subfolder(self)](#delete_subfolderself)
- [split_gcs_uri(uri)](#split_gcs_uriuri)

# Module Contents
## GCloudStorageTool
This class handles most of the interaction needed with Google Cloud Storage, so the base code becomes more readable and straightforward.

### \_\_init\_\_(self, uri=None, bucket=None, subfolder="", filename=None, connection="default", authenticate=True, \*, credentials=None, client=None)
Takes either a _uri_ or a _bucket_ name (and, if necessary, also a _subfolder_ name and a _file name_) as parameters to set the current working directory. Raises a `ValueError` if both _uri_ and _bucket_ are given. It also creates the Google Cloud Storage client (the _client_ attribute).

When setting by the _uri_, it will consider that a filename was given if the path doesn't end with a slash, i.e. `/`. If it does, it will consider that the path only has bucket and subfolder arguments. In this implementation, a subfolder **always** ends with a slash (`/`), which is added if missing.

The paradigm of this class is that all the operations are done in the current working directory, so it is important to set the right path (you can reset it later, but still).

The client authenticates with the `google` service settings of the _connection_ parameter in the credential store (a service account key file or info, and the project). Without them, Application Default Credentials are used (e.g. Workload Identity, the Cloud Run/Compute Engine metadata server or `gcloud auth application-default login`). A named connection other than "default" must exist in the credential store. The `GOOGLE_APPLICATION_CREDENTIALS` environment variable is not changed.

The _authenticate_ parameter sets whether the credential store is used. If set to False, Application Default Credentials are used directly, which might be desired if the environment is already authenticated, for example in a Google Cloud Composer environment.

The keyword-only _credentials_ parameter takes the `google` settings directly (used even if _authenticate_ is False), and the keyword-only _client_ parameter takes a ready `google.cloud.storage.Client`.

The _project_ attribute is a dictionary with the "id", "name" and "number" of the project from the settings, or None if there are no settings (or a client was given).

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


# With a filename

gs = GCloudStorageTool(uri="gs://some_bucket/subfolder/example.txt")
# or
gs = GCloudStorageTool(bucket="some_bucket", subfolder="subfolder/", filename="example.txt")


# Without a filename

gs = GCloudStorageTool(uri="gs://some_other_bucket/some_subfolder/subpath/")
# or
gs = GCloudStorageTool(bucket="some_other_bucket", subfolder="some_subfolder/subpath/")


# Using Application Default Credentials directly
gs = GCloudStorageTool(uri="gs://some_bucket/subfolder/", authenticate=False)
```

### bucket(self) @property
Returns the bucket object from the client based on the _bucket_name_ attribute. It's a local reference, so getting it doesn't make an API call. Can be set directly or with the \_\_init\_\_ or set_bucket methods; setting it resets the subfolder and filename.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(uri="gs://some_bucket/subfolder/file.csv")

# Set a bucket directly
gs.bucket = "some_other_bucket"

# Use the bucket object as needed
gs.bucket.blob("subfolder/file.csv").download_to_filename("file.csv")
```

### blob(self) @property
Returns the blob object from the client based on the _subfolder_ and _filename_ attributes. Can be set directly (with the blob name, which sets both the subfolder and the filename) or with the \_\_init\_\_ or select_file methods. If no _filename_ is set, returns None.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(bucket="some_bucket")

# Set a blob directly
gs.blob = "subfolder/file.csv"

# Use the blob object as needed
gs.blob.download_to_filename("file.csv")
```

### uri(self) @property
Returns a string containing the URI for the currently set bucket, subfolder and filename. Can be set directly or with the \_\_init\_\_ method.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(bucket="some_bucket")

# Set a uri directly
gs.uri = "gs://some_other_bucket/subfolder/file.csv"

# Use the uri as needed
print(gs.uri)
```

### set_bucket(self, bucket)
Takes a string as a parameter to reset the _bucket_ name and bucket object. It has no return value.

This method also resets the _subfolder_ and _filename_ attributes.

**Warning:** this method doesn't check whether the bucket actually exists or not. This operation may not fail, but other methods and properties might do if the bucket doesn't exist.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(uri="gs://some_bucket/subfolder/file.csv")

# Note that it'll reset the subfolder and filename
gs.set_bucket("some_other_bucket")

# Check new path structure
print(gs.uri)

# output: gs://some_other_bucket/
```

### set_subfolder(self, subfolder)
Takes a string as the parameter to reset the _subfolder_ name. It has no return value.

This method also resets the _filename_ attribute.

**Warning:** this method doesn't check whether the subfolder path actually exists or not. This operation may not fail, but other methods and properties might do if the subfolder path doesn't exist.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(uri="gs://some_bucket/subfolder/file.csv")

# Note that it'll reset the filename
gs.set_subfolder("some/more_complex/subfolder/structure/")

# Check new path structure
print(gs.uri)

# output: gs://some_bucket/some/more_complex/subfolder/structure/
```

### select_file(self, filename)
Takes a string as the parameter to set or reset the _filename_, inside the current subfolder. It has no return value.

**Warning:** this method doesn't check whether the file actually exists or not. This operation may not fail, but other methods and properties might do if the file doesn't exist.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(uri="gs://some_bucket/subfolder/")

gs.select_file("file.csv")

# Check new path structure
print(gs.uri)

# output: gs://some_bucket/subfolder/file.csv
```

### list_all_buckets(self)
Returns a list with the information of all buckets in the project, each one a dictionary in the same format as the one returned by [get_bucket_info](#get_bucket_infoself-bucketnone). It takes no parameter.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


# Setting or not a subfolder doesn't change the output of this function
gs = GCloudStorageTool(bucket="some_bucket")

all_buckets = gs.list_all_buckets()
bucket_names = [bucket_info["Name"] for bucket_info in all_buckets]

# some code here
```

### get_bucket_info(self, bucket=None)
Returns a dictionary with the information of the currently selected _bucket_ (or the bucket object passed in the parameters).

The fields contained in the returned dictionary are:
- Name
- TimeCreated (a `datetime`)
- TimeUpdated (a `datetime`)
- OwnerID (empty string if not available)

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(bucket="some_bucket")

bucket_info = gs.get_bucket_info()
print(bucket_info["TimeCreated"].isoformat())
```

### get_file_info(self, filename=None, info=None)
Gets the remote file's information.

If no _filename_ is given, it uses the one already selected (raises a `ValueError` if no filename is set). A _filename_ is looked up inside the current subfolder. Raises a `FileNotFoundError` if the file doesn't exist.

If an _info_ parameter is given, returns only that info. If not, returns all the file's information in a dictionary.

The fields contained in the returned dictionary (and available) are:
- Name
- Bucket
- ContentType
- TimeCreated (a `datetime`)
- TimeUpdated (a `datetime`)
- TimeDeleted
- Size
- MD5
- OwnerID
- CRC32c
- EncryptionAlgorithm
- EncryptionKeySHA256

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(bucket="some_bucket", subfolder="some_subfolder", filename="file.csv")

remote_file_info = gs.get_file_info()
print(remote_file_info)

# Only the size of another file in the same subfolder
size = gs.get_file_info("other_file.csv", info="Size")
```

### list_contents(self, yield_results=False)
Lists all files under the currently set _bucket_ and _subfolder_, recursively (including the ones in nested "folders"). Each item is a dictionary with the file's information, in the same format as the one returned by [get_file_info](#get_file_infoself-filenamenone-infonone).

It can either return a list or a lazy iterator, if _yield_results_ is set to True. Lists can be more familiar to use, but when dealing with large amounts of data, yielding the results may be a better option in terms of efficiency.

For more information on how to use generators and yield, check this video:
https://www.youtube.com/watch?v=bD05uGo_sVI

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(uri="gs://some_bucket/subfolder/")

path_contents = gs.list_contents()

if len(path_contents) == 0:
    gs.set_subfolder("logs/subfolder/")

    # When a specific bucket/ bucket + subfolder contains a lot of data,
    # that's when yielding the results may be more efficient.
    for file_info in gs.list_contents(yield_results=True):
        print(file_info["Name"], file_info["Size"])

# some code here
```

### rename_file(self, new_filename)
Renames the selected file, keeping it in the same subfolder, and selects the new filename. Raises a `ValueError` if no file is selected.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(uri="gs://some_bucket/subfolder/old_filename.json")

# Renames "old_filename.json" to "new_filename.json"
gs.rename_file("new_filename.json")

print(gs.uri)
# output: gs://some_bucket/subfolder/new_filename.json
```

### rename_subfolder(self, new_subfolder)
Moves all files under the currently set subfolder to the _new_subfolder_, recursively (including the ones in nested "folders"), so the final result is similar to renaming a subfolder. The current subfolder is then set to the new one; the selected filename is kept.

Raises a `ValueError` if no subfolder is set, to avoid renaming every file in the bucket by accident.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(bucket="some_bucket", subfolder="a_generic_subfolder/", filename="filename.json")

# Renames subfolder from "a_generic_subfolder/" to "another_generic_subfolder/"
gs.rename_subfolder("another_generic_subfolder")

print(gs.uri)
# output: gs://some_bucket/another_generic_subfolder/filename.json
```

### upload_file(self, filename, remote_path=None)
Uploads a local file to a remote path in Google Cloud Storage (GS).

_remote_path_ can be either a full URI or a blob name (relative to the bucket root). If it ends with a slash (`/`), the file keeps its local name inside that "folder". If a URI has a different bucket than the one currently set, the bucket from the URI is ignored (with a warning).

If the _remote_path_ parameter is not set, it will default to one of two options:
- whatever subfolder plus filename attributes are set in the instance of the class, if the filename attribute is set;
- whatever subfolder is set in the instance of the class plus the name of the file that is being uploaded, if the filename attribute is not set.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


file_location = "C:\\Users\\USER\\Desktop\\file.csv"

gs = GCloudStorageTool(uri="gs://some_bucket/subfolder/")

# upload_file method accepts all these options
gs.upload_file(file_location)                                          # gs://some_bucket/subfolder/file.csv
gs.upload_file(file_location, "gs://some_bucket/other_subfolder/")     # gs://some_bucket/other_subfolder/file.csv
gs.upload_file(file_location, "another_subfolder/")                    # gs://some_bucket/another_subfolder/file.csv
gs.upload_file(file_location, "another_subfolder/renamed_file.csv")    # gs://some_bucket/another_subfolder/renamed_file.csv
```

### upload_subfolder(self, folder_path)
Uploads a local folder, recursively, into the currently set environment (bucket and subfolder).

Keeps the folder name and its structure as prefix in Google Cloud Storage, i.e. `./data/a.csv` uploaded to `gs://bucket/sub/` becomes `gs://bucket/sub/data/a.csv`.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


folder = "C:\\Users\\USER\\Documents\\some_folder"

gs = GCloudStorageTool(uri="gs://some_bucket/subfolder/")

gs.upload_subfolder(folder)
# folder contents will be in URI "gs://some_bucket/subfolder/some_folder/"
```

### upload_from_dataframe(self, dataframe, file_format="CSV", filename=None, overwrite=False, \*\*kwargs)
Uploads a _dataframe_ directly to a file in the _file_format_ given, without having to save the file locally.

If no _filename_ is given, it uses the selected file; otherwise, the _filename_ is looked up inside the current subfolder. If the file already exists, it raises a `FileExistsError`, unless _overwrite_ is set to True.

File formats supported are (any other raises a `ValueError`):
- CSV
- JSON

_\*\*kwargs_ are passed directly to the DataFrame.to_csv or DataFrame.to_json methods (according to the file format chosen).

The complete documentation of these methods can be found here:
- CSV: https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_csv.html
- JSON: https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_json.html

Usage example:
```python
import pandas as pd
from instackup.gcloudstorage_tools import GCloudStorageTool


df = pd.read_csv("C:\\Users\\USER\\Desktop\\file.csv")

gs = GCloudStorageTool(uri="gs://some_bucket/subfolder/")


gs.upload_from_dataframe(df, file_format="JSON", filename="file.json", orient="records", lines=True)

# or

gs.uri = "gs://some_bucket/subfolder/file.csv"
gs.upload_from_dataframe(df, overwrite=True, index=False)
```

### download_file(self, download_to=None, remote_filename=None, replace=False)
Downloads a remote GS file to a local path.

If the _remote_filename_ parameter is not set, it will default to the currently selected file (raises a `ValueError` if no file is selected). A _remote_filename_ is looked up inside the current subfolder.

_download_to_ can be either a local directory or a full local file path, if it ends with the remote file name. If it's not set, the file is downloaded to the current working directory. Missing local directories are created.

If _replace_ is set to True and there is already a file downloaded with the same filename and path, it will replace the file. Otherwise it will raise a `FileExistsError`.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(uri="gs://some_bucket/other_subfolder/file.csv")

# download_file method accepts both options
gs.download_file(download_to="C:\\Users\\USER\\Desktop")
gs.download_file(download_to="C:\\Users\\USER\\Desktop\\file.csv", replace=True)

# Another file in the same subfolder (gs://some_bucket/other_subfolder/other_file.csv)
gs.download_file(download_to="C:\\Users\\USER\\Desktop", remote_filename="other_file.csv")
```

### download_subfolder(self, download_to=None)
Downloads all remote Storage files in the currently set environment (bucket and subfolder), recursively, keeping their structure.

The files are saved in a local folder named after the subfolder (or `<bucket>_<timestamp>`, if no subfolder is set), created in the _download_to_ location or, if not set, in the current working directory. Files whose names would point outside that folder (e.g. with `..` in them) are skipped.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


desired_location = "C:\\Users\\USER\\Desktop\\downloaded_files"

gs = GCloudStorageTool(bucket="some_bucket", subfolder="some_subfolder/")

gs.download_subfolder(download_to=desired_location)
# files will be in "C:\\Users\\USER\\Desktop\\downloaded_files\\some_subfolder"
```

### download_on_dataframe(self, \*\*kwargs)
Uses the currently selected file to download it and load it directly into a Pandas DataFrame, without having to save the file. Raises a `ValueError` if no file is selected.

_\*\*kwargs_ are passed directly to the pandas.read_csv method.

The complete documentation of this method can be found here:
https://pandas.pydata.org/docs/reference/api/pandas.read_csv.html

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(uri="gs://some_bucket/subfolder/")

# For a well behaved file, you may just use the method directly
gs.select_file("file.csv")
df = gs.download_on_dataframe()

# For a file with a weird layout, you may want to use some parameters to save some time in data treatment
gs.select_file("weird_file.csv")
df = gs.download_on_dataframe(sep=";", encoding="ISO-8859-1", decimal=",")
```

### download_as_string(self, remote_filename=None, encoding="UTF-8")
Downloads a remote file directly into a Python string, decoded with the given _encoding_, without having to save it.

If the _remote_filename_ parameter is not set, it will default to the currently selected file. A _remote_filename_ is looked up inside the current subfolder.

Usage example:
```python
import json
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(uri="gs://some_bucket/subfolder/")
gs.select_file("file.json")

# Getting the file in a string format
file_string = gs.download_as_string()

# If it's a JSON file, for example, you can pass the result to the json.loads function
py_dict = json.loads(file_string)
```

### delete_file(self)
Deletes the selected file from Google Cloud Storage and resets the filename. Raises a `ValueError` if no file is selected.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(bucket="some_bucket", subfolder="some/subfolder/structure/", filename="file.csv")

# Delete file and reset filename
gs.delete_file()

print(gs.uri)
# output: gs://some_bucket/some/subfolder/structure/
```

### delete_subfolder(self)
Deletes all files with the subfolder prefix, recursively, so the final result is similar to deleting a subfolder.

Raises a `ValueError` if no subfolder is set, to avoid emptying the bucket by accident.

Once the subfolder is deleted, the subfolder and filename are reset.

Usage example:
```python
from instackup.gcloudstorage_tools import GCloudStorageTool


gs = GCloudStorageTool(bucket="some_bucket", subfolder="some/subfolder/structure/")

# Delete subfolder and reset filename and subfolder name
gs.delete_subfolder()

print(gs.uri)
# output: gs://some_bucket/
```

## split_gcs_uri(uri)
Splits a Google Cloud Storage URI into a (bucket, subfolder, filename) tuple.

A URI ending with a slash (`/`), or with only a bucket, points to a folder, so the filename is None. The subfolder, when present, always ends with a slash. Raises a `ValueError` if the URI isn't in the `gs://<bucket>[/<subfolder>][/<filename>]` format.

Usage example:
```python
from instackup.gcloudstorage_tools import split_gcs_uri


print(split_gcs_uri("gs://some_bucket/subfolder/example.txt"))
# output: >>> ('some_bucket', 'subfolder/', 'example.txt')

print(split_gcs_uri("gs://some_bucket/subfolder/"))
# output: >>> ('some_bucket', 'subfolder/', None)
```
