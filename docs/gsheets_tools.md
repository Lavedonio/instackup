# gsheets_tools
This is the documentation for the gsheets_tools module and all its contents, with usage examples.

# Index
- [GSheetsTool](#gsheetstool)
  - [\_\_init\_\_(self, sheet_url=None, sheet_key=None, sheet_gid=None, auth_mode='secret_key', read_only=False, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])](#__init__self-sheet_urlnone-sheet_keynone-sheet_gidnone-auth_modesecret_key-read_onlyfalse-scopeshttpswwwgoogleapiscomauthspreadsheets-httpswwwgoogleapiscomauthdrive)
  - [set_spreadsheet_by_url(self, sheet_url)](#set_spreadsheet_by_urlself-sheet_url)
  - [set_spreadsheet_by_key(self, sheet_key)](#set_spreadsheet_by_keyself-sheet_key)
  - [set_worksheet_by_id(self, sheet_gid)](#set_worksheet_by_idself-sheet_gid)
  - [download(self)](#downloadself)
  - [upload(self, dataframe, write_mode="APPEND", force_upload=False)](#uploadself-dataframe-write_modeappend-force_uploadfalse)

# Module Contents
## GSheetsTool
This class encapsulates the gspread module to ease the setup process and handle most of the interaction needed with Google Sheets, so the base code becomes more readable and straightforward.

### \_\_init\_\_(self, sheet_url=None, sheet_key=None, sheet_gid=None, auth_mode='secret_key', read_only=False, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
Initialization takes either _sheet_url_ or _sheet_key_ and _sheet_gid_ parameters to first referenciate the worksheet.

_auth_mode_ parameter can be 1 out of 3 types:
- secret_key: will look for the configured Secret Key,;
- oauth: will prompt a window requiring manual authentication;
- composer: will use the Google Cloud Composer environment (as long it's running in one) to set the credentials to that project.

_read_only_ parameter will convert the scopes to their read only versions. That means that they will can only be seen or downloaded, but not edited.

_scopes_ parameter sets the appropriated scopes to the environment when connecting. Sometimes only the spreadsheets authorization is necessary or can be given.

Usage example:
```
from instackup.gsheets_tools import GSheetsTool


sheet = GSheetsTool(sheet_url="https://docs.google.com/spreadsheets/d/0B7ciWr8lX8LTMVVyajlScU42OU0/edit#gid=214062020")

# or

sheet = GSheetsTool(sheet_key="0B7ciWr8lX8LTMVVyajlScU42OU0", sheet_gid="214062020")
```

### set_spreadsheet_by_url(self, sheet_url)
Set _spreadsheet_ and _worksheet_ attributes by the Spreadsheet URL.

Usage example:
```
from instackup.gsheets_tools import GSheetsTool


sheet = GSheetsTool(sheet_key="0B7ciWr8lX8LTMVVyajlScU42OU0", sheet_gid="214062020")

# Do something with the selected sheet

# Changing Sheets
sheet.set_spreadsheet_by_url("https://docs.google.com/spreadsheets/d/0B7ciWr8lX8LTWjFMQW4yT2MtRlk/edit#gid=324336327")
```

### set_spreadsheet_by_key(self, sheet_key)
Set _spreadsheet_ attribute by the Spreadsheet key value.

Usage example:
```
from instackup.gsheets_tools import GSheetsTool


sheet = GSheetsTool(sheet_key="0B7ciWr8lX8LTMVVyajlScU42OU0", sheet_gid="214062020")

# Do something with the selected sheet

# Changing Sheets (need to setup worksheet before using. See set_worksheet_by_id method)
sheet.set_spreadsheet_by_key("0B7ciWr8lX8LTWjFMQW4yT2MtRlk")
```

### set_worksheet_by_id(self, sheet_gid)
Set _worksheet_ attribute by the Spreadsheet gid value.

Usage example:
```
from instackup.gsheets_tools import GSheetsTool


sheet = GSheetsTool(sheet_key="0B7ciWr8lX8LTMVVyajlScU42OU0", sheet_gid="214062020")

# Do something with the selected sheet

# Changing Sheets
sheet.set_spreadsheet_by_key("0B7ciWr8lX8LTWjFMQW4yT2MtRlk")
sheet.set_worksheet_by_id("324336327")
```

### download(self)
Download the selected _worksheet_ into a Pandas DataFrame. Raises an error if no worksheet is set.

Usage example:
```
from instackup.gsheets_tools import GSheetsTool


sheet = GSheetsTool(sheet_key="0B7ciWr8lX8LTMVVyajlScU42OU0", sheet_gid="214062020")
df = sheet.download()
```

### upload(self, dataframe, write_mode="APPEND", force_upload=False)
Upload the Pandas DataFrame to the selected worksheet. Raises an error if no worksheet is set.

The write_mode parameter determines how the data will be written and can be one of 3 choices:
- APPEND: will append the data to what's written in the worksheet;
- EMPTY: writes data only if there's not data in the wroksheet or if there's just the headers;
- TRUNCATE: removes any current data and uploads what's in the DataFrame.

If the force_upload parameter is set to True, it won't validade if the combination of what's in the worksheet and what's in the DataFrame fits.

Usage example:
```
import pandas as pd
from instackup.gsheets_tools import GSheetsTool


data_dict = {
    'first_col': pd.Series([1, 2, 3]),
    'second_col': pd.Series([1, 2, 3, 4])
}
df = pd.DataFrame(data_dict)


sheet = GSheetsTool(sheet_key="0B7ciWr8lX8LTMVVyajlScU42OU0", sheet_gid="214062020")
df = sheet.upload(df, write_mode="TRUNCATE")
```
