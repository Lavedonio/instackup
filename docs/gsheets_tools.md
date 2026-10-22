# gsheets_tools
This is the documentation for the gsheets_tools module and all its contents, with usage examples.

This module needs the `gsheets` extra: `pip install 'instackup[gsheets]'`.

Credentials come from environment variables, a credentials file or the cloud platform identity (see [credentials.md](credentials.md)).

# Index
- [Global Variables](#global-variables)
- [GSheetsTool](#gsheetstool)
  - [\_\_init\_\_(self, sheet_url=None, sheet_key=None, sheet_gid=None, auth_mode="secret_key", connection="default", read_only=False, scopes=DEFAULT_SCOPES, \*, credentials=None, gspread_client=None)](#__init__self-sheet_urlnone-sheet_keynone-sheet_gidnone-auth_modesecret_key-connectiondefault-read_onlyfalse-scopesdefault_scopes--credentialsnone-gspread_clientnone)
  - [set_spreadsheet_by_url(self, sheet_url)](#set_spreadsheet_by_urlself-sheet_url)
  - [set_spreadsheet_by_key(self, sheet_key)](#set_spreadsheet_by_keyself-sheet_key)
  - [set_worksheet_by_id(self, sheet_gid)](#set_worksheet_by_idself-sheet_gid)
  - [download(self)](#downloadself)
  - [upload(self, dataframe, write_mode="APPEND", force_upload=False)](#uploadself-dataframe-write_modeappend-force_uploadfalse)

# Module Contents
## Global Variables
These are the global variables of this module:
- **SPREADSHEETS_SCOPE**: The Google Sheets scope, `https://www.googleapis.com/auth/spreadsheets`.
- **DRIVE_SCOPE**: The Google Drive scope, `https://www.googleapis.com/auth/drive`.
- **DEFAULT_SCOPES**: The default scopes used when connecting: `(SPREADSHEETS_SCOPE, DRIVE_SCOPE)`.
- **WRITE_MODES**: The write modes accepted by the upload method: `("APPEND", "EMPTY", "TRUNCATE")`.

## GSheetsTool
This class encapsulates the gspread module to ease the setup process and handle most of the interaction needed with Google Sheets, so the base code becomes more readable and straightforward.

### \_\_init\_\_(self, sheet_url=None, sheet_key=None, sheet_gid=None, auth_mode="secret_key", connection="default", read_only=False, scopes=DEFAULT_SCOPES, \*, credentials=None, gspread_client=None)
Initialization takes either the _sheet_url_ or the _sheet_key_ and _sheet_gid_ parameters to first reference the spreadsheet and worksheet. If _sheet_url_ is given, the worksheet comes from the `#gid=` part of the URL and _sheet_gid_ is ignored.

_auth_mode_ parameter can be 1 out of 3 types:
- secret_key (default): will use the service account of the `google` service settings of the _connection_ parameter in the credential store (or the ones given in the keyword-only _credentials_ parameter); without them, it falls back to Application Default Credentials;
- default (or its alias, composer): will use Application Default Credentials directly, e.g. when running in Google Cloud Composer, Cloud Run or GKE with Workload Identity;
- oauth: will use gspread's interactive OAuth flow for end users, which prompts a browser window requiring manual authentication (see the [gspread docs](https://docs.gspread.org/en/latest/oauth2.html#for-end-users-using-oauth-client-id)).

The _connection_ and _credentials_ parameters are only used with the secret_key mode. An unknown _auth_mode_ raises a `ValueError`.

_read_only_ parameter will convert the scopes to their read only versions. That means that the sheets can only be seen or downloaded, but not edited.

_scopes_ parameter sets the appropriate scopes to the environment when connecting. Sometimes only the spreadsheets authorization is necessary or can be given.

The keyword-only _gspread_client_ parameter takes a ready `gspread.Client`, used instead of authenticating.

Usage example:
```python
from instackup.gsheets_tools import GSheetsTool, SPREADSHEETS_SCOPE


sheet = GSheetsTool(sheet_url="https://docs.google.com/spreadsheets/d/0B7ciWr8lX8LTMVVyajlScU42OU0/edit#gid=214062020")

# or

sheet = GSheetsTool(sheet_key="0B7ciWr8lX8LTMVVyajlScU42OU0", sheet_gid="214062020")

# or, using Application Default Credentials with only the spreadsheets scope

sheet = GSheetsTool(sheet_key="0B7ciWr8lX8LTMVVyajlScU42OU0", auth_mode="default", scopes=[SPREADSHEETS_SCOPE])
```

### set_spreadsheet_by_url(self, sheet_url)
Sets the _spreadsheet_ attribute by the Spreadsheet URL, and also the _worksheet_ attribute if the URL has a `#gid=` part (otherwise, the worksheet is unset).

Usage example:
```python
from instackup.gsheets_tools import GSheetsTool


sheet = GSheetsTool(sheet_key="0B7ciWr8lX8LTMVVyajlScU42OU0", sheet_gid="214062020")

# Do something with the selected sheet

# Changing Sheets
sheet.set_spreadsheet_by_url("https://docs.google.com/spreadsheets/d/0B7ciWr8lX8LTWjFMQW4yT2MtRlk/edit#gid=324336327")
```

### set_spreadsheet_by_key(self, sheet_key)
Sets the _spreadsheet_ attribute by the Spreadsheet key value (the ID in its URL). The _worksheet_ attribute is unset.

Usage example:
```python
from instackup.gsheets_tools import GSheetsTool


sheet = GSheetsTool(sheet_key="0B7ciWr8lX8LTMVVyajlScU42OU0", sheet_gid="214062020")

# Do something with the selected sheet

# Changing Sheets (need to setup worksheet before using. See set_worksheet_by_id method)
sheet.set_spreadsheet_by_key("0B7ciWr8lX8LTWjFMQW4yT2MtRlk")
```

### set_worksheet_by_id(self, sheet_gid)
Sets the _worksheet_ attribute by the Worksheet gid value (the number after `#gid=` in its URL), inside the current spreadsheet.

Raises a `ValueError` if no spreadsheet is set or if the worksheet isn't found.

Usage example:
```python
from instackup.gsheets_tools import GSheetsTool


sheet = GSheetsTool(sheet_key="0B7ciWr8lX8LTMVVyajlScU42OU0", sheet_gid="214062020")

# Do something with the selected sheet

# Changing Sheets
sheet.set_spreadsheet_by_key("0B7ciWr8lX8LTWjFMQW4yT2MtRlk")
sheet.set_worksheet_by_id("324336327")
```

### download(self)
Downloads the selected _worksheet_ into a Pandas DataFrame, using its first row as the header. Raises a `ValueError` if no worksheet is set.

Usage example:
```python
from instackup.gsheets_tools import GSheetsTool


sheet = GSheetsTool(sheet_key="0B7ciWr8lX8LTMVVyajlScU42OU0", sheet_gid="214062020")
df = sheet.download()
```

### upload(self, dataframe, write_mode="APPEND", force_upload=False)
Uploads the Pandas DataFrame to the selected worksheet. It has no return value. Raises a `ValueError` if no worksheet is set.

The _write_mode_ parameter determines how the data will be written and can be one of 3 choices (any other raises a `ValueError`):
- APPEND: adds the rows after the data already in the worksheet, leaving the existing cells untouched;
- EMPTY: writes data only if there's no data in the worksheet or if there's just the header; otherwise raises a `ValueError`;
- TRUNCATE: removes any current data and uploads what's in the DataFrame.

When the worksheet has data, the DataFrame columns must match its header, otherwise a `ValueError` is raised. If the _force_upload_ parameter is set to True, this check is skipped (with APPEND, the rows are then added by position).

Missing values (NaN/None) are written as empty cells, and dates/times as text.

Usage example:
```python
import pandas as pd
from instackup.gsheets_tools import GSheetsTool


data_dict = {
    "first_col": pd.Series([1, 2, 3]),
    "second_col": pd.Series([1, 2, 3, 4]),
}
df = pd.DataFrame(data_dict)  # The missing value in first_col will be an empty cell


sheet = GSheetsTool(sheet_key="0B7ciWr8lX8LTMVVyajlScU42OU0", sheet_gid="214062020")
sheet.upload(df, write_mode="TRUNCATE", force_upload=True)
```
