# heroku_tools
This is the documentation for the heroku_tools module and all its contents, with usage examples.

This module needs no extra dependencies (a plain `pip install instackup` is enough), but the [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli) must be installed.

# Index
- [HerokuTool](#herokutool)
  - [\_\_init\_\_(self, heroku_path="heroku", app=None, remote=None)](#__init__self-heroku_pathheroku-appnone-remotenone)
  - [app_flag(self) @property](#app_flagself-property)
  - [execute(self, cmd)](#executeself-cmd)

# Module Contents
## HerokuTool
This class encapsulates and handles most of the interaction needed with the Heroku CLI, so the base code becomes more readable and straightforward.

Commands are run without a shell, so arguments can't be used to inject other commands.

### \_\_init\_\_(self, heroku_path="heroku", app=None, remote=None)
Initialization takes the optional parameter _heroku_path_, which is either the name of the CLI in the PATH variable or the actual path to the CLI app location in the system.

It also takes 2 extra optional parameters: _app_ and _remote_, which specify the current app in use. There's no need to fill both, just one is ok (_app_ wins if both are set). If there's only one registered app, these parameters don't need to be filled.

Raises an `OSError` if the Heroku CLI isn't installed or can't be reached.

Usage example:
```python
from instackup.heroku_tools import HerokuTool

# There's no need to fill both app and remote parameters. This is just an example.
heroku = HerokuTool(heroku_path="path/to/heroku", app="lavedonio", remote="heroku-staging")
```

### app_flag(self) @property
Returns the app flag string (`--app <app>` or `--remote <remote>`) that's added to every command run by the execute method, based on the _app_ or _remote_ parameters given in \_\_init\_\_. It's an empty string if neither is set.

### execute(self, cmd)
Executes a Heroku command via the CLI. _cmd_ can be either a string (split like a shell would) or a list of arguments.

Returns the `subprocess.CompletedProcess` of the command; its `stdout` and `stderr` attributes are bytes. A failing command doesn't raise an error, so check its `returncode`.

Usage example:
```python
from instackup.heroku_tools import HerokuTool

heroku = HerokuTool(remote="heroku-staging")

result = heroku.execute("releases")
print(result.stdout.decode())

# Same as: heroku config:get DATABASE_URL --remote heroku-staging
result = heroku.execute(["config:get", "DATABASE_URL"])
if result.returncode == 0:
    database_url = result.stdout.decode().strip()
```
