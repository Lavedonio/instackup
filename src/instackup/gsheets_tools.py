"""Google Sheets tool, built on gspread."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from ._google import resolve_google_auth
from ._utils import missing_extra_message

try:
    import google.auth
    import gspread
    from gspread.exceptions import WorksheetNotFound
except ImportError as exc:  # pragma: no cover - depends on installed extras
    raise ImportError(missing_extra_message("gsheets")) from exc

logger = logging.getLogger(__name__)

SPREADSHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
DEFAULT_SCOPES = (SPREADSHEETS_SCOPE, DRIVE_SCOPE)
WRITE_MODES = ("APPEND", "EMPTY", "TRUNCATE")


class GSheetsTool:
    """Wraps gspread to ease the setup and handle most of the interaction needed with Google Sheets.

    ``auth_mode`` is one of:

    - 'secret_key' (default): the ``google.<connection>`` service account from the
      credential store (or ``credentials``); without one, Application Default Credentials;
    - 'default' (alias 'composer'): Application Default Credentials, e.g. on Cloud
      Composer, Cloud Run or GKE with Workload Identity;
    - 'oauth': gspread's interactive OAuth flow for end users.

    A ready ``gspread.Client`` can be passed as ``gspread_client`` instead.
    """

    def __init__(
        self,
        sheet_url: str | None = None,
        sheet_key: str | None = None,
        sheet_gid: int | str | None = None,
        auth_mode: str = "secret_key",
        connection: str = "default",
        read_only: bool = False,
        scopes: Sequence[str] = DEFAULT_SCOPES,
        *,
        credentials: Mapping[str, Any] | None = None,
        gspread_client: gspread.Client | None = None,
    ) -> None:
        scopes = list(scopes)
        if read_only:
            scopes = [f"{DRIVE_SCOPE}.readonly"] if DRIVE_SCOPE in scopes else []
            scopes.append(f"{SPREADSHEETS_SCOPE}.readonly")

        if gspread_client is None:
            gspread_client = _authorize(auth_mode.lower(), connection, credentials, scopes)

        self.gspread_client = gspread_client
        self.spreadsheet: gspread.Spreadsheet | None = None
        self.worksheet: gspread.Worksheet | None = None

        if sheet_url is not None:
            self.set_spreadsheet_by_url(sheet_url)
        elif sheet_key is not None:
            self.set_spreadsheet_by_key(sheet_key)
            if sheet_gid is not None:
                self.set_worksheet_by_id(sheet_gid)

    def set_spreadsheet_by_url(self, sheet_url: str) -> None:
        """Set the spreadsheet, and the worksheet if the URL has a ``#gid=``, from a spreadsheet URL."""
        url, _, fragment = sheet_url.partition("#gid=")
        gid = fragment.split("&", 1)[0]  # "Link to range" URLs continue with "&range=A1:B2"
        self.spreadsheet = self.gspread_client.open_by_url(url)
        self.worksheet = None
        if gid:
            self.set_worksheet_by_id(gid)

    def set_spreadsheet_by_key(self, sheet_key: str) -> None:
        """Set the spreadsheet from its key (the ID in its URL). Unsets the worksheet."""
        self.spreadsheet = self.gspread_client.open_by_key(sheet_key)
        self.worksheet = None

    def set_worksheet_by_id(self, sheet_gid: int | str) -> None:
        """Set the worksheet from its gid (the number after ``#gid=`` in its URL)."""
        if self.spreadsheet is None:
            raise ValueError("No spreadsheet set. Set it first before selecting a worksheet.")
        try:
            self.worksheet = self.spreadsheet.get_worksheet_by_id(int(sheet_gid))
        except WorksheetNotFound:
            raise ValueError(
                f"Worksheet ID (sheet_gid: {sheet_gid}) not found in {self.spreadsheet.title} "
                f"(sheet_key: {self.spreadsheet.id})"
            ) from None

    def _require_worksheet(self, action: str) -> gspread.Worksheet:
        if self.worksheet is None:
            raise ValueError(f"No worksheet set. Set it first before {action}.")
        return self.worksheet

    def download(self) -> pd.DataFrame:
        """The selected worksheet as a DataFrame, using its first row as the header."""
        return pd.DataFrame(self._require_worksheet("downloading").get_all_records())

    def upload(self, dataframe: pd.DataFrame, write_mode: str = "APPEND", force_upload: bool = False) -> None:
        """Write a DataFrame to the selected worksheet.

        ``write_mode`` is one of:

        - APPEND: adds the rows after the data already in the worksheet, leaving
          existing cells untouched;
        - EMPTY: writes only if the worksheet is empty or has just the header;
        - TRUNCATE: replaces any current data.

        When the worksheet has data, the DataFrame columns must match its header unless
        ``force_upload`` is True (with APPEND, rows are then added by position).
        Missing values (NaN/None) are written as empty cells and dates/times as text.
        """
        worksheet = self._require_worksheet("uploading")

        write_mode = write_mode.upper()
        if write_mode not in WRITE_MODES:
            raise ValueError("The write_mode parameter can only be set as 'APPEND', 'EMPTY' or 'TRUNCATE'.")

        values = _to_sheet_values(dataframe)
        if force_upload and write_mode == "TRUNCATE":
            _replace_contents(worksheet, values)
            return

        existing = worksheet.get_all_values()
        has_data = len(existing) > 1
        if has_data and not force_upload and _trim_row(existing[0]) != values[0]:
            raise ValueError(
                "New data columns and inplace data columns don't match. "
                "Set force_upload parameter to True to override this check."
            )

        if write_mode == "APPEND" and has_data:
            worksheet.append_rows(values[1:])
        elif write_mode == "EMPTY" and has_data:
            raise ValueError("Worksheet is not empty. Select other mode or verify the Worksheet.")
        else:
            _replace_contents(worksheet, values)


def _authorize(
    auth_mode: str, connection: str, credentials: Mapping[str, Any] | None, scopes: list[str]
) -> gspread.Client:
    if auth_mode == "secret_key":
        return gspread.authorize(resolve_google_auth(connection, credentials, scopes=scopes).credentials)
    if auth_mode in ("default", "composer"):
        google_credentials, _ = google.auth.default(scopes=scopes)
        return gspread.authorize(google_credentials)
    if auth_mode == "oauth":
        return gspread.oauth(scopes=scopes)
    raise ValueError("Authentication mode not recognized. Choose between 'secret_key', 'default' or 'oauth'.")


def _replace_contents(worksheet: gspread.Worksheet, values: list[list[Any]]) -> None:
    worksheet.clear()
    worksheet.update(values=values)


def _trim_row(row: list[str]) -> list[str]:
    """A worksheet row without the empty cells that pad it to the sheet's width."""
    while row and row[-1] == "":
        row = row[:-1]
    return row


def _to_sheet_values(dataframe: pd.DataFrame) -> list[list[Any]]:
    """Header plus rows, with every cell converted to a JSON-serializable value."""
    rows = [[_to_cell(value) for value in row] for row in dataframe.astype(object).itertuples(index=False, name=None)]
    return [[str(column) for column in dataframe.columns], *rows]


def _to_cell(value: Any) -> Any:
    if pd.api.types.is_scalar(value) and pd.isna(value):
        return ""  # NaN isn't valid JSON
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, (date, time, timedelta)):  # Includes pandas Timestamp and Timedelta
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value
