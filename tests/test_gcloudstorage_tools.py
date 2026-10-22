from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, create_autospec, sentinel

import pandas as pd
import pytest
from google.cloud import storage

from instackup import gcloudstorage_tools
from instackup._google import GoogleAuth
from instackup.gcloudstorage_tools import GCloudStorageTool, split_gcs_uri

BUCKET = "my-bucket"
CONTENT = b"id,name\n1,a\n2,b\n"
DATAFRAME = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})


def fake_blob(name: str, content: bytes = b"") -> MagicMock:
    """A Blob double whose downloads return or write ``content``."""
    blob = create_autospec(storage.Blob, instance=True)
    blob.name = name
    blob.exists.return_value = False
    blob.download_as_bytes.return_value = content
    blob.download_to_filename.side_effect = lambda filename: Path(filename).write_bytes(content)
    return blob


def stored_blob(name: str, **resource: Any) -> storage.Blob:
    """A real Blob carrying the metadata resource the GCS API returns for it."""
    blob = storage.Blob(name, bucket=storage.Bucket(None, name=BUCKET))
    blob._set_properties({"name": name, "bucket": BUCKET, **resource})
    return blob


def stored_bucket(name: str, **resource: Any) -> storage.Bucket:
    bucket = storage.Bucket(None, name=name)
    bucket._set_properties({"name": name, **resource})
    return bucket


def local_files(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def blobs() -> dict[str, MagicMock]:
    """Blob doubles handed out by the fake bucket, by name; pre-populate to set their content."""
    return {}


@pytest.fixture
def client(blobs: dict[str, MagicMock]) -> MagicMock:
    client = create_autospec(storage.Client, instance=True)
    bucket = create_autospec(storage.Bucket, instance=True)
    bucket.name = BUCKET
    bucket.blob.side_effect = lambda name: blobs.setdefault(name, fake_blob(name))
    client.bucket.return_value = bucket
    return client


@pytest.fixture
def bucket(client: MagicMock) -> MagicMock:
    return client.bucket.return_value


@pytest.fixture
def tool(client: MagicMock) -> GCloudStorageTool:
    return GCloudStorageTool(bucket=BUCKET, client=client)


@pytest.fixture
def file_tool(client: MagicMock, blobs: dict[str, MagicMock]) -> GCloudStorageTool:
    """A tool with ``gs://my-bucket/folder/file.csv`` (holding CONTENT) selected."""
    blobs["folder/file.csv"] = fake_blob("folder/file.csv", CONTENT)
    return GCloudStorageTool(uri=f"gs://{BUCKET}/folder/file.csv", client=client)


# -- split_gcs_uri -------------------------------------------------------------


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("gs://my-bucket", ("my-bucket", "", None)),
        ("gs://my-bucket/", ("my-bucket", "", None)),
        ("gs://my-bucket/folder/", ("my-bucket", "folder/", None)),
        ("gs://my-bucket/folder/nested/", ("my-bucket", "folder/nested/", None)),
        ("gs://my-bucket/file.csv", ("my-bucket", "", "file.csv")),
        ("gs://my-bucket/folder/nested/file.csv", ("my-bucket", "folder/nested/", "file.csv")),
    ],
)
def test_split_gcs_uri(uri: str, expected: tuple[str, str, str | None]) -> None:
    assert split_gcs_uri(uri) == expected


@pytest.mark.parametrize("uri", ["s3://my-bucket/file.csv", "my-bucket/file.csv", "gs://"])
def test_split_gcs_uri_rejects_other_uris(uri: str) -> None:
    with pytest.raises(ValueError, match="Invalid service type"):
        split_gcs_uri(uri)


# -- Construction --------------------------------------------------------------


def test_init_from_uri_takes_priority_over_subfolder_and_filename(client: MagicMock) -> None:
    tool = GCloudStorageTool(
        uri="gs://my-bucket/folder/file.csv", subfolder="ignored", filename="ignored.csv", client=client
    )

    assert (tool.bucket_name, tool.subfolder, tool.filename) == (BUCKET, "folder/", "file.csv")
    assert tool.client is client
    assert tool.project is None


def test_init_from_bucket_normalizes_subfolder(client: MagicMock) -> None:
    tool = GCloudStorageTool(bucket=BUCKET, subfolder="folder/nested", filename="file.csv", client=client)

    assert (tool.bucket_name, tool.subfolder, tool.filename) == (BUCKET, "folder/nested/", "file.csv")
    assert tool.uri == "gs://my-bucket/folder/nested/file.csv"


def test_init_rejects_both_uri_and_bucket(client: MagicMock) -> None:
    with pytest.raises(ValueError, match="either bucket name or full Google Cloud Storage path"):
        GCloudStorageTool(uri="gs://my-bucket/", bucket=BUCKET, client=client)


@pytest.mark.parametrize("authenticate", [True, False])
def test_init_builds_client_from_resolved_google_auth(monkeypatch: pytest.MonkeyPatch, authenticate: bool) -> None:
    project_info = {"id": "my-project", "name": "My Project", "number": "42"}
    auth = GoogleAuth(credentials=sentinel.credentials, project_id="my-project", project_info=project_info)
    resolve_calls = []

    def fake_resolve(connection="default", credentials=None, *, scopes=None, use_config=True):
        resolve_calls.append((connection, credentials, use_config))
        return auth

    client_cls = MagicMock()
    monkeypatch.setattr(gcloudstorage_tools, "resolve_google_auth", fake_resolve)
    monkeypatch.setattr(gcloudstorage_tools.storage, "Client", client_cls)

    tool = GCloudStorageTool(
        uri="gs://my-bucket/", connection="analytics", authenticate=authenticate, credentials={"project_id": "x"}
    )

    assert resolve_calls == [("analytics", {"project_id": "x"}, authenticate)]
    client_cls.assert_called_once_with(project="my-project", credentials=sentinel.credentials)
    assert tool.client is client_cls.return_value
    assert tool.project == project_info


# -- Location properties -------------------------------------------------------


def test_bucket_property_is_a_local_reference(tool: GCloudStorageTool, client: MagicMock) -> None:
    assert tool.bucket is client.bucket.return_value
    client.bucket.assert_called_once_with(BUCKET)
    client.get_bucket.assert_not_called()


@pytest.mark.parametrize(
    "switch",
    [lambda tool: tool.set_bucket("other-bucket"), lambda tool: setattr(tool, "bucket", "other-bucket")],
    ids=["set_bucket", "setter"],
)
def test_switching_bucket_resets_location(file_tool: GCloudStorageTool, switch: Any) -> None:
    switch(file_tool)

    assert (file_tool.bucket_name, file_tool.subfolder, file_tool.filename) == ("other-bucket", "", None)
    assert file_tool.uri == "gs://other-bucket/"


def test_blob_is_none_without_selected_file(tool: GCloudStorageTool) -> None:
    assert tool.blob is None


def test_blob_points_to_selected_file(file_tool: GCloudStorageTool, client: MagicMock) -> None:
    assert file_tool.blob.name == "folder/file.csv"
    client.bucket.assert_called_with(BUCKET)


@pytest.mark.parametrize(
    ("blob_name", "subfolder", "filename"),
    [("file.csv", "", "file.csv"), ("folder/nested/file.csv", "folder/nested/", "file.csv")],
)
def test_blob_setter_selects_subfolder_and_file(
    tool: GCloudStorageTool, blob_name: str, subfolder: str, filename: str
) -> None:
    tool.blob = blob_name

    assert (tool.subfolder, tool.filename) == (subfolder, filename)
    assert tool.uri == f"gs://my-bucket/{blob_name}"


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("gs://other-bucket/", ("other-bucket", "", None)),
        ("gs://other-bucket/folder/", ("other-bucket", "folder/", None)),
        ("gs://other-bucket/folder/file.csv", ("other-bucket", "folder/", "file.csv")),
    ],
)
def test_uri_setter(file_tool: GCloudStorageTool, uri: str, expected: tuple[str, str, str | None]) -> None:
    file_tool.uri = uri

    assert (file_tool.bucket_name, file_tool.subfolder, file_tool.filename) == expected
    assert file_tool.uri == uri


def test_set_subfolder_normalizes_and_resets_file(file_tool: GCloudStorageTool) -> None:
    file_tool.set_subfolder("other/nested")

    assert (file_tool.subfolder, file_tool.filename) == ("other/nested/", None)


def test_select_file_keeps_subfolder(tool: GCloudStorageTool) -> None:
    tool.set_subfolder("folder")
    tool.select_file("file.csv")

    assert tool.uri == "gs://my-bucket/folder/file.csv"


# -- Bucket and file info ------------------------------------------------------


def test_get_bucket_info_fetches_current_bucket(tool: GCloudStorageTool, client: MagicMock) -> None:
    client.get_bucket.return_value = stored_bucket(
        BUCKET,
        timeCreated="2026-01-02T03:04:05.000Z",
        updated="2026-02-03T04:05:06.000Z",
        owner={"entity": "project-owners-1", "entityId": "owner-id"},
    )

    assert tool.get_bucket_info() == {
        "Name": BUCKET,
        "TimeCreated": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        "TimeUpdated": datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC),
        "OwnerID": "owner-id",
    }
    client.get_bucket.assert_called_once_with(BUCKET)


def test_get_bucket_info_of_given_bucket(tool: GCloudStorageTool, client: MagicMock) -> None:
    info = tool.get_bucket_info(stored_bucket("other-bucket"))

    assert info == {"Name": "other-bucket", "TimeCreated": None, "TimeUpdated": None, "OwnerID": ""}
    client.get_bucket.assert_not_called()


def test_list_all_buckets(tool: GCloudStorageTool, client: MagicMock) -> None:
    client.list_buckets.return_value = iter([stored_bucket("a"), stored_bucket("b", owner={"entityId": "owner"})])

    infos = tool.list_all_buckets()

    assert [(info["Name"], info["OwnerID"]) for info in infos] == [("a", ""), ("b", "owner")]


def test_get_file_info_returns_metadata_of_selected_file(file_tool: GCloudStorageTool, bucket: MagicMock) -> None:
    bucket.get_blob.return_value = stored_blob(
        "folder/file.csv",
        contentType="text/csv",
        timeCreated="2026-01-02T03:04:05.000Z",
        updated="2026-02-03T04:05:06.000Z",
        size="15",
        md5Hash="bWQ1",
        crc32c="Y3Jj",
        owner={"entity": "user-1", "entityId": "owner-id"},
        customerEncryption={"encryptionAlgorithm": "AES256", "keySha256": "a2V5"},
    )

    assert file_tool.get_file_info() == {
        "Name": "folder/file.csv",
        "Bucket": BUCKET,
        "ContentType": "text/csv",
        "TimeCreated": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        "TimeUpdated": datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC),
        "TimeDeleted": None,
        "Size": 15,
        "MD5": "bWQ1",
        "OwnerID": "owner-id",
        "CRC32c": "Y3Jj",
        "EncryptionAlgorithm": "AES256",
        "EncryptionKeySHA256": "a2V5",
    }
    bucket.get_blob.assert_called_once_with("folder/file.csv")


@pytest.mark.parametrize(
    ("info", "expected"), [("Size", 5), ("OwnerID", ""), ("EncryptionAlgorithm", ""), ("TimeDeleted", None)]
)
def test_get_file_info_single_field_of_named_file(
    file_tool: GCloudStorageTool, bucket: MagicMock, info: str, expected: Any
) -> None:
    bucket.get_blob.return_value = stored_blob("folder/other.csv", size="5")

    assert file_tool.get_file_info("other.csv", info=info) == expected
    bucket.get_blob.assert_called_once_with("folder/other.csv")


def test_get_file_info_of_missing_file(file_tool: GCloudStorageTool, bucket: MagicMock) -> None:
    bucket.get_blob.return_value = None

    with pytest.raises(FileNotFoundError, match=re.escape("gs://my-bucket/folder/file.csv not found")):
        file_tool.get_file_info()


def test_get_file_info_requires_a_file(tool: GCloudStorageTool) -> None:
    with pytest.raises(ValueError, match="No file selected"):
        tool.get_file_info()


# -- Listing -------------------------------------------------------------------


def test_list_contents_skips_folder_placeholders(client: MagicMock) -> None:
    client.list_blobs.return_value = iter(
        [
            stored_blob("folder/"),
            stored_blob("folder/a.csv"),
            stored_blob("folder/nested/"),
            stored_blob("folder/nested/b.csv"),
        ]
    )
    tool = GCloudStorageTool(uri="gs://my-bucket/folder/", client=client)

    contents = tool.list_contents()

    assert isinstance(contents, list)
    assert [info["Name"] for info in contents] == ["folder/a.csv", "folder/nested/b.csv"]
    client.list_blobs.assert_called_once_with(BUCKET, prefix="folder/")


def test_list_contents_lazily(client: MagicMock) -> None:
    client.list_blobs.return_value = iter([stored_blob("folder/"), stored_blob("folder/a.csv")])
    tool = GCloudStorageTool(uri="gs://my-bucket/folder/", client=client)

    contents = tool.list_contents(yield_results=True)

    assert isinstance(contents, Iterator)
    client.list_blobs.assert_not_called()
    assert [info["Name"] for info in contents] == ["folder/a.csv"]


def test_list_contents_at_bucket_root(tool: GCloudStorageTool, client: MagicMock) -> None:
    client.list_blobs.return_value = iter([stored_blob("a.csv"), stored_blob("folder/b.csv")])

    assert [info["Name"] for info in tool.list_contents()] == ["a.csv", "folder/b.csv"]
    client.list_blobs.assert_called_once_with(BUCKET, prefix=None)


# -- Renaming ------------------------------------------------------------------


def test_rename_file(file_tool: GCloudStorageTool, bucket: MagicMock, blobs: dict[str, MagicMock]) -> None:
    file_tool.rename_file("renamed.csv")

    bucket.rename_blob.assert_called_once_with(blobs["folder/file.csv"], "folder/renamed.csv")
    assert file_tool.uri == "gs://my-bucket/folder/renamed.csv"


def test_rename_file_requires_a_file(tool: GCloudStorageTool, bucket: MagicMock) -> None:
    with pytest.raises(ValueError, match="No filename set"):
        tool.rename_file("renamed.csv")
    bucket.rename_blob.assert_not_called()


@pytest.mark.parametrize("new_subfolder", ["archive/old", "archive/old/"])
def test_rename_subfolder_moves_every_blob(client: MagicMock, bucket: MagicMock, new_subfolder: str) -> None:
    listed = [fake_blob("folder/"), fake_blob("folder/a.csv"), fake_blob("folder/nested/b.csv")]
    client.list_blobs.return_value = iter(listed)
    tool = GCloudStorageTool(uri="gs://my-bucket/folder/", client=client)

    tool.rename_subfolder(new_subfolder)

    client.list_blobs.assert_called_once_with(BUCKET, prefix="folder/")
    assert bucket.rename_blob.call_args_list == [
        call(listed[0], "archive/old/"),
        call(listed[1], "archive/old/a.csv"),
        call(listed[2], "archive/old/nested/b.csv"),
    ]
    assert tool.subfolder == "archive/old/"


def test_rename_subfolder_refuses_at_bucket_root(tool: GCloudStorageTool, client: MagicMock, bucket: MagicMock) -> None:
    with pytest.raises(ValueError, match="Refusing to rename every object in bucket 'my-bucket'"):
        tool.rename_subfolder("new")
    client.list_blobs.assert_not_called()
    bucket.rename_blob.assert_not_called()


# -- Uploads -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("selected", "expected_name"), [(None, "folder/local.csv"), ("remote.csv", "folder/remote.csv")]
)
def test_upload_file_to_current_location(
    client: MagicMock, blobs: dict[str, MagicMock], tmp_path: Path, selected: str | None, expected_name: str
) -> None:
    local = tmp_path / "local.csv"
    tool = GCloudStorageTool(bucket=BUCKET, subfolder="folder", filename=selected, client=client)

    tool.upload_file(str(local))

    assert list(blobs) == [expected_name]
    blobs[expected_name].upload_from_filename.assert_called_once_with(str(local))


@pytest.mark.parametrize("remote_path", ["gs://my-bucket/target/file.csv", "target/file.csv"])
def test_upload_file_to_given_remote_path(
    file_tool: GCloudStorageTool, blobs: dict[str, MagicMock], remote_path: str
) -> None:
    file_tool.upload_file("local.csv", remote_path)

    blobs["target/file.csv"].upload_from_filename.assert_called_once_with("local.csv")
    blobs["folder/file.csv"].upload_from_filename.assert_not_called()


def test_upload_file_ignores_bucket_of_a_different_uri(
    tool: GCloudStorageTool, client: MagicMock, blobs: dict[str, MagicMock], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="instackup.gcloudstorage_tools"):
        tool.upload_file("local.csv", "gs://other-bucket/target/file.csv")

    assert {c.args for c in client.bucket.call_args_list} == {(BUCKET,)}
    blobs["target/file.csv"].upload_from_filename.assert_called_once_with("local.csv")
    assert "different bucket" in caplog.text


@pytest.mark.parametrize("subfolder", ["", "sub/"])
@pytest.mark.parametrize("relative", [True, False], ids=["relative", "absolute"])
def test_upload_subfolder_keeps_local_structure(
    client: MagicMock,
    blobs: dict[str, MagicMock],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    subfolder: str,
    relative: bool,
) -> None:
    files = ["a.csv", "nested/b.csv", "nested/deeper/c.txt"]
    data = tmp_path / "data"
    (data / "empty").mkdir(parents=True)
    for name in files:
        (data / name).parent.mkdir(parents=True, exist_ok=True)
        (data / name).write_text(name)
    monkeypatch.chdir(tmp_path)
    tool = GCloudStorageTool(bucket=BUCKET, subfolder=subfolder, client=client)

    tool.upload_subfolder("data/" if relative else str(data))

    assert sorted(blobs) == [f"{subfolder}data/{name}" for name in files]
    for name in files:
        (local_path,) = blobs[f"{subfolder}data/{name}"].upload_from_filename.call_args.args
        assert Path(local_path).read_text() == name


@pytest.mark.parametrize(
    ("file_format", "kwargs", "expected_data", "content_type"),
    [
        ("CSV", {}, ",id,name\n0,1,a\n1,2,b\n", "text/csv"),
        ("csv", {"index": False, "sep": ";"}, "id;name\n1;a\n2;b\n", "text/csv"),
        ("JSON", {}, '{"id":{"0":1,"1":2},"name":{"0":"a","1":"b"}}', "application/json"),
        ("json", {"orient": "records"}, '[{"id":1,"name":"a"},{"id":2,"name":"b"}]', "application/json"),
    ],
)
def test_upload_from_dataframe(
    file_tool: GCloudStorageTool,
    blobs: dict[str, MagicMock],
    file_format: str,
    kwargs: dict[str, Any],
    expected_data: str,
    content_type: str,
) -> None:
    file_tool.upload_from_dataframe(DATAFRAME, file_format, **kwargs)

    blobs["folder/file.csv"].upload_from_string.assert_called_once_with(expected_data, content_type=content_type)


def test_upload_from_dataframe_csv_line_endings_dont_depend_on_the_os(
    file_tool: GCloudStorageTool, blobs: dict[str, MagicMock], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "linesep", "\r\n")  # As on Windows

    file_tool.upload_from_dataframe(DATAFRAME, index=False)

    blobs["folder/file.csv"].upload_from_string.assert_called_once_with("id,name\n1,a\n2,b\n", content_type="text/csv")


def test_upload_from_dataframe_to_named_file(file_tool: GCloudStorageTool, blobs: dict[str, MagicMock]) -> None:
    file_tool.upload_from_dataframe(DATAFRAME, filename="other.csv", index=False)

    blobs["folder/other.csv"].upload_from_string.assert_called_once_with("id,name\n1,a\n2,b\n", content_type="text/csv")
    blobs["folder/file.csv"].upload_from_string.assert_not_called()


def test_upload_from_dataframe_refuses_to_overwrite(file_tool: GCloudStorageTool, blobs: dict[str, MagicMock]) -> None:
    blobs["folder/file.csv"].exists.return_value = True

    with pytest.raises(FileExistsError, match="overwrite is set to False"):
        file_tool.upload_from_dataframe(DATAFRAME)
    blobs["folder/file.csv"].upload_from_string.assert_not_called()


def test_upload_from_dataframe_overwrites_when_asked(file_tool: GCloudStorageTool, blobs: dict[str, MagicMock]) -> None:
    blobs["folder/file.csv"].exists.return_value = True

    file_tool.upload_from_dataframe(DATAFRAME, overwrite=True)

    blobs["folder/file.csv"].upload_from_string.assert_called_once()


def test_upload_from_dataframe_rejects_unsupported_format(
    file_tool: GCloudStorageTool, blobs: dict[str, MagicMock]
) -> None:
    with pytest.raises(ValueError, match="File format PARQUET not supported"):
        file_tool.upload_from_dataframe(DATAFRAME, "parquet")
    blobs["folder/file.csv"].upload_from_string.assert_not_called()


def test_upload_from_dataframe_requires_a_file(tool: GCloudStorageTool) -> None:
    with pytest.raises(ValueError, match="No file selected"):
        tool.upload_from_dataframe(DATAFRAME)


# -- Downloads -----------------------------------------------------------------


def test_download_file_to_cwd(file_tool: GCloudStorageTool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    file_tool.download_file()

    assert local_files(tmp_path) == {"file.csv": CONTENT}


@pytest.mark.parametrize(
    ("download_to", "expected"),
    [("out/nested", "out/nested/file.csv"), ("out/nested/", "out/nested/file.csv"), ("out/file.csv", "out/file.csv")],
    ids=["directory", "directory-slash", "file-path"],
)
def test_download_file_to_given_location(
    file_tool: GCloudStorageTool, tmp_path: Path, download_to: str, expected: str
) -> None:
    file_tool.download_file(f"{tmp_path}/{download_to}")

    assert local_files(tmp_path) == {expected: CONTENT}


def test_download_file_by_name(file_tool: GCloudStorageTool, blobs: dict[str, MagicMock], tmp_path: Path) -> None:
    blobs["folder/other.csv"] = fake_blob("folder/other.csv", b"other")

    file_tool.download_file(str(tmp_path), remote_filename="other.csv")

    assert local_files(tmp_path) == {"other.csv": b"other"}


def test_download_file_refuses_to_replace_existing_file(
    file_tool: GCloudStorageTool, blobs: dict[str, MagicMock], tmp_path: Path
) -> None:
    (tmp_path / "file.csv").write_bytes(b"local")

    with pytest.raises(FileExistsError, match="File already exists"):
        file_tool.download_file(str(tmp_path))

    assert (tmp_path / "file.csv").read_bytes() == b"local"
    blobs["folder/file.csv"].download_to_filename.assert_not_called()


def test_download_file_replaces_existing_file_when_asked(file_tool: GCloudStorageTool, tmp_path: Path) -> None:
    (tmp_path / "file.csv").write_bytes(b"local")

    file_tool.download_file(str(tmp_path), replace=True)

    assert (tmp_path / "file.csv").read_bytes() == CONTENT


def test_download_file_requires_a_file(tool: GCloudStorageTool, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No file selected"):
        tool.download_file(str(tmp_path))


@pytest.mark.parametrize("download_to", [None, "downloads"])
def test_download_subfolder_recreates_remote_layout(
    client: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, download_to: str | None
) -> None:
    listed = [
        fake_blob("data/reports/"),
        fake_blob("data/reports/a.csv", b"a"),
        fake_blob("data/reports/2024/"),
        fake_blob("data/reports/2024/b.csv", b"b"),
    ]
    client.list_blobs.return_value = iter(listed)
    monkeypatch.chdir(tmp_path)
    tool = GCloudStorageTool(uri="gs://my-bucket/data/reports/", client=client)

    tool.download_subfolder(download_to)

    root = tmp_path / (download_to or "")
    assert local_files(root) == {"reports/a.csv": b"a", "reports/2024/b.csv": b"b"}
    client.list_blobs.assert_called_once_with(BUCKET, prefix="data/reports/")
    listed[0].download_to_filename.assert_not_called()
    listed[2].download_to_filename.assert_not_called()


def test_download_subfolder_at_bucket_root_uses_timestamped_dir(
    tool: GCloudStorageTool, client: MagicMock, tmp_path: Path
) -> None:
    client.list_blobs.return_value = iter(
        [fake_blob("a.csv", b"a"), fake_blob("folder/"), fake_blob("folder/b.csv", b"b")]
    )

    tool.download_subfolder(str(tmp_path))

    (download_dir,) = tmp_path.iterdir()
    assert download_dir.name.startswith(f"{BUCKET}_")
    assert local_files(download_dir) == {"a.csv": b"a", "folder/b.csv": b"b"}
    client.list_blobs.assert_called_once_with(BUCKET, prefix=None)


def test_download_subfolder_stays_inside_download_folder(
    client: MagicMock, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client.list_blobs.return_value = iter([fake_blob("data/../../escaped.csv", b"x"), fake_blob("data/ok.csv", b"ok")])
    tool = GCloudStorageTool(uri="gs://my-bucket/data/", client=client)

    tool.download_subfolder(str(tmp_path / "downloads"))

    assert not (tmp_path / "escaped.csv").exists()
    assert local_files(tmp_path / "downloads") == {"data/ok.csv": b"ok"}
    assert "outside the download folder" in caplog.text


@pytest.mark.parametrize("remote_path", ["gs://my-bucket/target/", "target/"])
def test_upload_file_to_a_folder_keeps_the_local_name(
    tool: GCloudStorageTool, blobs: dict[str, MagicMock], remote_path: str
) -> None:
    tool.upload_file("dir/local.csv", remote_path)
    blobs["target/local.csv"].upload_from_filename.assert_called_once_with("dir/local.csv")


def test_rename_subfolder_lists_before_renaming(client: MagicMock) -> None:
    listed = [fake_blob("data/a.csv", b"a")]

    def list_blobs(*args: object, **kwargs: object) -> Iterator[MagicMock]:
        yield from listed
        # A live listing could already include the renamed object under the same prefix.
        assert client.bucket.return_value.rename_blob.call_count == 0

    client.list_blobs.side_effect = list_blobs
    tool = GCloudStorageTool(uri="gs://my-bucket/data/", client=client)
    tool.rename_subfolder("data/archive")
    client.bucket.return_value.rename_blob.assert_called_once_with(listed[0], "data/archive/a.csv")


def test_download_on_dataframe(file_tool: GCloudStorageTool, blobs: dict[str, MagicMock]) -> None:
    blobs["folder/file.csv"].download_as_bytes.return_value = b"id;name\n1;a\n2;b\n"

    dataframe = file_tool.download_on_dataframe(sep=";")

    pd.testing.assert_frame_equal(dataframe, DATAFRAME)


def test_download_on_dataframe_requires_a_file(tool: GCloudStorageTool) -> None:
    with pytest.raises(ValueError, match="No file selected"):
        tool.download_on_dataframe()


@pytest.mark.parametrize(("encoding", "kwargs"), [("utf-8", {}), ("latin-1", {"encoding": "latin-1"})])
def test_download_as_string(
    file_tool: GCloudStorageTool, blobs: dict[str, MagicMock], encoding: str, kwargs: dict[str, str]
) -> None:
    blobs["folder/file.csv"].download_as_bytes.return_value = "olá".encode(encoding)
    blobs["folder/notes.txt"] = fake_blob("folder/notes.txt", "adeus".encode(encoding))

    assert file_tool.download_as_string(**kwargs) == "olá"
    assert file_tool.download_as_string("notes.txt", **kwargs) == "adeus"


# -- Deletion ------------------------------------------------------------------


def test_delete_file(file_tool: GCloudStorageTool, bucket: MagicMock) -> None:
    file_tool.delete_file()

    bucket.delete_blob.assert_called_once_with("folder/file.csv")
    assert file_tool.filename is None
    assert file_tool.uri == "gs://my-bucket/folder/"


def test_delete_file_requires_a_file(tool: GCloudStorageTool, bucket: MagicMock) -> None:
    with pytest.raises(ValueError, match="No filename set"):
        tool.delete_file()
    bucket.delete_blob.assert_not_called()


def test_delete_subfolder(file_tool: GCloudStorageTool, client: MagicMock, bucket: MagicMock) -> None:
    listed = [fake_blob("folder/"), fake_blob("folder/file.csv"), fake_blob("folder/nested/b.csv")]
    client.list_blobs.return_value = iter(listed)

    file_tool.delete_subfolder()

    client.list_blobs.assert_called_once_with(BUCKET, prefix="folder/")
    bucket.delete_blobs.assert_called_once_with(listed)
    assert (file_tool.subfolder, file_tool.filename) == ("", None)


def test_delete_subfolder_refuses_at_bucket_root(tool: GCloudStorageTool, client: MagicMock, bucket: MagicMock) -> None:
    with pytest.raises(ValueError, match="Refusing to delete every object in bucket 'my-bucket'"):
        tool.delete_subfolder()
    client.list_blobs.assert_not_called()
    bucket.delete_blobs.assert_not_called()
