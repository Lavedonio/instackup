"""Amazon S3 tool."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Literal, overload

from ._aws import ClientError, create_session
from ._utils import as_folder, local_path_for, timestamped_dir_name
from .general_tools import parse_remote_uri

logger = logging.getLogger(__name__)


class S3Tool:
    """Handles most of the interaction needed with S3.

    S3 is not a hierarchical filesystem but a key-value store, even though keys are
    often written like file paths (prefix + filename)::

        s3://bucket-1/folder1/sub1/file.csv
        root| bucket |        key         |

    More on that: https://stackoverflow.com/questions/52443839/s3-what-exactly-is-a-prefix-and-what-ratelimits-apply

    This class treats keys and key prefixes as a folder tree, which makes code that
    works with S3 easier to write and read.

    AWS credentials come from ``credentials`` or the ``aws.<connection>`` settings in
    the credential store; without them, boto3's default credential chain is used.
    A ready ``boto3.Session`` can be passed as ``session`` instead.
    """

    def __init__(
        self,
        uri: str | None = None,
        bucket: str | None = None,
        subfolder: str = "",
        connection: str = "default",
        *,
        credentials: Mapping[str, Any] | None = None,
        session: Any = None,
    ) -> None:
        if bucket is not None and uri is not None:
            logger.error("Specify either bucket name or an URI.")
            raise ValueError("Specify either bucket name or an URI.")

        # A URI takes priority over the subfolder parameter.
        if uri is not None:
            bucket, subfolder = parse_remote_uri(uri, "s3")

        if session is None:
            session = create_session(connection, credentials)
        self.s3 = session.resource("s3")
        logger.debug("Connected to S3 by boto3")

        self.bucket_name = bucket
        self.subfolder = as_folder(subfolder)

    @property
    def bucket(self) -> Any:
        return self.s3.Bucket(self.bucket_name)

    @bucket.setter
    def bucket(self, bucket_name: str) -> None:
        self.set_bucket(bucket_name)

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket_name}/{self.subfolder}"

    @uri.setter
    def uri(self, uri: str) -> None:
        self.bucket_name, self.subfolder = parse_remote_uri(uri, "s3")

    def set_bucket(self, bucket: str) -> None:
        self.bucket_name = bucket
        self.subfolder = ""  # Resets subfolder

    def set_subfolder(self, subfolder: str) -> None:
        self.subfolder = as_folder(subfolder)

    def _key_exists(self, key: str) -> bool:
        try:
            self.s3.Object(self.bucket_name, key).load()
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        return True

    def _require_subfolder(self, action: str) -> None:
        if not self.subfolder:
            raise ValueError(f"No subfolder set. Refusing to {action} every object in bucket {self.bucket_name!r}.")

    def rename_file(self, old_filename: str, new_filename: str) -> None:
        """Rename a file inside the current subfolder (copy to the new key, then delete the old one)."""
        old_key = self.subfolder + old_filename
        new_key = self.subfolder + new_filename

        if not self._key_exists(old_key):
            logger.error("File %s does not exist in path %s", old_filename, self.uri)
            raise ValueError(f"File {old_filename} does not exist in path {self.uri}")

        self.s3.Object(self.bucket_name, new_key).copy_from(CopySource={"Bucket": self.bucket_name, "Key": old_key})
        self.s3.Object(self.bucket_name, old_key).delete()

    def rename_subfolder(self, new_subfolder: str) -> None:
        """Move every key under the current subfolder (recursively) to ``new_subfolder``."""
        self._require_subfolder("rename")
        new_subfolder = as_folder(new_subfolder)

        # List everything first: renamed keys may still match the prefix (e.g. "data/" -> "data/old/").
        for obj in list(self.bucket.objects.filter(Prefix=self.subfolder)):
            new_key = new_subfolder + obj.key[len(self.subfolder) :]
            logger.debug("Renaming %s to %s", obj.key, new_key)
            self.s3.Object(self.bucket_name, new_key).copy_from(CopySource={"Bucket": self.bucket_name, "Key": obj.key})
            obj.delete()

        self.set_subfolder(new_subfolder)

    def list_all_buckets(self) -> list[str]:
        """Names of all buckets in S3."""
        return [bucket.name for bucket in self.s3.buckets.all()]

    @overload
    def list_contents(self, yield_results: Literal[False] = ...) -> list[str]: ...
    @overload
    def list_contents(self, yield_results: Literal[True]) -> Iterator[str]: ...

    def list_contents(self, yield_results: bool = False) -> list[str] | Iterator[str]:
        """Keys in the current location.

        Without a subfolder, every key in the bucket; with one, only its direct
        children (not keys in nested "folders"). Returns a list, or a lazy iterator if
        ``yield_results`` is True, which is better for large buckets.
        """
        contents = self._iter_contents()
        return contents if yield_results else list(contents)

    def _iter_contents(self) -> Iterator[str]:
        if not self.subfolder:
            for obj in self.bucket.objects.all():
                yield obj.key
        else:
            for obj in self.bucket.objects.filter(Prefix=self.subfolder, Delimiter="/"):
                if obj.key != self.subfolder:
                    yield obj.key

    def _key_from_remote_path(self, remote_path: str) -> str:
        """Key from a full ``s3://`` URI or a plain key. A URI's bucket is ignored (with a warning)."""
        try:
            bucket, key = parse_remote_uri(remote_path, "s3")
        except ValueError:
            return remote_path

        if bucket != self.bucket_name:
            logger.warning(
                "Path given has different bucket than the one that is currently set. Ignoring bucket from path."
            )
        # parse_remote_uri() adds a trailing "/"; keep it only if the URI pointed to a folder.
        return key if remote_path.endswith("/") else key[:-1]

    def upload_file(self, filename: str, remote_path: str | None = None) -> None:
        """Upload a local file.

        ``remote_path`` can be a full URI or a key; if it ends with "/", the file keeps
        its local name inside that folder. If not set, the file is uploaded to the
        current subfolder with its own name.
        """
        if remote_path is None:
            remote_path = self.subfolder + os.path.basename(filename)
        else:
            remote_path = self._key_from_remote_path(remote_path)
            if not remote_path or remote_path.endswith("/"):
                remote_path += os.path.basename(filename)

        logger.info("Uploading file %s to s3://%s/%s", filename, self.bucket_name, remote_path)
        self.bucket.upload_file(filename, remote_path)

    def upload_subfolder(self, folder_path: str) -> None:
        """Upload a local folder into the current location, keeping its structure.

        ``./data/a.csv`` uploaded to ``s3://bucket/sub/`` becomes ``s3://bucket/sub/data/a.csv``.
        """
        folder = Path(folder_path)
        prefix = f"{self.subfolder}{folder.resolve().name}/"
        logger.info("Uploading local folder %s to s3://%s/%s", folder_path, self.bucket_name, prefix)

        for local_file in sorted(folder.rglob("*")):
            if local_file.is_file():
                remote_path = prefix + local_file.relative_to(folder).as_posix()
                logger.info("Uploading file %s to s3://%s/%s", local_file, self.bucket_name, remote_path)
                self.bucket.upload_file(str(local_file), remote_path)

        logger.info("Finished uploading local folder %s to s3://%s/%s", folder_path, self.bucket_name, prefix)

    def download_file(self, remote_path: str, filename: str | None = None, replace: bool = False) -> None:
        """Download an S3 file to a local path.

        ``remote_path`` can be a full URI or a key. If ``filename`` is not set, the
        file is saved as ``<current subfolder>/<remote file name>``, relative to the
        current working directory. Raises ``FileExistsError`` if the local file exists,
        unless ``replace`` is True.
        """
        key = self._key_from_remote_path(remote_path)
        if filename is None:
            filename = self.subfolder + os.path.basename(remote_path)

        target = Path(filename)
        if target.exists() and not replace:
            logger.error("File already exists at %s.", target.resolve())
            raise FileExistsError(f"File already exists at {target.resolve()}. Clean the folder to continue.")

        target.parent.mkdir(parents=True, exist_ok=True)
        logger.debug("Downloading s3://%s/%s to %s", self.bucket_name, key, target)
        self.bucket.download_file(key, str(target))

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
        for obj in self.bucket.objects.filter(Prefix=self.subfolder):
            if obj.key.endswith("/"):  # "Folder" placeholder objects
                continue
            local_filename = local_path_for(download_dir, obj.key[len(self.subfolder) :])
            if local_filename is None:
                logger.warning(
                    "Skipping s3://%s/%s: its key points outside the download folder.", self.bucket_name, obj.key
                )
                continue
            local_filename.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Downloading remote file s3://%s/%s to %s", self.bucket_name, obj.key, local_filename)
            self.bucket.download_file(obj.key, str(local_filename))

    def delete_file(self, filename: str, fail_silently: bool = False) -> None:
        """Delete a file from the current subfolder.

        Raises ``ValueError`` if it doesn't exist, unless ``fail_silently`` is True.
        """
        key = self.subfolder + filename
        logger.debug("key: %s", key)

        if self._key_exists(key):
            self.s3.Object(self.bucket_name, key).delete()
        elif not fail_silently:
            logger.error("File %s does not exist in path %s", filename, self.uri)
            raise ValueError(f"File {filename} does not exist in path {self.uri}")

    def delete_subfolder(self) -> None:
        """Delete every key under the current subfolder (recursively), then reset the subfolder.

        Raises ``ValueError`` when no subfolder is set, to avoid emptying the bucket by accident.
        """
        self._require_subfolder("delete")
        self.bucket.objects.filter(Prefix=self.subfolder).delete()
        self.subfolder = ""
