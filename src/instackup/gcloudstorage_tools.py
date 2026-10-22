"""Google Cloud Storage tool."""

from __future__ import annotations

import io
import logging
import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Literal, overload

import pandas as pd

from ._google import resolve_google_auth
from ._utils import as_folder, local_path_for, missing_extra_message, timestamped_dir_name
from .general_tools import parse_remote_uri

try:
    import google.cloud.storage as storage
except ImportError as exc:  # pragma: no cover - depends on installed extras
    raise ImportError(missing_extra_message("gcp")) from exc

logger = logging.getLogger(__name__)


def split_gcs_uri(uri: str) -> tuple[str, str, str | None]:
    """Split ``gs://bucket/folder/file`` into (bucket, subfolder, filename).

    A URI ending in "/" (or with only a bucket) points to a folder, so filename is None.
    """
    bucket, key = parse_remote_uri(uri, "gs")
    if not key or uri.endswith("/"):
        return bucket, key, None
    folder, _, filename = key.rstrip("/").rpartition("/")
    return bucket, as_folder(folder), filename


class GCloudStorageTool:
    """Handles most of the interaction needed with Google Cloud Storage.

    Authenticates with the ``google.<connection>`` settings in the credential store
    (or ``credentials``), falling back to Application Default Credentials. With
    ``authenticate=False`` the store is skipped (explicit ``credentials`` still apply). A ready
    ``google.cloud.storage.Client`` can be passed as ``client`` instead.
    """

    def __init__(
        self,
        uri: str | None = None,
        bucket: str | None = None,
        subfolder: str = "",
        filename: str | None = None,
        connection: str = "default",
        authenticate: bool = True,
        *,
        credentials: Mapping[str, Any] | None = None,
        client: storage.Client | None = None,
    ) -> None:
        if bucket is not None and uri is not None:
            logger.error("Specify either bucket name or full Google Cloud Storage path.")
            raise ValueError("Specify either bucket name or full Google Cloud Storage path.")

        # A URI takes priority over the subfolder and filename parameters.
        if uri is not None:
            bucket, subfolder, filename = split_gcs_uri(uri)
        else:
            subfolder = as_folder(subfolder)

        project = None
        if client is None:
            logger.debug("Initiating Google Cloud Storage Client")
            auth = resolve_google_auth(connection, credentials, use_config=authenticate)
            client = storage.Client(project=auth.project_id, credentials=auth.credentials)
            project = auth.project_info

        self.client = client
        self.bucket_name = bucket
        self.subfolder = subfolder
        self.filename = filename
        self.project = project

    @property
    def bucket(self) -> storage.Bucket:
        # A local reference: no API call, so object-level permissions are enough.
        return self.client.bucket(self.bucket_name)

    @bucket.setter
    def bucket(self, bucket_name: str) -> None:
        self.set_bucket(bucket_name)

    @property
    def blob(self) -> storage.Blob | None:
        if self.filename is None:
            return None
        return self.bucket.blob(self.subfolder + self.filename)

    @blob.setter
    def blob(self, blob_name: str) -> None:
        subfolder, _, self.filename = blob_name.rpartition("/")
        self.subfolder = as_folder(subfolder)

    @property
    def uri(self) -> str:
        return f"gs://{self.bucket_name}/{self.subfolder}{self.filename or ''}"

    @uri.setter
    def uri(self, uri: str) -> None:
        self.bucket_name, self.subfolder, self.filename = split_gcs_uri(uri)

    def set_bucket(self, bucket: str) -> None:
        self.bucket_name = bucket
        self.subfolder = ""  # Resets subfolder
        self.filename = None  # Resets filename

    def set_subfolder(self, subfolder: str) -> None:
        self.subfolder = as_folder(subfolder)
        self.filename = None  # Resets filename

    def select_file(self, filename: str) -> None:
        self.filename = filename

    def _require_blob(self, remote_filename: str | None = None) -> storage.Blob:
        if remote_filename is not None:
            return self.bucket.blob(self.subfolder + remote_filename)
        blob = self.blob
        if blob is None:
            raise ValueError("No file selected. Set it with the select_file method first or pass a filename.")
        return blob

    def _require_subfolder(self, action: str) -> None:
        if not self.subfolder:
            raise ValueError(f"No subfolder set. Refusing to {action} every object in bucket {self.bucket_name!r}.")

    def list_all_buckets(self) -> list[dict[str, Any]]:
        """Info of all buckets in the project."""
        return [self.get_bucket_info(bucket) for bucket in self.client.list_buckets()]

    def get_bucket_info(self, bucket: storage.Bucket | None = None) -> dict[str, Any]:
        """Name, creation/update times and owner of a bucket (the current one by default)."""
        if bucket is None:
            bucket = self.client.get_bucket(self.bucket_name)

        return {
            "Name": bucket.name,
            "TimeCreated": bucket.time_created,
            "TimeUpdated": bucket.updated,
            "OwnerID": (bucket.owner or {}).get("entityId", ""),
        }

    @staticmethod
    def _blob_info(blob: storage.Blob, param: str | None = None) -> Any:
        """Convert a ``google.cloud.storage.Blob`` to a dictionary (or one of its values)."""
        encryption = blob._properties.get("customerEncryption", {})  # No public accessor for these
        blob_info = {
            "Name": blob.name,
            "Bucket": blob.bucket.name,
            "ContentType": blob.content_type,
            "TimeCreated": blob.time_created,
            "TimeUpdated": blob.updated,
            "TimeDeleted": blob.time_deleted,
            "Size": blob.size,
            "MD5": blob.md5_hash,
            "OwnerID": (blob.owner or {}).get("entityId", ""),
            "CRC32c": blob.crc32c,
            "EncryptionAlgorithm": encryption.get("encryptionAlgorithm", ""),
            "EncryptionKeySHA256": encryption.get("keySha256", ""),
        }

        if param is not None:
            return blob_info[param]
        return blob_info

    def get_file_info(self, filename: str | None = None, info: str | None = None) -> Any:
        """Metadata of a remote file, as a dictionary, or only the ``info`` field if given.

        Uses the selected file unless ``filename`` is given. Raises
        ``FileNotFoundError`` if the file doesn't exist.
        """
        name = self._require_blob(filename).name
        blob = self.bucket.get_blob(name)  # Fetches the metadata
        if blob is None:
            raise FileNotFoundError(f"File gs://{self.bucket_name}/{name} not found.")
        return self._blob_info(blob, info)

    @overload
    def list_contents(self, yield_results: Literal[False] = ...) -> list[dict[str, Any]]: ...
    @overload
    def list_contents(self, yield_results: Literal[True]) -> Iterator[dict[str, Any]]: ...

    def list_contents(self, yield_results: bool = False) -> list[dict[str, Any]] | Iterator[dict[str, Any]]:
        """Info of every file under the current subfolder (recursively).

        Returns a list, or a lazy iterator if ``yield_results`` is True, which is
        better for large buckets.
        """
        contents = self._iter_contents()
        return contents if yield_results else list(contents)

    def _iter_contents(self) -> Iterator[dict[str, Any]]:
        for blob in self.client.list_blobs(self.bucket_name, prefix=self.subfolder or None):
            if not blob.name.endswith("/"):  # Skip "folder" placeholder objects
                yield self._blob_info(blob)

    def rename_file(self, new_filename: str) -> None:
        """Rename the selected file, keeping it in the same subfolder."""
        if self.filename is None:
            raise ValueError("No filename set. Use the select_file method to do so first.")

        self.bucket.rename_blob(self._require_blob(), self.subfolder + new_filename)
        self.filename = new_filename

    def rename_subfolder(self, new_subfolder: str) -> None:
        """Move every file under the current subfolder (recursively) to ``new_subfolder``."""
        self._require_subfolder("rename")
        new_subfolder = as_folder(new_subfolder)

        # List everything first: renamed blobs may still match the prefix (e.g. "data/" -> "data/old/").
        for blob in list(self.client.list_blobs(self.bucket_name, prefix=self.subfolder)):
            self.bucket.rename_blob(blob, new_subfolder + blob.name[len(self.subfolder) :])

        self.subfolder = new_subfolder

    def _blob_name_from_remote_path(self, remote_path: str) -> str:
        """Blob name from a full ``gs://`` URI or a plain name. A URI's bucket is ignored (with a warning)."""
        try:
            bucket, name = parse_remote_uri(remote_path, "gs")
        except ValueError:
            return remote_path

        if bucket != self.bucket_name:
            logger.warning(
                "Path given has different bucket than the one that is currently set. Ignoring bucket from path."
            )
        # parse_remote_uri() adds a trailing "/"; keep it only if the URI pointed to a folder.
        return name if remote_path.endswith("/") else name[:-1]

    def upload_file(self, filename: str, remote_path: str | None = None) -> None:
        """Upload a local file.

        ``remote_path`` can be a full URI or a blob name; if it ends with "/", the file
        keeps its local name inside that folder. If not set, the file goes to the
        current subfolder, named after the selected file or, if none is selected, after
        the local file.
        """
        if remote_path is None:
            remote_path = self.subfolder + (self.filename or os.path.basename(filename))
        else:
            remote_path = self._blob_name_from_remote_path(remote_path)
            if not remote_path or remote_path.endswith("/"):
                remote_path += os.path.basename(filename)

        logger.info("Uploading file %s to gs://%s/%s", filename, self.bucket_name, remote_path)
        self.bucket.blob(remote_path).upload_from_filename(filename)

    def upload_subfolder(self, folder_path: str) -> None:
        """Upload a local folder into the current location, keeping its structure.

        ``./data/a.csv`` uploaded to ``gs://bucket/sub/`` becomes ``gs://bucket/sub/data/a.csv``.
        """
        folder = Path(folder_path)
        prefix = f"{self.subfolder}{folder.resolve().name}/"
        logger.info("Uploading local folder %s to gs://%s/%s", folder_path, self.bucket_name, prefix)

        for local_file in sorted(folder.rglob("*")):
            if local_file.is_file():
                remote_path = prefix + local_file.relative_to(folder).as_posix()
                logger.info("Uploading file %s to gs://%s/%s", local_file, self.bucket_name, remote_path)
                self.bucket.blob(remote_path).upload_from_filename(str(local_file))

        logger.info("Finished uploading local folder %s to gs://%s/%s", folder_path, self.bucket_name, prefix)

    def upload_from_dataframe(
        self,
        dataframe: pd.DataFrame,
        file_format: str = "CSV",
        filename: str | None = None,
        overwrite: bool = False,
        **kwargs: Any,
    ) -> None:
        """Upload a DataFrame as a CSV or JSON file, without saving it locally.

        Uses the selected file unless ``filename`` is given; raises ``FileExistsError``
        if the file exists and ``overwrite`` is False. ``kwargs`` go to
        ``DataFrame.to_csv`` or ``DataFrame.to_json``.
        """
        file_format = file_format.upper()
        if file_format == "CSV":
            kwargs.setdefault("lineterminator", "\n")  # pandas defaults to the OS separator
            data, content_type = dataframe.to_csv(**kwargs), "text/csv"
        elif file_format == "JSON":
            data, content_type = dataframe.to_json(**kwargs), "application/json"
        else:
            raise ValueError(f"File format {file_format} not supported. Supported formats are 'CSV' and 'JSON'.")

        blob = self._require_blob(filename)
        if not overwrite and blob.exists():
            raise FileExistsError("File already exists and overwrite is set to False.")

        blob.upload_from_string(data, content_type=content_type)

    def download_file(
        self, download_to: str | None = None, remote_filename: str | None = None, replace: bool = False
    ) -> None:
        """Download a remote file.

        Uses the selected file unless ``remote_filename`` is given. ``download_to`` is
        either a directory or a full local file path ending in the remote file name;
        defaults to the current working directory. Raises ``FileExistsError`` if the
        local file exists, unless ``replace`` is True.
        """
        blob = self._require_blob(remote_filename)
        local_name = os.path.basename(blob.name)

        target = Path(local_name)
        if download_to is not None:
            destination = Path(download_to)
            target = destination if destination.name == local_name else destination / local_name

        logger.debug("Blob name: %s, local filename: %s", blob.name, target)
        if target.exists() and not replace:
            logger.error("File already exists at %s.", target.resolve())
            raise FileExistsError(f"File already exists at {target.resolve()}. Clean the folder to continue.")

        target.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(str(target))
        logger.info("File downloaded successfully")

    def download_subfolder(self, download_to: str | None = None) -> None:
        """Download everything under the current location (recursively) into a local folder.

        The folder is named after the subfolder (or ``<bucket>_<timestamp>`` at the
        bucket root) and created in ``download_to`` or the current working directory.
        """
        if self.subfolder:
            download_dir = Path(self.subfolder.rstrip("/").rsplit("/", 1)[-1])
        else:
            download_dir = Path(timestamped_dir_name(str(self.bucket_name)))
        if download_to is not None:
            download_dir = Path(download_to) / download_dir

        logger.info("Downloading files...")
        for blob in self.client.list_blobs(self.bucket_name, prefix=self.subfolder or None):
            if blob.name.endswith("/"):  # "Folder" placeholder objects
                continue
            local_filename = local_path_for(download_dir, blob.name[len(self.subfolder) :])
            if local_filename is None:
                logger.warning(
                    "Skipping gs://%s/%s: its name points outside the download folder.", self.bucket_name, blob.name
                )
                continue
            local_filename.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Downloading remote file gs://%s/%s to %s", self.bucket_name, blob.name, local_filename)
            blob.download_to_filename(str(local_filename))

    def download_on_dataframe(self, **kwargs: Any) -> pd.DataFrame:
        """Read the selected CSV file directly into a DataFrame, without saving it locally.

        ``kwargs`` go to ``pandas.read_csv``.
        """
        blob = self._require_blob()
        logger.debug("gs path: %s", self.uri)
        return pd.read_csv(io.BytesIO(blob.download_as_bytes()), **kwargs)

    def download_as_string(self, remote_filename: str | None = None, encoding: str = "UTF-8") -> str:
        """Read a remote file directly into a string, without saving it locally."""
        return self._require_blob(remote_filename).download_as_bytes().decode(encoding)

    def delete_file(self) -> None:
        """Delete the selected file."""
        if self.filename is None:
            raise ValueError("No filename set. Use the select_file method to do so first.")

        self.bucket.delete_blob(self.subfolder + self.filename)
        self.filename = None  # It doesn't exist anymore

    def delete_subfolder(self) -> None:
        """Delete every file under the current subfolder (recursively), then reset location.

        Raises ``ValueError`` when no subfolder is set, to avoid emptying the bucket by accident.
        """
        self._require_subfolder("delete")
        self.bucket.delete_blobs(list(self.client.list_blobs(self.bucket_name, prefix=self.subfolder)))

        # They don't exist anymore
        self.subfolder = ""
        self.filename = None
