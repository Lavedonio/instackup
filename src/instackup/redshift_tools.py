"""Amazon Redshift tool, built on top of the PostgreSQL tool."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Self

from ._aws import BotoCoreError, ClientError, create_session
from .credentials import CredentialsNotFoundError, get_default_store
from .sql_tools import PostgreSQLTool, _connect_postgresql, _database_errors

logger = logging.getLogger(__name__)

CONNECTION_TYPES = ("cluster_credentials", "master_password")


class RedShiftTool(PostgreSQLTool):
    """Handles most of the interaction needed with Redshift.

    With ``connect_by_cluster=True`` (the default) a temporary password is requested
    from the Redshift API with ``GetClusterCredentials`` each time :meth:`connect`
    is called, using the AWS credentials of the same ``connection`` name if they're
    configured, otherwise the ``default`` AWS connection (and so, if that isn't
    configured either, the AWS default credential chain). Otherwise the configured
    user and password are used.

    Settings are read from ``redshift.<connection>.cluster_credentials`` or
    ``redshift.<connection>.master_password``; ``credentials`` may hold either that
    nested structure or the flat settings directly. An ``iam_role`` setting is used to
    authorize :meth:`unload_to_S3`.
    """

    def __init__(
        self,
        connection: str = "default",
        connect_by_cluster: bool = True,
        *,
        credentials: Mapping[str, Any] | None = None,
        session: Any = None,
        iam_role: str | None = None,
    ) -> None:
        # Approach based on https://stackoverflow.com/questions/44243169/connect-to-redshift-using-python-using-iam-role
        connection_type = CONNECTION_TYPES[0] if connect_by_cluster else CONNECTION_TYPES[1]
        logger.debug("connection_type = %s", connection_type)

        settings = (
            dict(credentials)
            if credentials is not None
            else get_default_store().get("redshift", connection, required=True) or {}
        )
        redshift_creds: dict[str, Any] = settings.get(connection_type, settings)
        if not isinstance(redshift_creds, dict) or "host" not in redshift_creds:
            raise CredentialsNotFoundError(
                f"Redshift connection {connection!r} has no {connection_type!r} settings with a 'host'."
            )

        self.sql_type = "RedShift"
        self.filename = None  # Unused; kept for compatibility with the parent class
        self.connection_parameters = redshift_creds
        self.connection: Any = None
        self.cursor: Any = None

        self.dbname = redshift_creds["dbname"]
        self.user = redshift_creds["user"]
        self.password = redshift_creds.get("password")
        self.cluster_id = redshift_creds.get("cluster_id")
        self.host = redshift_creds["host"]
        self.port = redshift_creds.get("port", 5439)
        self.connect_by_cluster = connect_by_cluster
        self.iam_role = iam_role or settings.get("iam_role")
        self.cluster_creds: dict[str, Any] | None = None

        self._aws_connection = connection
        self._session = session

    @property
    def session(self) -> Any:
        """The boto3 session used for the Redshift API and UNLOAD credentials, created on first use."""
        if self._session is None:
            aws_connection = self._aws_connection
            if get_default_store().get("aws", aws_connection) is None:
                aws_connection = "default"  # A Redshift connection name needn't have its own AWS identity
            self._session = create_session(aws_connection)
        return self._session

    def connect(self, fail_silently: bool = False) -> Self | None:
        """Open the connection.

        If ``fail_silently`` is True, errors are logged instead of raised and ``None`` is returned.
        """
        try:
            if self.connect_by_cluster:
                logger.debug("Getting cluster credentials...")
                self.cluster_creds = self.session.client("redshift").get_cluster_credentials(
                    DbUser=self.user,
                    DbName=self.dbname,
                    ClusterIdentifier=self.cluster_id,
                    AutoCreate=False,
                )
                user, password = self.cluster_creds["DbUser"], self.cluster_creds["DbPassword"]
            else:
                logger.debug("Connecting by MasterUser and password...")
                user, password = self.user, self.password

            conn = _connect_postgresql(
                {"host": self.host, "port": self.port, "user": user, "password": password, "dbname": self.dbname}
            )
        except (*_database_errors(), BotoCoreError, ClientError) as e:
            logger.exception("Failed to open database connection.")
            if not fail_silently:
                raise e
            logger.error("ATTENTION: Failing Silently")
            return None

        logger.info("Connected!")
        self.connection = conn
        self.cursor = conn.cursor()
        return self

    def unload_to_S3(
        self,
        redshift_query: str,
        s3_path: str,
        filename: str,
        unload_options: str = "MANIFEST GZIP ALLOWOVERWRITE REGION 'us-east-2'",
        *,
        iam_role: str | None = None,
    ) -> None:
        """Run an UNLOAD command to copy the results of ``redshift_query`` to S3.

        Files are written to ``<s3_path>/<filename>_*``. The command is authorized
        with an IAM role (the ``iam_role`` argument or setting), which is recommended;
        otherwise the session's AWS credentials are embedded in the command.

        Unload options: https://docs.aws.amazon.com/redshift/latest/dg/r_UNLOAD.html
        """
        unload_query = f"""
            UNLOAD ($$ {redshift_query} $$)
            TO '{s3_path.rstrip("/")}/{filename}_'
            {self._unload_authorization(iam_role)}
            {unload_options};
        """

        logger.debug("Unloading query to %s", s3_path)
        # Never log this statement: it may contain AWS secret keys.
        self._run(unload_query, None, fail_silently=False, error_message="Error running UNLOAD!", log_sql=False)

    def _unload_authorization(self, iam_role: str | None) -> str:
        role = iam_role or self.iam_role
        if role:
            return f"IAM_ROLE '{role}'"

        aws_credentials = self.session.get_credentials()
        if aws_credentials is None:
            raise CredentialsNotFoundError("UNLOAD needs either an IAM role or AWS credentials, and none were found.")
        frozen = aws_credentials.get_frozen_credentials()
        auth_args = [f"aws_access_key_id={frozen.access_key}", f"aws_secret_access_key={frozen.secret_key}"]
        if frozen.token:
            auth_args.append(f"token={frozen.token}")
        return f"WITH CREDENTIALS '{';'.join(auth_args)}'"
