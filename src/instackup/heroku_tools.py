"""Heroku CLI wrapper."""

from __future__ import annotations

import logging
import shlex
import subprocess
from collections.abc import Sequence

logger = logging.getLogger(__name__)


class HerokuTool:
    """Encapsulates the interaction needed with the Heroku CLI.

    Commands are run without a shell, so arguments can't be used to inject other commands.
    """

    def __init__(self, heroku_path: str = "heroku", app: str | None = None, remote: str | None = None) -> None:
        try:
            p_test = subprocess.run([heroku_path, "--version"], capture_output=True, check=False)
        except OSError as e:
            raise OSError("Heroku CLI not installed or not able to be reached.") from e
        if p_test.returncode != 0:
            raise OSError("Heroku CLI not installed or not able to be reached.")

        self.heroku = heroku_path
        self.app = app
        self.remote = remote

    @property
    def app_flag(self) -> str:
        """The ``--app``/``--remote`` flag added to every command (``--app`` wins if both are set)."""
        if self.app:
            return "--app " + shlex.quote(self.app)
        if self.remote:
            return "--remote " + shlex.quote(self.remote)
        return ""

    def execute(self, cmd: str | Sequence[str]) -> subprocess.CompletedProcess[bytes]:
        """Run a Heroku CLI command, e.g. ``execute("ps")`` or ``execute(["config:get", "KEY"])``.

        Returns the ``CompletedProcess``; its ``stdout`` and ``stderr`` are bytes.
        """
        args = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
        command = [self.heroku, *args, *shlex.split(self.app_flag)]
        logger.debug("Running %s", command)
        return subprocess.run(command, capture_output=True, check=False)
