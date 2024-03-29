# Instackup
This Python library is an open source way to standardize and simplify connections with cloud-based tools, databases and commonly used tools in data manipulation and analysis. It can help BI teams by having a unified source code for local development and testing as well as remote production (automated scheduled run) environments.

# Index

- [Current release](#current-release)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Documentation](#documentation)
- [Version logs](#version-logs)

# Current release
**Version 0.3.0 (beta)**

# Prerequisites
1. Have a [Python 3.6 version or superior](https://www.python.org/downloads/) installed;
2. Create a YAML (or JSON) file with credentials information;
3. [Optional but recommended] Configure an Environment Variable that points where the Credentials file is.

### 1. Have a Python 3.6 version or superior installed
Got to this [link](https://www.python.org/downloads/) e download the most current version that is compatible with this package.

### 2. Create a YAML (or JSON) file with credentials information

Use the files [secret_template.yml](https://github.com/Lavedonio/instackup/blob/master/credentials/secret_template.yml) or [secret_blank.yml](https://github.com/Lavedonio/instackup/blob/master/credentials/secret_blank.yml) as a base or copy and paste the code bellow and modify its values to the ones in your credentials/projects:

```
#################################################################
#                                                               #
#        ACCOUNTS CREDENTIALS. DO NOT SHARE THIS FILE.          #
#                                                               #
# Specifications:                                               #
# - For the credentials you don't have, leave it blank.         #
# - Keep Google's secret file in the same folder as this file.  #
# - BigQuery project_ids must be strings, i.e., inside quotes.  #
#                                                               #
# Recommendations:                                              #
# - YAML specification: https://yaml.org/spec/1.2/spec.html     #
# - Keep this file in a static path like a folder within the    #
# Desktop. Ex.: C:\Users\USER\Desktop\Credentials\secret.yml    #
#                                                               #
#################################################################

Location: local


Google:
  default:
    project_id: project_id
    project_name: project_name
    project_number: "000000000000"
    secret_filename: api_key.json


AWS:
  default:
    access_key: AWSAWSAWSAWSAWSAWSAWS
    secret_key: some_secret_key_value

RedShift:
  default:
    cluster_credentials:
      dbname: db
      user: masteruser
      host: blablabla.random.us-east-2.redshift.amazonaws.com
      cluster_id: cluster
      port: 5439
    master_password:
      dbname: db
      user: masteruser
      host: blablabla.random.us-east-2.redshift.amazonaws.com
      password: masterpassword
      port: 5439


PostgreSQL:
  default:
    dbname: postgres
    user: postgres
    host: localhost
    password: ""
    port: 5432


MySQL:
  default:
    dbname: mydb
    host: localhost
    user: root
    password: ""
    port: 3306
```
Save this file with `.yml` extension in a folder where you know the path won't be modified, like the Desktop folder (Example: `C:\Users\USER\Desktop\Credentials\secret.yml`).

If you prefer, you can follow this step using a JSON file instead. Follow the same instructions but using `.json` instead of `.yml`.

### 3. [Optional but recommended] Configure an Environment Variable that points where the Credentials file is.

To configure the Environment Variable, follow the instructions bellow, based on your Operating System.

#### Windows
1. Place the YAML (or JSON) file in a folder you won't change its name or path later;
2. In Windows Search, type `Environment Variables` and click in the Control Panel result;
3. Click on the button `Environment Variables...`;
4. In **Environment Variables**, click on the button `New`;
5. In **Variable name** type `CREDENTIALS_HOME` and in **Variable value** paste the full path to the recently created YAML (or JSON) file;
6. Click **Ok** in the 3 open windows.

#### Linux/MacOS
1. Place the YAML (or JSON) file in a folder you won't change its name or path later;
2. Open the file `.bashrc`. If it doesn't exists, create one in the `HOME` directory. If you don't know how to get there, open the Terminal, type `cd` and then **ENTER**;
3. Inside the file, in a new line, type the command: `export CREDENTIALS_HOME="/path/to/file"`, replacing the content inside quotes by the full path to the recently created YAML (or JSON) file;
4. Save the file and restart all open Terminal windows.

> **Note:** If you don't follow this last prerequisite, you need to set the environment variable manually inside the code. To do that, inside your python code, after the imports, type the command (replacing the content inside quotes by the full path to the recently created YAML (or JSON) file):

```
os.environ["CREDENTIALS_HOME"] = "/path/to/file"
```

# Installation
Go to the Terminal and type:

    pip install instackup

# Documentation
Check the documentation by clicking in each topic.

- [bigquery_tools](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#bigquery_tools)
  - [Global Variables](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#global-variables)
  - [BigQueryTool](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#bigquerytool)
    - [\_\_init\_\_(self, authenticate=True)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#__init__self-authenticatetrue)
    - [query(self, sql_query)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#queryself-sql_query)
    - [query_and_save_results(self, sql_query, dest_dataset, dest_table, writing_mode="TRUNCATE", create_table_if_needed=False)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#query_and_save_resultsself-sql_query-dest_dataset-dest_table-writing_modetruncate-create_table_if_neededfalse)
    - [list_datasets(self)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#list_datasetsself)
    - [create_dataset(self, dataset, location="US")](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#create_datasetself-dataset-locationus)
    - [list_dataset_permissions(self, dataset)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#list_dataset_permissionsself-dataset)
    - [add_dataset_permission(self, dataset, role, email_type, email)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#add_dataset_permissionself-dataset-role-email_type-email)
    - [remove_dataset_permission(self, dataset, email)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#remove_dataset_permissionself-dataset-email)
    - [list_tables_in_dataset(self, dataset, get=None, return_type="dict")](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#list_tables_in_datasetself-dataset-getnone-return_typedict)
    - [get_table_schema(self, dataset, table)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#get_table_schemaself-dataset-table)
    - [convert_postgresql_table_schema(self, dataframe, parse_json_columns=True)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#convert_postgresql_table_schemaself-dataframe-parse_json_columnstrue)
    - [convert_multiple_postgresql_tables_schema(self, dataframe, parse_json_columns=True)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#convert_multiple_postgresql_tables_schemaself-dataframe-parse_json_columnstrue)
    - [convert_dataframe_to_numeric(dataframe, exclude_columns=[], \*\*kwargs)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#convert_dataframe_to_numericdataframe-exclude_columns-kwargs)
    - [clean_dataframe_column_names(dataframe, allowed_chars="abcdefghijklmnopqrstuvwxyz0123456789", special_treatment={})](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#clean_dataframe_column_namesdataframe-allowed_charsabcdefghijklmnopqrstuvwxyz0123456789-special_treatment)
    - [upload(self, dataframe, dataset, table, \*\*kwargs)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#uploadself-dataframe-dataset-table-kwargs)
    - [create_empty_table(self, dataset, table, schema)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#create_empty_tableself-dataset-table-schema)
    - [upload_from_gcs(self, dataset, table, gs_path, file_format="CSV", header_rows=1, delimiter=",", encoding="UTF-8", ignore_unknown_values=False, max_bad_records=0, writing_mode="APPEND", create_table_if_needed=False, schema=None)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#upload_from_gcsself-dataset-table-gs_path-file_formatcsv-header_rows1-delimiter-encodingutf-8-ignore_unknown_valuesfalse-max_bad_records0-writing_modeappend-create_table_if_neededfalse-schemanone)
    - [upload_from_file(self, dataset, table, file_location, file_format="CSV", header_rows=1, delimiter=",", encoding="UTF-8", ignore_unknown_values=False, max_bad_records=0, writing_mode="APPEND", create_table_if_needed=False, schema=None)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#upload_from_fileself-dataset-table-file_location-file_formatcsv-header_rows1-delimiter-encodingutf-8-ignore_unknown_valuesfalse-max_bad_records0-writing_modeappend-create_table_if_neededfalse-schemanone)
    - [start_transfer(self, project_path=None, project_name=None, transfer_name=None)](https://github.com/Lavedonio/instackup/blob/master/docs/bigquery_tools.md#start_transferself-project_pathnone-project_namenone-transfer_namenone)
- [gcloudstorage_tools](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#gcloudstorage_tools)
  - [GCloudStorageTool](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#gcloudstoragetool)
    - [\_\_init\_\_(self, uri=None, bucket=None, subfolder="", filename=None, authenticate=True)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#__init__self-urinone-bucketnone-subfolder-filenamenone-authenticatetrue)
    - [bucket(self) @property](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#bucketself-property)
    - [blob(self) @property](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#blobself-property)
    - [uri(self) @property](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#uriself-property)
    - [set_bucket(self, bucket)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#set_bucketself-bucket)
    - [set_subfolder(self, subfolder)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#set_subfolderself-subfolder)
    - [select_file(self, filename)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#select_fileself-filename)
    - [list_all_buckets(self)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#list_all_bucketsself)
    - [get_bucket_info(self, bucket=None)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#get_bucket_infoself-bucketnone)
    - [get_file_info(self, filename=None, info=None)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#get_file_infoself-filenamenone-infonone)
    - [list_contents(self, yield_results=False)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#list_contentsself-yield_resultsfalse)
    - [rename_file(self, new_filename)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#rename_fileself-new_filename)
    - [rename_subfolder(self, new_subfolder)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#rename_subfolderself-new_subfolder)
    - [upload_file(self, filename, remote_path=None)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#upload_fileself-filename-remote_pathnone)
    - [upload_subfolder(self, folder_path)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#upload_subfolderself-folder_path)
    - [upload_from_dataframe(self, dataframe, file_format='CSV', filename=None, overwrite=False, \*\*kwargs)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#upload_from_dataframeself-dataframe-file_formatcsv-filenamenone-overwritefalse-kwargs)
    - [download_file(self, download_to=None, remote_filename=None, replace=False)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#download_fileself-download_tonone-remote_filenamenone-replacefalse)
    - [download_subfolder(self)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#download_subfolderself)
    - [download_on_dataframe(self, \*\*kwargs)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#download_on_dataframeself-kwargs)
    - [download_as_string(self, remote_filename=None, encoding="UTF-8")](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#download_as_stringself-remote_filenamenone-encodingutf-8)
    - [delete_file(self)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#delete_fileself)
    - [delete_subfolder(self)](https://github.com/Lavedonio/instackup/blob/master/docs/gcloudstorage_tools.md#delete_subfolderself)
- [general_tools](https://github.com/Lavedonio/instackup/blob/master/docs/general_tools.md#general_tools)
  - [fetch_credentials(service_name, \*\*kwargs)](https://github.com/Lavedonio/instackup/blob/master/docs/general_tools.md#fetch_credentialsservice_name-kwargs)
  - [code_location()](https://github.com/Lavedonio/instackup/blob/master/docs/general_tools.md#code_location)
  - [unicode_to_ascii(unicode_string)](https://github.com/Lavedonio/instackup/blob/master/docs/general_tools.md#unicode_to_asciiunicode_string)
  - [parse_remote_uri(uri, service)](https://github.com/Lavedonio/instackup/blob/master/docs/general_tools.md#parse_remote_uriuri-service)
- [gsheets_tools](https://github.com/Lavedonio/instackup/blob/master/docs/gsheets_tools.md#gsheets_tools)
  - [GSheetsTool](https://github.com/Lavedonio/instackup/blob/master/docs/gsheets_tools.md#gsheetstool)
    - [\_\_init\_\_(self, sheet_url=None, sheet_key=None, sheet_gid=None, auth_mode='secret_key', read_only=False, scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])](https://github.com/Lavedonio/instackup/blob/master/docs/gsheets_tools.md#__init__self-sheet_urlnone-sheet_keynone-sheet_gidnone-auth_modesecret_key-read_onlyfalse-scopeshttpswwwgoogleapiscomauthspreadsheets-httpswwwgoogleapiscomauthdrive)
    - [set_spreadsheet_by_url(self, sheet_url)](https://github.com/Lavedonio/instackup/blob/master/docs/gsheets_tools.md#set_spreadsheet_by_urlself-sheet_url)
    - [set_spreadsheet_by_key(self, sheet_key)](https://github.com/Lavedonio/instackup/blob/master/docs/gsheets_tools.md#set_spreadsheet_by_keyself-sheet_key)
    - [set_worksheet_by_id(self, sheet_gid)](https://github.com/Lavedonio/instackup/blob/master/docs/gsheets_tools.md#set_worksheet_by_idself-sheet_gid)
    - [download(self)](https://github.com/Lavedonio/instackup/blob/master/docs/gsheets_tools.md#downloadself)
    - [upload(self, dataframe, write_mode="APPEND", force_upload=False)](https://github.com/Lavedonio/instackup/blob/master/docs/gsheets_tools.md#uploadself-dataframe-write_modeappend-force_uploadfalse)
- [heroku_tools](https://github.com/Lavedonio/instackup/blob/master/docs/heroku_tools.md#heroku_tools)
  - [HerokuTool](https://github.com/Lavedonio/instackup/blob/master/docs/heroku_tools.md#herokutool)
    - [\_\_init\_\_(self, heroku_path="heroku", app=None, remote=None)](https://github.com/Lavedonio/instackup/blob/master/docs/heroku_tools.md#__init__self-heroku_pathheroku-appnone-remotenone)
    - [app_flag(self) @property](https://github.com/Lavedonio/instackup/blob/master/docs/heroku_tools.md#app_flagself-property)
    - [execute(self, cmd)](https://github.com/Lavedonio/instackup/blob/master/docs/heroku_tools.md#executeself-cmd)
- [redshift_tools](https://github.com/Lavedonio/instackup/blob/master/docs/redshift_tools.md#redshift_tools)
  - [RedShiftTool](https://github.com/Lavedonio/instackup/blob/master/docs/redshift_tools.md#redshifttool)
    - [\_\_init\_\_(self, connect_by_cluster=True)](https://github.com/Lavedonio/instackup/blob/master/docs/redshift_tools.md#__init__self-connect_by_clustertrue)
    - [connect(self, fail_silently=False)](https://github.com/Lavedonio/instackup/blob/master/docs/redshift_tools.md#connectself-fail_silentlyfalse)
    - [commit(self)](https://github.com/Lavedonio/instackup/blob/master/docs/redshift_tools.md#commitself)
    - [rollback(self)](https://github.com/Lavedonio/instackup/blob/master/docs/redshift_tools.md#rollbackself)
    - [close_connection(self)](https://github.com/Lavedonio/instackup/blob/master/docs/redshift_tools.md#close_connectionself)
    - [execute_sql(self, command, fail_silently=False)](https://github.com/Lavedonio/instackup/blob/master/docs/redshift_tools.md#execute_sqlself-command-fail_silentlyfalse)
    - [query(self, sql_query, fetch_through_pandas=True, fail_silently=False)](https://github.com/Lavedonio/instackup/blob/master/docs/redshift_tools.md#queryself-sql_query-fetch_through_pandastrue-fail_silentlyfalse)
    - [describe_table(self, table, schema="public", fetch_through_pandas=True, fail_silently=False)](https://github.com/Lavedonio/instackup/blob/master/docs/redshift_tools.md#describe_tableself-table-schemapublic-fetch_through_pandastrue-fail_silentlyfalse)
    - [get_all_db_info(self, get_json_info=True, fetch_through_pandas=True, fail_silently=False)](https://github.com/Lavedonio/instackup/blob/master/docs/redshift_tools.md#get_all_db_infoself-get_json_infotrue-fetch_through_pandastrue-fail_silentlyfalse)
    - [unload_to_S3(self, redshift_query, s3_path, filename, unload_options="MANIFEST GZIP ALLOWOVERWRITE REGION 'us-east-2'")](https://github.com/Lavedonio/instackup/blob/master/docs/redshift_tools.md#unload_to_s3self-redshift_query-s3_path-filename-unload_optionsmanifest-gzip-allowoverwrite-region-us-east-2)
- [s3_tools](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#s3_tools)
  - [S3Tool](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#s3tool)
    - [\_\_init\_\_(self, uri=None, bucket=None, subfolder="")](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#__init__self-urinone-bucketnone-subfolder)
    - [bucket(self) @property](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#bucketself-property)
    - [uri(self) @property](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#uriself-property)
    - [set_bucket(self, bucket)](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#set_bucketself-bucket)
    - [set_subfolder(self, subfolder)](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#set_subfolderself-subfolder)
    - [rename_file(self, old_filename, new_filename)](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#rename_fileself-old_filename-new_filename)
    - [rename_subfolder(self, new_subfolder)](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#rename_subfolderself-new_subfolder)
    - [list_all_buckets(self)](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#list_all_bucketsself)
    - [list_contents(self, yield_results=False)](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#list_contentsself-yield_resultsfalse)
    - [upload_file(self, filename, remote_path=None)](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#upload_fileself-filename-remote_pathnone)
    - [upload_subfolder(self, folder_path)](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#upload_subfolderself-folder_path)
    - [download_file(self, remote_path, filename=None)](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#download_fileself-remote_path-filenamenone)
    - [download_subfolder(self, download_to=None)](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#download_subfolderself-download_tonone)
    - [delete_file(self, filename, fail_silently=False)](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#delete_fileself-filename-fail_silentlyfalse)
    - [delete_subfolder(self)](https://github.com/Lavedonio/instackup/blob/master/docs/s3_tools.md#delete_subfolderself)
- [sql_tools](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#sql_tools)
  - [SQLTool](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#sqltool)
    - [\_\_init\_\_(self, sql_type, filename=None, connection='default')](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#__init__self-sql_type-filenamenone-connectiondefault)
    - [connect(self, fail_silently=False)](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#connectself-fail_silentlyfalse)
    - [commit(self)](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#commitself)
    - [rollback(self)](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#rollbackself)
    - [close_connection(self)](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#close_connectionself)
    - [execute_sql(self, command, fail_silently=False)](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#execute_sqlself-command-fail_silentlyfalse)
    - [query(self, sql_query, fetch_through_pandas=True, fail_silently=False)](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#queryself-sql_query-fetch_through_pandastrue-fail_silentlyfalse)
  - [SQLiteTool](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#sqlitetool)
    - [\_\_init\_\_(self, filename=None)](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#__init__self-filenamenone)
    - [describe_table(self, table, fetch_through_pandas=True, fail_silently=False)](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#describe_tableself-table-fetch_through_pandastrue-fail_silentlyfalse)
  - [MySQLTool](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#mysqltool)
    - [\_\_init\_\_(self, connection='default')](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#__init__self-connectiondefault)
    - [describe_table(self, table, fetch_through_pandas=True, fail_silently=False)](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#describe_tableself-table-fetch_through_pandastrue-fail_silentlyfalse-1)
  - [PostgreSQLTool](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#postgresqltool)
    - [\_\_init\_\_(self, connection='default')](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#__init__self-connectiondefault-1)
    - [describe_table(self, table, schema="public", fetch_through_pandas=True, fail_silently=False)](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#describe_tableself-table-schemapublic-fetch_through_pandastrue-fail_silentlyfalse-2)
    - [get_all_db_info(self, get_json_info=True, fetch_through_pandas=True, fail_silently=False)](https://github.com/Lavedonio/instackup/blob/master/docs/sql_tools.md#get_all_db_infoself-get_json_infotrue-fetch_through_pandastrue-fail_silentlyfalse)

# Version logs
See what changed in every version.

- Beta releases
  - [Version 0.3.0](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.3.0-beta-current_release.md#version-030-beta) (current release)
  - [Version 0.2.6](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.2.6-beta.md#version-026-beta)
  - [Version 0.2.5](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.2.5-beta.md#version-025-beta)
  - [Version 0.2.4](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.2.4-beta.md#version-024-beta)
  - [Version 0.2.3](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.2.3-beta.md#version-023-beta)
  - [Version 0.2.2](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.2.2-beta.md#version-022-beta)
  - [Version 0.2.1](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.2.1-beta.md#version-021-beta)
  - [Version 0.2.0](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.2.0-beta.md#version-020-beta)
  - [Version 0.1.2](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.1.2-beta.md#version-012-beta)
  - [Version 0.1.1](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.1.1-beta.md#version-011-beta)
  - [Version 0.1.0](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.1.0-beta.md#version-010-beta)
- Alpha releases
  - [Version 0.0.6](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.0.6-alpha.md#version-006-alpha)
  - [Version 0.0.5](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.0.5-alpha.md#version-005-alpha)
  - [Version 0.0.4](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.0.4-alpha.md#version-004-alpha)
  - [Version 0.0.3](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.0.3-alpha.md#version-003-alpha)
  - [Version 0.0.2](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.0.2-alpha.md#version-002-alpha)
  - [Version 0.0.1](https://github.com/Lavedonio/instackup/blob/master/version_logs/v0.0.1-alpha.md#version-001-alpha)
