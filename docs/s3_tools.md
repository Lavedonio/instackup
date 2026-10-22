# s3_tools
This is the documentation for the s3_tools module and all its contents, with usage examples.

This module needs the `aws` extra: `pip install 'instackup[aws]'`.

Credentials come from environment variables, a credentials file or the cloud platform identity (see [credentials.md](credentials.md)).

# Index
- [S3Tool](#s3tool)
  - [\_\_init\_\_(self, uri=None, bucket=None, subfolder="", connection="default", \*, credentials=None, session=None)](#__init__self-urinone-bucketnone-subfolder-connectiondefault--credentialsnone-sessionnone)
  - [bucket(self) @property](#bucketself-property)
  - [uri(self) @property](#uriself-property)
  - [set_bucket(self, bucket)](#set_bucketself-bucket)
  - [set_subfolder(self, subfolder)](#set_subfolderself-subfolder)
  - [rename_file(self, old_filename, new_filename)](#rename_fileself-old_filename-new_filename)
  - [rename_subfolder(self, new_subfolder)](#rename_subfolderself-new_subfolder)
  - [list_all_buckets(self)](#list_all_bucketsself)
  - [list_contents(self, yield_results=False)](#list_contentsself-yield_resultsfalse)
  - [upload_file(self, filename, remote_path=None)](#upload_fileself-filename-remote_pathnone)
  - [upload_subfolder(self, folder_path)](#upload_subfolderself-folder_path)
  - [download_file(self, remote_path, filename=None, replace=False)](#download_fileself-remote_path-filenamenone-replacefalse)
  - [download_subfolder(self, download_to=None)](#download_subfolderself-download_tonone)
  - [delete_file(self, filename, fail_silently=False)](#delete_fileself-filename-fail_silentlyfalse)
  - [delete_subfolder(self)](#delete_subfolderself)

# Module Contents
## S3Tool
This class handles most of the interaction needed with S3, so the base code becomes more readable and straightforward.

To understand the S3 structure, you need to know it is not a hierarchical filesystem, it is only a key-value store, though the key is often used like a file path for organising data, prefix + filename. More information about this can be read in this StackOverflow thread:
https://stackoverflow.com/questions/52443839/s3-what-exactly-is-a-prefix-and-what-ratelimits-apply

All that means is that while you may see a path as:
```text
s3://bucket-1/folder1/subfolder1/some_file.csv
root| folder | sub.1 |  sub.2   |    file    |
```

It is actually:
```text
s3://bucket-1/folder1/sub1/file.csv
root| bucket |         key        |
```

A great (not directly related) thread that can help that sink in (and help understand some methods here) is this one: https://stackoverflow.com/questions/35803027/retrieving-subfolders-names-in-s3-bucket-from-boto3

In this class, all keys and key prefixes are treated as a folder tree structure, since the reason for this to exist is to make the programmers' interactions with S3 easier to write and the code easier to read.

### \_\_init\_\_(self, uri=None, bucket=None, subfolder="", connection="default", \*, credentials=None, session=None)
Takes either a _uri_ or a _bucket_ name (and, optionally, a _subfolder_ name) as parameters to set the current working directory. Raises a `ValueError` if both _uri_ and _bucket_ are given. In this implementation, a subfolder **always** ends with a slash (`/`), which is added if missing.

The paradigm of this class is that all the operations are done in the current working directory, so it is important to set the right path (you can reset it later, but still).

It also creates the S3 resource (the _s3_ attribute) with the AWS credentials of the _connection_ parameter, read from the `aws` service settings in the credential store (`access_key`, `secret_key`, `session_token`, `profile` and `region`). Without them, boto3's default credential chain is used (environment, shared config/SSO, container and instance roles), which is the recommended setup in production. A named connection other than "default" must exist in the credential store.

The keyword-only _credentials_ parameter takes those AWS settings directly instead, and the keyword-only _session_ parameter takes a ready `boto3.Session`.

Usage example:
```python
import boto3
from instackup.s3_tools import S3Tool


s3 = S3Tool(uri="s3://some_bucket/subfolder/")

# or

s3 = S3Tool(bucket="some_other_bucket", subfolder="some_subfolder/subpath/")

# or

s3 = S3Tool(uri="s3://some_bucket/subfolder/", session=boto3.Session(profile_name="analytics"))
```

### bucket(self) @property
Returns the bucket object from the S3 resource based on the _bucket_name_ attribute. Can be set directly or with the \_\_init\_\_ or set_bucket methods; setting it resets the subfolder.

Usage example:
```python
from instackup.s3_tools import S3Tool


s3 = S3Tool(uri="s3://some_bucket/subfolder/")

# Set a bucket directly
s3.bucket = "some_other_bucket"

# Use the bucket object as needed
for obj in s3.bucket.objects.all():
    print(obj.key)
```

### uri(self) @property
Returns a string containing the URI for the currently set bucket and subfolder. Can be set directly or with the \_\_init\_\_ method.

Usage example:
```python
from instackup.s3_tools import S3Tool


s3 = S3Tool(bucket="some_bucket", subfolder="subfolder/")

# Set a uri directly
s3.uri = "s3://some_other_bucket/some/more_complex/subfolder/structure/"

# Use the uri as needed
print(s3.uri)
```

### set_bucket(self, bucket)
Takes a string as a parameter to reset the _bucket_ name, and so its bucket object. It also resets the _subfolder_. It has no return value.

Usage example:
```python
from instackup.s3_tools import S3Tool


s3 = S3Tool(uri="s3://some_bucket/subfolder/")

s3.set_bucket("some_other_bucket")

# Check new path structure
print(s3.uri)

# output: s3://some_other_bucket/
```

### set_subfolder(self, subfolder)
Takes a string as the parameter to reset the _subfolder_ name. It has no return value.

Usage example:
```python
from instackup.s3_tools import S3Tool


s3 = S3Tool(uri="s3://some_bucket/subfolder/")

s3.set_subfolder("some/more_complex/subfolder/structure/")

# Check new path structure
print(s3.uri)

# output: s3://some_bucket/some/more_complex/subfolder/structure/
```

### rename_file(self, old_filename, new_filename)
Takes 2 strings containing file names inside the current subfolder and renames the file, by copying it to the new key and then deleting the old one. It has no return value.

Raises a `ValueError` if the file doesn't exist.

Usage example:
```python
from instackup.s3_tools import S3Tool


s3 = S3Tool(bucket="some_bucket", subfolder="subfolder/")

s3.rename_file("old_name.csv", "new_name.csv")
```

### rename_subfolder(self, new_subfolder)
Takes a string containing the _new subfolder_ name and moves all keys under the currently set subfolder to it, recursively (including the ones in nested "folders"), so the final result is similar to renaming a subfolder. The current subfolder is then set to the new one. It has no return value.

Raises a `ValueError` if no subfolder is set, to avoid renaming every file in the bucket by accident.

Usage example:
```python
from instackup.s3_tools import S3Tool


old_subfolder = "some/more_complex/subfolder/structure/"
new_subfolder = "some/new/subfolder/structure/"

s3 = S3Tool(bucket="some_bucket", subfolder=old_subfolder)

# The final result is similar to just renaming the "more_complex" folder to "new"
s3.rename_subfolder(new_subfolder)

print(s3.uri)
# output: s3://some_bucket/some/new/subfolder/structure/
```

### list_all_buckets(self)
Returns a list with the names of all buckets in S3. It takes no parameter.

Usage example:
```python
from instackup.s3_tools import S3Tool


# Setting or not a subfolder doesn't change the output of this function
s3 = S3Tool(bucket="some_bucket")

all_buckets = s3.list_all_buckets()

# some code here
```

### list_contents(self, yield_results=False)
Lists the keys in the currently set bucket and subfolder. Without a subfolder, it lists every key in the bucket; with one, only the files directly inside it (not the ones in nested "folders").

It can either return a list or a lazy iterator, if _yield_results_ is set to True. Lists can be more familiar to use, but when dealing with large amounts of data, yielding the results may be a better option in terms of efficiency.

For more information on how to use generators and yield, check this video:
https://www.youtube.com/watch?v=bD05uGo_sVI

Usage example:
```python
from instackup.s3_tools import S3Tool


s3 = S3Tool(uri="s3://some_bucket/subfolder/")

path_contents = s3.list_contents()

if len(path_contents) == 0:
    s3.set_subfolder("logs/subfolder/")

    # When a specific bucket/ bucket + subfolder contains a lot of data,
    # that's when yielding the results may be more efficient.
    for key in s3.list_contents(yield_results=True):
        print(key)

# some code here
```

### upload_file(self, filename, remote_path=None)
Uploads a local file to a remote path in S3. It has no return value.

_remote_path_ can be either a full URI or a key (relative to the bucket root). If it ends with a slash (`/`), the file keeps its local name inside that "folder". If a URI has a different bucket than the one currently set, the bucket from the URI is ignored (with a warning).

If the _remote_path_ parameter is not set, it will default to whatever subfolder is set in the instance of the class plus the _file name_ that is being uploaded.

Usage example:
```python
from instackup.s3_tools import S3Tool


file_location = "C:\\Users\\USER\\Desktop\\file.csv"

s3 = S3Tool(uri="s3://some_bucket/subfolder/")

# upload_file method accepts all these options
s3.upload_file(file_location)                                          # s3://some_bucket/subfolder/file.csv
s3.upload_file(file_location, "s3://some_bucket/other_subfolder/")     # s3://some_bucket/other_subfolder/file.csv
s3.upload_file(file_location, "another_subfolder/")                    # s3://some_bucket/another_subfolder/file.csv
s3.upload_file(file_location, "another_subfolder/renamed_file.csv")    # s3://some_bucket/another_subfolder/renamed_file.csv
```

### upload_subfolder(self, folder_path)
Uploads a local folder, recursively, into the currently set environment (bucket and subfolder). It has no return value.

Keeps the folder name and its structure as prefix in S3, i.e. `./data/a.csv` uploaded to `s3://bucket/sub/` becomes `s3://bucket/sub/data/a.csv`.

Usage example:
```python
from instackup.s3_tools import S3Tool


folder = "C:\\Users\\USER\\Documents\\some_folder"

s3 = S3Tool(uri="s3://some_bucket/subfolder/")

s3.upload_subfolder(folder)
# folder contents will be in URI "s3://some_bucket/subfolder/some_folder/"
```

### download_file(self, remote_path, filename=None, replace=False)
Downloads a remote S3 file to a local path. It has no return value.

_remote_path_ can be either a full URI or a key (relative to the bucket root). If a URI has a different bucket than the one currently set, the bucket from the URI is ignored (with a warning).

If the _filename_ parameter is not set, the file is saved as `<current subfolder>/<remote file name>`, relative to the current working directory. Missing local directories are created.

If there's already a local file with the same path, it raises a `FileExistsError`, unless _replace_ is set to True, in which case the file is replaced.

Usage example:
```python
from instackup.s3_tools import S3Tool


file_desired_location = "C:\\Users\\USER\\Desktop\\file.csv"
remote_location = "s3://some_bucket/other_subfolder/file.csv"

s3 = S3Tool(uri="s3://some_bucket/subfolder/")

# download_file method accepts both options
s3.download_file(remote_location)  # Saved in "subfolder/file.csv"
s3.download_file(remote_location, file_desired_location, replace=True)
```

### download_subfolder(self, download_to=None)
Downloads all remote S3 files in the currently set environment (bucket and subfolder), recursively, keeping their structure. It has no return value.

The files are saved in a local folder named after the subfolder (or `<bucket>_<timestamp>`, if no subfolder is set), created in the _download_to_ location or, if not set, in the current working directory. Keys that would point outside that folder (e.g. with `..` in them) are skipped.

Usage example:
```python
from instackup.s3_tools import S3Tool


desired_location = "C:\\Users\\USER\\Desktop\\downloaded_files"

s3 = S3Tool(uri="s3://some_bucket/subfolder/")

s3.download_subfolder(download_to=desired_location)
# files will be in "C:\\Users\\USER\\Desktop\\downloaded_files\\subfolder"
```

### delete_file(self, filename, fail_silently=False)
Deletes a file from the currently set path. It has no return value.

Raises a `ValueError` if the file doesn't exist, unless the _fail_silently_ parameter is set to True.

Usage example:
```python
from instackup.s3_tools import S3Tool


filename = "file.csv"

s3 = S3Tool(uri="s3://some_bucket/subfolder/")

s3.delete_file(filename)

# Will fail to delete the same file it was deleted before,
# but won't raise any error due to fail_silently being set to True
s3.delete_file(filename, fail_silently=True)
```

### delete_subfolder(self)
Deletes all files with the subfolder prefix, recursively, so the final result is similar to deleting a subfolder. It has no return value.

Raises a `ValueError` if no subfolder is set, to avoid emptying the bucket by accident.

Once the subfolder is deleted, it resets to no extra path (empty subfolder name).

Usage example:
```python
from instackup.s3_tools import S3Tool


s3 = S3Tool(uri="s3://some_bucket/subfolder/")

s3.delete_subfolder()

# Check new path structure
print(s3.uri)

# output: s3://some_bucket/
```
