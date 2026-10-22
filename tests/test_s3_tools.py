from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from instackup._aws import create_session
from instackup.credentials import CredentialsNotFoundError
from instackup.s3_tools import S3Tool

BUCKET = "test-bucket"


@pytest.fixture
def s3(aws_test_credentials: None) -> Iterator[S3Tool]:
    with mock_aws():
        boto3.client("s3").create_bucket(Bucket=BUCKET)
        yield S3Tool(bucket=BUCKET)


def put(tool: S3Tool, *keys: str) -> None:
    for key in keys:
        tool.s3.Object(BUCKET, key).put(Body=f"content of {key}".encode())


def keys(tool: S3Tool) -> list[str]:
    return sorted(obj.key for obj in tool.s3.Bucket(BUCKET).objects.all())


# -- Sessions --------------------------------------------------------------------------


def test_session_from_store_credentials(use_credentials) -> None:
    use_credentials(
        {"AWS": {"default": {"access_key": "AKIA", "secret_key": "s", "session_token": "t", "region": "sa-east-1"}}}
    )
    session = create_session()
    frozen = session.get_credentials().get_frozen_credentials()
    assert (frozen.access_key, frozen.secret_key, frozen.token) == ("AKIA", "s", "t")
    assert session.region_name == "sa-east-1"


def test_session_falls_back_to_default_chain(aws_test_credentials: None) -> None:
    assert create_session().get_credentials().access_key == "testing"


def test_session_named_connection_must_exist(use_credentials) -> None:
    use_credentials({"aws": {"default": {}}})
    with pytest.raises(CredentialsNotFoundError, match="'prod'"):
        create_session("prod")


def test_session_explicit_credentials() -> None:
    session = create_session("anything", {"aws_access_key_id": "A", "aws_secret_access_key": "B"})
    assert session.get_credentials().access_key == "A"


# -- Location handling ----------------------------------------------------------------------


def test_init_with_uri(aws_test_credentials: None) -> None:
    tool = S3Tool(uri="s3://bucket/folder/sub")
    assert (tool.bucket_name, tool.subfolder, tool.uri) == ("bucket", "folder/sub/", "s3://bucket/folder/sub/")


def test_init_rejects_bucket_and_uri(aws_test_credentials: None) -> None:
    with pytest.raises(ValueError, match="either bucket name or an URI"):
        S3Tool(uri="s3://bucket", bucket="bucket")


def test_init_with_session_and_subfolder() -> None:
    tool = S3Tool(bucket="b", subfolder="data", session=boto3.Session(aws_access_key_id="x", aws_secret_access_key="y"))
    assert tool.uri == "s3://b/data/"


def test_location_setters(s3: S3Tool) -> None:
    s3.set_subfolder("a/b")
    assert s3.subfolder == "a/b/"
    s3.bucket = "other"
    assert (s3.bucket_name, s3.subfolder) == ("other", "")
    s3.uri = "s3://third/x/"
    assert (s3.bucket_name, s3.subfolder) == ("third", "x/")
    assert s3.bucket.name == "third"


# -- Listing ------------------------------------------------------------------------------------


def test_list_all_buckets(s3: S3Tool) -> None:
    assert s3.list_all_buckets() == [BUCKET]


def test_list_contents(s3: S3Tool) -> None:
    put(s3, "root.csv", "data/", "data/a.csv", "data/nested/b.csv")
    assert sorted(s3.list_contents()) == ["data/", "data/a.csv", "data/nested/b.csv", "root.csv"]

    s3.set_subfolder("data")
    assert s3.list_contents() == ["data/a.csv"]
    contents = s3.list_contents(yield_results=True)
    assert not isinstance(contents, list)
    assert list(contents) == ["data/a.csv"]


# -- Uploads ----------------------------------------------------------------------------------------


def test_upload_file_destinations(s3: S3Tool, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    local = tmp_path / "local.csv"
    local.write_text("x")
    s3.set_subfolder("in")

    s3.upload_file(str(local))
    s3.upload_file(str(local), "explicit/key.csv")
    s3.upload_file(str(local), f"s3://{BUCKET}/from/uri.csv")
    s3.upload_file(str(local), "s3://other-bucket/other.csv")

    assert keys(s3) == ["explicit/key.csv", "from/uri.csv", "in/local.csv", "other.csv"]
    assert "different bucket" in caplog.text


def test_upload_file_to_a_folder_keeps_the_local_name(s3: S3Tool, tmp_path: Path) -> None:
    local = tmp_path / "local.csv"
    local.write_text("x")

    s3.upload_file(str(local), "plain/")
    s3.upload_file(str(local), f"s3://{BUCKET}/uri/")

    assert keys(s3) == ["plain/local.csv", "uri/local.csv"]


def test_upload_subfolder(s3: S3Tool, tmp_path: Path) -> None:
    folder = tmp_path / "reports"
    (folder / "2026" / "q1").mkdir(parents=True)
    (folder / "summary.csv").write_text("s")
    (folder / "2026" / "q1" / "detail.csv").write_text("d")

    s3.set_subfolder("uploads")
    s3.upload_subfolder(str(folder))

    assert keys(s3) == ["uploads/reports/2026/q1/detail.csv", "uploads/reports/summary.csv"]


# -- Downloads -----------------------------------------------------------------------------------------


def test_download_file_default_location(s3: S3Tool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    put(s3, "data/a.csv")
    s3.set_subfolder("data")

    s3.download_file("data/a.csv")

    assert (tmp_path / "data" / "a.csv").read_text() == "content of data/a.csv"


def test_download_file_to_path_and_replace(s3: S3Tool, tmp_path: Path) -> None:
    put(s3, "a.csv")
    target = tmp_path / "out" / "renamed.csv"

    s3.download_file(f"s3://{BUCKET}/a.csv", str(target))
    assert target.read_text() == "content of a.csv"

    with pytest.raises(FileExistsError):
        s3.download_file("a.csv", str(target))
    target.write_text("old")
    s3.download_file("a.csv", str(target), replace=True)
    assert target.read_text() == "content of a.csv"


def test_download_subfolder(s3: S3Tool, tmp_path: Path) -> None:
    put(s3, "data/", "data/a.csv", "data/nested/b.csv", "other/c.csv")
    s3.set_subfolder("data")

    s3.download_subfolder(str(tmp_path))

    downloaded = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file())
    assert downloaded == ["data/a.csv", "data/nested/b.csv"]


def test_download_subfolder_stays_inside_download_folder(
    s3: S3Tool, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    put(s3, "data/../../escaped.csv", "data/ok.csv")
    s3.set_subfolder("data")

    s3.download_subfolder(str(tmp_path / "downloads"))

    assert not (tmp_path / "escaped.csv").exists()
    assert (tmp_path / "downloads" / "data" / "ok.csv").exists()
    assert "outside the download folder" in caplog.text


def test_rename_subfolder_into_its_own_child(s3: S3Tool) -> None:
    put(s3, "data/a.csv", "data/b.csv")
    s3.set_subfolder("data")
    s3.rename_subfolder("data/archive")
    assert keys(s3) == ["data/archive/a.csv", "data/archive/b.csv"]


def test_download_whole_bucket(s3: S3Tool, tmp_path: Path) -> None:
    put(s3, "a.csv")
    s3.download_subfolder(str(tmp_path))
    (download_dir,) = tmp_path.iterdir()
    assert download_dir.name.startswith(f"{BUCKET}_")
    assert (download_dir / "a.csv").exists()


# -- Renames and deletes ------------------------------------------------------------------------------


def test_rename_file(s3: S3Tool) -> None:
    put(s3, "data/old name.csv")
    s3.set_subfolder("data")
    s3.rename_file("old name.csv", "new.csv")
    assert keys(s3) == ["data/new.csv"]

    with pytest.raises(ValueError, match="does not exist"):
        s3.rename_file("missing.csv", "x.csv")


def test_rename_subfolder(s3: S3Tool) -> None:
    put(s3, "data/", "data/a.csv", "data/nested/b.csv", "database.csv")
    s3.set_subfolder("data")
    s3.rename_subfolder("archive/2026")

    assert keys(s3) == ["archive/2026/", "archive/2026/a.csv", "archive/2026/nested/b.csv", "database.csv"]
    assert s3.subfolder == "archive/2026/"


def test_delete_file(s3: S3Tool) -> None:
    put(s3, "data/a.csv", "data/b.csv")
    s3.set_subfolder("data")
    s3.delete_file("a.csv")
    assert keys(s3) == ["data/b.csv"]

    with pytest.raises(ValueError, match="does not exist"):
        s3.delete_file("a.csv")
    s3.delete_file("a.csv", fail_silently=True)


def test_delete_subfolder(s3: S3Tool) -> None:
    put(s3, "data/", "data/a.csv", "data/nested/b.csv", "database.csv")
    s3.set_subfolder("data")
    s3.delete_subfolder()
    assert keys(s3) == ["database.csv"]
    assert s3.subfolder == ""


@pytest.mark.parametrize("operation", ["delete_subfolder", "rename_subfolder"])
def test_bucket_wide_operations_need_a_subfolder(s3: S3Tool, operation: str) -> None:
    put(s3, "a.csv")
    with pytest.raises(ValueError, match="No subfolder set"):
        getattr(s3, operation)(*(["new"] if operation == "rename_subfolder" else []))
    assert keys(s3) == ["a.csv"]
