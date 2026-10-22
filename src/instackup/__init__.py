"""Instackup: simple, unified access to cloud services, databases and common data tools.

Each tool lives in its own module and only needs its own optional dependencies, e.g.
``pip install 'instackup[gcp]'`` for BigQuery and Cloud Storage. The tool classes are
also importable from the package root; their modules are imported on first use.
"""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING, Any

try:
    from ._version import __version__
except ImportError:  # pragma: no cover - only when running from a source tree without building
    __version__ = "0.0.0"

# Libraries shouldn't configure logging; applications decide where records go.
logging.getLogger(__name__).addHandler(logging.NullHandler())

_LAZY_ATTRIBUTES = {
    "BigQueryTool": "bigquery_tools",
    "GCloudStorageTool": "gcloudstorage_tools",
    "GSheetsTool": "gsheets_tools",
    "HerokuTool": "heroku_tools",
    "MySQLTool": "sql_tools",
    "PostgreSQLTool": "sql_tools",
    "RedShiftTool": "redshift_tools",
    "S3Tool": "s3_tools",
    "SQLiteTool": "sql_tools",
}

__all__ = [
    "BigQueryTool",
    "GCloudStorageTool",
    "GSheetsTool",
    "HerokuTool",
    "MySQLTool",
    "PostgreSQLTool",
    "RedShiftTool",
    "S3Tool",
    "SQLiteTool",
    "__version__",
]

if TYPE_CHECKING:
    from .bigquery_tools import BigQueryTool
    from .gcloudstorage_tools import GCloudStorageTool
    from .gsheets_tools import GSheetsTool
    from .heroku_tools import HerokuTool
    from .redshift_tools import RedShiftTool
    from .s3_tools import S3Tool
    from .sql_tools import MySQLTool, PostgreSQLTool, SQLiteTool


def __getattr__(name: str) -> Any:
    module_name = _LAZY_ATTRIBUTES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(f".{module_name}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_ATTRIBUTES})
