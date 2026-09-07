"""
config.py — Constants only. No logic, no I/O, no column-name literals beyond
Study_Name (the one literal column name the app is allowed to know about).

The 31-name reference schema for study files lives ONLY in
test_meta_pipeline.py. Adding a data-column list here is a QC failure.
"""

from __future__ import annotations

ACCEPTED_EXTENSIONS: tuple[str, ...] = (".csv", ".xlsx")
EXCEL_SHEET_INDEX: int = 0                    # brief decision 6: "Excel reads sheet 1"

MASTER_FILENAME_PREFIX: str = "master_"       # compared against stem.lower()
STUDY_NAME_COL: str = "Study_Name"            # the only literal column name in the app

OUTPUT_ENCODING: str = "utf-8-sig"
TIMESTAMP_FORMAT: str = "%Y-%m-%d_%H%M"       # brief decision 15
MASTER_FILENAME_PATTERN: str = "Master_{name}_{timestamp}.csv"
EXCEPTION_FILENAME_PATTERN: str = "Exceptions_{name}_{timestamp}.csv"  # DESIGN DEFAULT — pending confirmation, see spec section 8, item 8
MASTER_TIMESTAMP_SUFFIX_RE: str = r"^(?P<name>.+)_\d{4}-\d{2}-\d{2}_\d{4}$"
ILLEGAL_FILENAME_CHARS: str = '<>:"/\\|?*'
FILENAME_REPLACEMENT_CHAR: str = "_"

STATUS_APPENDED: str = "appended"
STATUS_SKIPPED: str = "skipped"
STATUS_REJECTED: str = "rejected"

REASON_NONE: str = ""
REASON_UNREADABLE: str = "unreadable"
REASON_EMPTY_FILE: str = "empty file"
REASON_NO_DATA_ROWS: str = "no data rows"
REASON_COLUMN_MISMATCH: str = "column mismatch"
REASON_DUPLICATE_COLUMNS: str = "duplicate columns"
REASON_ALREADY_IN_MASTER: str = "already in master"
REASON_DUPLICATE_IN_BATCH: str = "duplicate in batch"
REASON_BLANK_STUDY_NAME: str = "blank study name"
REASON_NOT_SELECTED_MASTER: str = "not selected as master"  # DESIGN DEFAULT — pending confirmation, see spec section 8, item 5

EXCEPTION_REPORT_COLUMNS: list[str] = ["file", "status", "reason", "missing_cols", "extra_cols"]
LIST_JOIN_SEPARATOR: str = "; "
