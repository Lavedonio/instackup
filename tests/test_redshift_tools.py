from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock

import boto3
import psycopg2
import pytest
from moto import mock_aws

from instackup.credentials import CredentialsNotFoundError
from instackup.redshift_tools import RedShiftTool

CLUSTER = {"dbname": "dev", "user": "admin", "host": "cluster.example.com", "cluster_id": "my-cluster", "port": 5439}
MASTER = {"dbname": "dev", "user": "admin", "host": "cluster.example.com", "password": "pw", "port": 5439}


@pytest.fixture
def psycopg2_connect(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    connect = MagicMock()
    monkeypatch.setattr(psycopg2, "connect", connect)
    return connect


@pytest.fixture
def redshift_cluster(aws_test_credentials: None) -> Iterator[None]:
    with mock_aws():
        boto3.client("redshift").create_cluster(
            ClusterIdentifier="my-cluster",
            NodeType="dc2.large",
            MasterUsername="admin",
            MasterUserPassword="Password1",
        )
        yield


def executed_sql(connect: MagicMock) -> str:
    sql: str = connect.return_value.cursor.return_value.execute.call_args.args[0]
    return sql


def test_settings_from_store(use_credentials) -> None:
    use_credentials({"RedShift": {"default": {"cluster_credentials": CLUSTER, "iam_role": "arn:role"}}})
    tool = RedShiftTool()
    assert (tool.host, tool.cluster_id, tool.dbname, tool.port) == ("cluster.example.com", "my-cluster", "dev", 5439)
    assert tool.iam_role == "arn:role"
    assert tool.sql_type == "RedShift"


def test_flat_explicit_credentials() -> None:
    tool = RedShiftTool(connect_by_cluster=False, credentials=MASTER, iam_role="arn:explicit")
    assert (tool.user, tool.password, tool.iam_role) == ("admin", "pw", "arn:explicit")


def test_missing_settings(use_credentials) -> None:
    use_credentials({"redshift": {"default": {"cluster_credentials": CLUSTER}}})
    with pytest.raises(CredentialsNotFoundError, match="master_password"):
        RedShiftTool(connect_by_cluster=False)
    with pytest.raises(CredentialsNotFoundError):
        RedShiftTool(connection="other")


@pytest.mark.usefixtures("redshift_cluster")
def test_connect_with_cluster_credentials(psycopg2_connect: MagicMock) -> None:
    tool = RedShiftTool(credentials={"cluster_credentials": CLUSTER})
    assert tool.connect() is tool

    assert tool.cluster_creds is not None
    kwargs = psycopg2_connect.call_args.kwargs
    assert kwargs["user"] == tool.cluster_creds["DbUser"]
    assert kwargs["password"] == tool.cluster_creds["DbPassword"]
    assert (kwargs["host"], kwargs["port"], kwargs["dbname"]) == ("cluster.example.com", 5439, "dev")


def test_connect_with_master_password(psycopg2_connect: MagicMock) -> None:
    session = MagicMock()
    RedShiftTool(connect_by_cluster=False, credentials=MASTER, session=session).connect()

    psycopg2_connect.assert_called_once_with(
        None, host="cluster.example.com", port=5439, user="admin", password="pw", dbname="dev"
    )
    session.client.assert_not_called()


def test_connect_failures(aws_test_credentials: None, psycopg2_connect: MagicMock) -> None:
    with mock_aws():  # No cluster exists, so GetClusterCredentials fails
        tool = RedShiftTool(credentials={"cluster_credentials": CLUSTER})
        assert tool.connect(fail_silently=True) is None
        with pytest.raises(Exception, match="ClusterNotFound"):
            tool.connect()

    psycopg2_connect.side_effect = psycopg2.OperationalError("refused")
    with pytest.raises(psycopg2.OperationalError):
        RedShiftTool(connect_by_cluster=False, credentials=MASTER).connect()


def test_unload_with_iam_role(psycopg2_connect: MagicMock) -> None:
    tool = RedShiftTool(connect_by_cluster=False, credentials={"master_password": MASTER, "iam_role": "arn:role"})
    with tool:
        tool.unload_to_S3("SELECT * FROM t", "s3://bucket/path/", "export")

    sql = executed_sql(psycopg2_connect)
    assert "UNLOAD ($$ SELECT * FROM t $$)" in sql
    assert "TO 's3://bucket/path/export_'" in sql
    assert "IAM_ROLE 'arn:role'" in sql
    assert "MANIFEST GZIP ALLOWOVERWRITE" in sql


def test_unload_with_session_keys_is_not_logged(psycopg2_connect: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
    session = boto3.Session(aws_access_key_id="AKIA", aws_secret_access_key="SECRET", aws_session_token="TOKEN")
    tool = RedShiftTool(connect_by_cluster=False, credentials=MASTER, session=session)
    caplog.set_level(logging.DEBUG)
    with tool:
        tool.unload_to_S3("SELECT 1", "s3://bucket", "f", unload_options="CSV")

    sql = executed_sql(psycopg2_connect)
    assert "WITH CREDENTIALS 'aws_access_key_id=AKIA;aws_secret_access_key=SECRET;token=TOKEN'" in sql
    assert "SECRET" not in caplog.text


def test_unload_explicit_role_wins(psycopg2_connect: MagicMock) -> None:
    tool = RedShiftTool(connect_by_cluster=False, credentials={"master_password": MASTER, "iam_role": "arn:config"})
    with tool:
        tool.unload_to_S3("SELECT 1", "s3://b", "f", iam_role="arn:call")
    assert "IAM_ROLE 'arn:call'" in executed_sql(psycopg2_connect)


def test_unload_without_any_aws_credentials(psycopg2_connect: MagicMock) -> None:
    session: Any = MagicMock()
    session.get_credentials.return_value = None
    tool = RedShiftTool(connect_by_cluster=False, credentials=MASTER, session=session)
    with tool, pytest.raises(CredentialsNotFoundError, match="IAM role"):
        tool.unload_to_S3("SELECT 1", "s3://b", "f")


def test_session_is_created_lazily_for_the_same_connection(use_credentials) -> None:
    use_credentials(
        {
            "redshift": {"etl": {"master_password": MASTER}},
            "aws": {"etl": {"access_key": "AKIA-ETL", "secret_key": "s"}},
        }
    )
    tool = RedShiftTool(connection="etl", connect_by_cluster=False)
    assert tool._session is None
    assert tool.session.get_credentials().access_key == "AKIA-ETL"


def test_named_connection_without_its_own_aws_settings_uses_the_default(use_credentials) -> None:
    use_credentials(
        {
            "redshift": {"analytics": {"master_password": MASTER}},
            "aws": {"default": {"access_key": "AKIA-DEFAULT", "secret_key": "s"}},
        }
    )
    tool = RedShiftTool(connection="analytics", connect_by_cluster=False)
    assert tool.session.get_credentials().access_key == "AKIA-DEFAULT"
