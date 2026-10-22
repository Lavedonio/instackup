from __future__ import annotations

import subprocess
from collections.abc import Sequence
from typing import Any
from unittest.mock import MagicMock

import pytest

from instackup import heroku_tools
from instackup.heroku_tools import HerokuTool


def completed(args: Sequence[str], returncode: int = 0, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(args, returncode, stdout=b"", stderr=b"")


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    run = MagicMock(side_effect=completed)
    monkeypatch.setattr(heroku_tools.subprocess, "run", run)
    return run


def assert_ran_without_shell(run: MagicMock, command: list[str]) -> None:
    args, kwargs = run.call_args
    assert args == (command,)
    assert not kwargs.get("shell", False)
    assert kwargs.get("capture_output") is True
    assert not kwargs.get("text", False)


def test_init_checks_the_cli_version(run: MagicMock) -> None:
    tool = HerokuTool("/opt/heroku/bin/heroku", app="my-app", remote="staging")

    run.assert_called_once()
    assert_ran_without_shell(run, ["/opt/heroku/bin/heroku", "--version"])
    assert (tool.heroku, tool.app, tool.remote) == ("/opt/heroku/bin/heroku", "my-app", "staging")


@pytest.mark.parametrize(
    "error", [FileNotFoundError(2, "No such file or directory"), PermissionError(13, "Permission denied")]
)
def test_init_with_unreachable_cli(run: MagicMock, error: OSError) -> None:
    run.side_effect = error

    with pytest.raises(OSError, match="Heroku CLI not installed or not able to be reached") as excinfo:
        HerokuTool()

    assert excinfo.value.__cause__ is error


def test_init_with_failing_cli(run: MagicMock) -> None:
    run.side_effect = lambda args, **kwargs: completed(args, returncode=127)

    with pytest.raises(OSError, match="Heroku CLI not installed or not able to be reached"):
        HerokuTool()


@pytest.mark.parametrize(
    ("app", "remote", "flag"),
    [
        ("my-app", None, "--app my-app"),
        (None, "staging", "--remote staging"),
        ("my-app", "staging", "--app my-app"),
        (None, None, ""),
        ("my app", None, "--app 'my app'"),
        (None, "x; rm -rf ~", "--remote 'x; rm -rf ~'"),
    ],
)
def test_app_flag(run: MagicMock, app: str | None, remote: str | None, flag: str) -> None:
    assert HerokuTool(app=app, remote=remote).app_flag == flag


@pytest.mark.parametrize(
    ("cmd", "args"),
    [
        ("ps", ["ps"]),
        ('config:set "GREETING=hello world"', ["config:set", "GREETING=hello world"]),
        ("ps && rm -rf ~", ["ps", "&&", "rm", "-rf", "~"]),
        (["config:get", "KEY"], ["config:get", "KEY"]),
        (("run", "echo $HOME; ls"), ["run", "echo $HOME; ls"]),
    ],
    ids=["simple", "quoted", "shell-operators", "list", "tuple"],
)
@pytest.mark.parametrize(
    ("app", "remote", "flag_args"),
    [("my app", "staging", ["--app", "my app"]), (None, "staging", ["--remote", "staging"]), (None, None, [])],
    ids=["app", "remote", "no-flag"],
)
def test_execute(
    run: MagicMock,
    cmd: str | Sequence[str],
    args: list[str],
    app: str | None,
    remote: str | None,
    flag_args: list[str],
) -> None:
    tool = HerokuTool(app=app, remote=remote)

    tool.execute(cmd)

    assert_ran_without_shell(run, ["heroku", *args, *flag_args])


def test_execute_returns_the_completed_process(run: MagicMock) -> None:
    tool = HerokuTool()
    result = subprocess.CompletedProcess(["heroku", "ps"], 1, stdout=b"web.1: up\n", stderr=b"warning\n")
    run.side_effect = None
    run.return_value = result

    assert tool.execute("ps") is result
