from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, call, sentinel

import numpy as np
import pandas as pd
import pytest
from gspread.exceptions import WorksheetNotFound

from instackup import gsheets_tools
from instackup._google import GoogleAuth
from instackup.gsheets_tools import DRIVE_SCOPE, SPREADSHEETS_SCOPE, GSheetsTool, _to_sheet_values

SHEET_KEY = "abc123"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_KEY}/edit"
DEFAULT_SCOPES = [SPREADSHEETS_SCOPE, DRIVE_SCOPE]


@pytest.fixture
def gspread_client() -> MagicMock:
    client = MagicMock(name="gspread.Client")
    for spreadsheet in (client.open_by_url.return_value, client.open_by_key.return_value):
        spreadsheet.title = "Budget"
        spreadsheet.id = SHEET_KEY
    return client


@pytest.fixture
def worksheet(gspread_client: MagicMock) -> MagicMock:
    sheet = gspread_client.open_by_key.return_value.get_worksheet_by_id.return_value
    sheet.get_all_records.return_value = []
    sheet.get_all_values.return_value = []
    return sheet


@pytest.fixture
def tool(gspread_client: MagicMock, worksheet: MagicMock) -> GSheetsTool:
    return GSheetsTool(sheet_key=SHEET_KEY, sheet_gid=0, gspread_client=gspread_client)


@pytest.fixture
def gspread_auth(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    fakes = SimpleNamespace(authorize=MagicMock(name="gspread.authorize"), oauth=MagicMock(name="gspread.oauth"))
    monkeypatch.setattr(gsheets_tools.gspread, "authorize", fakes.authorize)
    monkeypatch.setattr(gsheets_tools.gspread, "oauth", fakes.oauth)
    return fakes


# -- Authentication ----------------------------------------------------------------


def test_injected_client_skips_authentication(gspread_client: MagicMock, gspread_auth: SimpleNamespace) -> None:
    tool = GSheetsTool(gspread_client=gspread_client)

    assert tool.gspread_client is gspread_client
    assert (tool.spreadsheet, tool.worksheet) == (None, None)
    gspread_auth.authorize.assert_not_called()
    gspread_auth.oauth.assert_not_called()


@pytest.mark.parametrize("auth_mode", ["secret_key", "SECRET_KEY"])
def test_secret_key_auth_uses_resolved_google_credentials(
    monkeypatch: pytest.MonkeyPatch, gspread_auth: SimpleNamespace, auth_mode: str
) -> None:
    resolve = MagicMock(return_value=GoogleAuth(sentinel.service_account, "proj", None))
    monkeypatch.setattr(gsheets_tools, "resolve_google_auth", resolve)

    tool = GSheetsTool(auth_mode=auth_mode, connection="reports", credentials={"project_id": "proj"})

    resolve.assert_called_once_with("reports", {"project_id": "proj"}, scopes=DEFAULT_SCOPES)
    gspread_auth.authorize.assert_called_once_with(sentinel.service_account)
    assert tool.gspread_client is gspread_auth.authorize.return_value


@pytest.mark.parametrize("auth_mode", ["default", "composer", "Default"])
def test_default_auth_uses_application_default_credentials(
    monkeypatch: pytest.MonkeyPatch, gspread_auth: SimpleNamespace, auth_mode: str
) -> None:
    adc = MagicMock(return_value=(sentinel.adc, "proj"))
    monkeypatch.setattr(gsheets_tools.google.auth, "default", adc)

    tool = GSheetsTool(auth_mode=auth_mode)

    adc.assert_called_once_with(scopes=DEFAULT_SCOPES)
    gspread_auth.authorize.assert_called_once_with(sentinel.adc)
    assert tool.gspread_client is gspread_auth.authorize.return_value


def test_oauth_auth(gspread_auth: SimpleNamespace) -> None:
    tool = GSheetsTool(auth_mode="OAuth")

    gspread_auth.oauth.assert_called_once_with(scopes=DEFAULT_SCOPES)
    assert tool.gspread_client is gspread_auth.oauth.return_value


def test_unknown_auth_mode() -> None:
    with pytest.raises(ValueError, match="Authentication mode not recognized"):
        GSheetsTool(auth_mode="api_key")


@pytest.mark.parametrize(
    ("read_only", "scopes", "expected"),
    [
        (False, (SPREADSHEETS_SCOPE,), [SPREADSHEETS_SCOPE]),
        (True, (SPREADSHEETS_SCOPE, DRIVE_SCOPE), [f"{DRIVE_SCOPE}.readonly", f"{SPREADSHEETS_SCOPE}.readonly"]),
        (True, (SPREADSHEETS_SCOPE,), [f"{SPREADSHEETS_SCOPE}.readonly"]),
    ],
)
def test_scopes(gspread_auth: SimpleNamespace, read_only: bool, scopes: tuple[str, ...], expected: list[str]) -> None:
    GSheetsTool(auth_mode="oauth", read_only=read_only, scopes=scopes)

    gspread_auth.oauth.assert_called_once_with(scopes=expected)


# -- Spreadsheet and worksheet selection -----------------------------------------------


def test_url_without_gid_selects_only_the_spreadsheet(gspread_client: MagicMock) -> None:
    tool = GSheetsTool(sheet_url=SHEET_URL, gspread_client=gspread_client)

    gspread_client.open_by_url.assert_called_once_with(SHEET_URL)
    assert tool.spreadsheet is gspread_client.open_by_url.return_value
    assert tool.worksheet is None


@pytest.mark.parametrize(
    "url_suffix",
    [
        "#gid=42",
        "?gid=42#gid=42",
        "#gid=42&range=A1:B2",
    ],
)
def test_url_with_gid_selects_the_worksheet(gspread_client: MagicMock, url_suffix: str) -> None:
    spreadsheet = gspread_client.open_by_url.return_value

    tool = GSheetsTool(sheet_url=SHEET_URL + url_suffix, gspread_client=gspread_client)

    gspread_client.open_by_url.assert_called_once_with(SHEET_URL + url_suffix.partition("#")[0])
    spreadsheet.get_worksheet_by_id.assert_called_once_with(42)
    assert tool.spreadsheet is spreadsheet
    assert tool.worksheet is spreadsheet.get_worksheet_by_id.return_value


@pytest.mark.parametrize("gid", [7, "7"])
def test_key_and_gid_select_the_worksheet(gspread_client: MagicMock, gid: int | str) -> None:
    spreadsheet = gspread_client.open_by_key.return_value

    tool = GSheetsTool(sheet_key=SHEET_KEY, sheet_gid=gid, gspread_client=gspread_client)

    gspread_client.open_by_key.assert_called_once_with(SHEET_KEY)
    spreadsheet.get_worksheet_by_id.assert_called_once_with(7)
    assert tool.spreadsheet is spreadsheet
    assert tool.worksheet is spreadsheet.get_worksheet_by_id.return_value


def test_key_without_gid_selects_only_the_spreadsheet(gspread_client: MagicMock) -> None:
    tool = GSheetsTool(sheet_key=SHEET_KEY, gspread_client=gspread_client)

    assert tool.spreadsheet is gspread_client.open_by_key.return_value
    assert tool.worksheet is None


@pytest.mark.parametrize("kwargs", [{"sheet_key": SHEET_KEY, "sheet_gid": 9}, {"sheet_url": f"{SHEET_URL}#gid=9"}])
def test_unknown_gid_raises_value_error(gspread_client: MagicMock, kwargs: dict[str, object]) -> None:
    for spreadsheet in (gspread_client.open_by_url.return_value, gspread_client.open_by_key.return_value):
        spreadsheet.get_worksheet_by_id.side_effect = WorksheetNotFound("id 9 not found")

    with pytest.raises(ValueError, match=r"Worksheet ID \(sheet_gid: 9\) not found in Budget \(sheet_key: abc123\)"):
        GSheetsTool(gspread_client=gspread_client, **kwargs)


def test_set_worksheet_without_spreadsheet(gspread_client: MagicMock) -> None:
    tool = GSheetsTool(gspread_client=gspread_client)

    with pytest.raises(ValueError, match="No spreadsheet set"):
        tool.set_worksheet_by_id(0)


def test_set_spreadsheet_by_url_replaces_the_worksheet(tool: GSheetsTool, gspread_client: MagicMock) -> None:
    tool.set_spreadsheet_by_url(SHEET_URL)

    assert tool.spreadsheet is gspread_client.open_by_url.return_value
    assert tool.worksheet is None


# -- Download ---------------------------------------------------------------------------


def test_download(tool: GSheetsTool, worksheet: MagicMock) -> None:
    worksheet.get_all_records.return_value = [{"name": "Ann", "age": 30}, {"name": "Bob", "age": 25}]

    pd.testing.assert_frame_equal(tool.download(), pd.DataFrame({"name": ["Ann", "Bob"], "age": [30, 25]}))


@pytest.mark.parametrize(("method", "args"), [("download", ()), ("upload", (pd.DataFrame({"a": [1]}),))])
def test_without_worksheet(gspread_client: MagicMock, method: str, args: tuple[object, ...]) -> None:
    tool = GSheetsTool(sheet_key=SHEET_KEY, gspread_client=gspread_client)

    with pytest.raises(ValueError, match=f"No worksheet set. Set it first before {method}ing."):
        getattr(tool, method)(*args)


# -- Upload ------------------------------------------------------------------------------

CURRENT = [["name", "age"], ["Ann", "30"]]  # As returned by get_all_values()
NEW = pd.DataFrame({"name": ["Bob"], "age": [25]})


def test_set_spreadsheet_by_key_unsets_the_worksheet(tool: GSheetsTool) -> None:
    tool.set_spreadsheet_by_key("other")
    assert tool.worksheet is None


def test_upload_appends_rows_without_rewriting_existing_data(tool: GSheetsTool, worksheet: MagicMock) -> None:
    worksheet.get_all_values.return_value = CURRENT

    tool.upload(NEW)

    assert worksheet.method_calls == [call.get_all_values(), call.append_rows([["Bob", 25]])]


@pytest.mark.parametrize("current", [[], [["name", "age"]], [["something", "else"]]], ids=["empty", "header", "other"])
@pytest.mark.parametrize("write_mode", ["APPEND", "empty", "Truncate"])
def test_upload_into_worksheet_without_data(
    tool: GSheetsTool, worksheet: MagicMock, write_mode: str, current: list[list[str]]
) -> None:
    worksheet.get_all_values.return_value = current

    tool.upload(NEW, write_mode=write_mode)

    worksheet.clear.assert_called_once_with()
    worksheet.update.assert_called_once_with(values=[["name", "age"], ["Bob", 25]])
    worksheet.append_rows.assert_not_called()


def test_upload_truncate_replaces_current_data(tool: GSheetsTool, worksheet: MagicMock) -> None:
    worksheet.get_all_values.return_value = CURRENT

    tool.upload(NEW, write_mode="TRUNCATE")

    assert worksheet.method_calls == [
        call.get_all_values(),
        call.clear(),
        call.update(values=[["name", "age"], ["Bob", 25]]),
    ]


@pytest.mark.parametrize("force_upload", [False, True])
def test_upload_empty_mode_refuses_non_empty_worksheet(
    tool: GSheetsTool, worksheet: MagicMock, force_upload: bool
) -> None:
    worksheet.get_all_values.return_value = CURRENT

    with pytest.raises(ValueError, match="Worksheet is not empty"):
        tool.upload(NEW, write_mode="EMPTY", force_upload=force_upload)

    worksheet.clear.assert_not_called()
    worksheet.update.assert_not_called()


@pytest.mark.parametrize("write_mode", ["APPEND", "EMPTY", "TRUNCATE"])
def test_upload_refuses_mismatched_columns(tool: GSheetsTool, worksheet: MagicMock, write_mode: str) -> None:
    worksheet.get_all_values.return_value = [["age", "name"], ["30", "Ann"]]

    with pytest.raises(ValueError, match="New data columns and inplace data columns don't match"):
        tool.upload(NEW, write_mode=write_mode)

    assert worksheet.method_calls == [call.get_all_values()]


def test_upload_matches_header_ignoring_padding_and_label_types(tool: GSheetsTool, worksheet: MagicMock) -> None:
    worksheet.get_all_values.return_value = [["name", "2024", ""], ["Ann", "1", ""]]

    tool.upload(pd.DataFrame({"name": ["Bob"], 2024: [2]}))

    worksheet.append_rows.assert_called_once_with([["Bob", 2]])


def test_upload_force_append_with_mismatched_columns(tool: GSheetsTool, worksheet: MagicMock) -> None:
    worksheet.get_all_values.return_value = [["id"], ["1"]]

    tool.upload(NEW, write_mode="APPEND", force_upload=True)

    worksheet.append_rows.assert_called_once_with([["Bob", 25]])


def test_upload_force_truncate_skips_reading_the_worksheet(tool: GSheetsTool, worksheet: MagicMock) -> None:
    tool.upload(NEW, write_mode="TRUNCATE", force_upload=True)

    assert worksheet.method_calls == [call.clear(), call.update(values=[["name", "age"], ["Bob", 25]])]


def test_upload_rejects_unknown_write_mode(tool: GSheetsTool, worksheet: MagicMock) -> None:
    with pytest.raises(ValueError, match="The write_mode parameter can only be set as 'APPEND', 'EMPTY' or 'TRUNCATE'"):
        tool.upload(NEW, write_mode="MERGE")

    assert worksheet.method_calls == []


def test_upload_writes_missing_values_as_empty_cells_and_header_as_strings(
    tool: GSheetsTool, worksheet: MagicMock
) -> None:
    df = pd.DataFrame({"name": ["Ann", None], 2024: [1.5, np.nan]})

    tool.upload(df, write_mode="TRUNCATE", force_upload=True)

    worksheet.update.assert_called_once_with(values=[["name", "2024"], ["Ann", 1.5], ["", ""]])


def test_upload_sends_json_serializable_values(tool: GSheetsTool, worksheet: MagicMock) -> None:
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-31 10:30"]),
            "date": [date(2024, 1, 31)],
            "duration": pd.to_timedelta(["1h"]),
            "amount": [Decimal("1.25")],
        }
    )

    tool.upload(df, write_mode="TRUNCATE", force_upload=True)

    values = worksheet.update.call_args.kwargs["values"]
    assert values[1] == ["2024-01-31 10:30:00", "2024-01-31", "0 days 01:00:00", 1.25]
    json.dumps(values, allow_nan=False)


def test_to_sheet_values() -> None:
    df = pd.DataFrame(
        {
            "text": ["a", None, "c"],
            "float": [1.5, np.nan, 3.0],
            "nullable_int": pd.array([1, None, 3], dtype="Int64"),
            0: [True, False, None],
        }
    )

    values = _to_sheet_values(df)

    assert values == [
        ["text", "float", "nullable_int", "0"],
        ["a", 1.5, 1, True],
        ["", "", "", False],
        ["c", 3.0, 3, ""],
    ]
    json.dumps(values, allow_nan=False)
