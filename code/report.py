"""
report.py — BatchResult -> the on-screen outcomes table, the downloadable
exception report, and the summary metrics dict. No streamlit import, no
filesystem writes, zero arithmetic beyond counting.

missing_cols / extra_cols are Python lists on FileOutcome; both frame
builders here join them with config.LIST_JOIN_SEPARATOR so every cell in
every DataFrame this module produces is a scalar str, consistent with the
precision contract in ARCHITECTURE.md section 5 (a raw list in a CSV cell
would render as "['A', 'B']", which is not a value anyone asked for).
"""

from __future__ import annotations

from typing import Sequence

import pandas as pd

import config
from models import BatchResult, FileOutcome


def _join(values: list[str]) -> str:
    return config.LIST_JOIN_SEPARATOR.join(values)


def outcomes_to_frame(outcomes: Sequence[FileOutcome]) -> pd.DataFrame:
    """All outcomes, for the on-screen table: file, status, reason,
    study_name, rows, missing_cols, extra_cols (lists joined with
    config.LIST_JOIN_SEPARATOR).
    """
    return pd.DataFrame(
        {
            "file": [o.file for o in outcomes],
            "status": [o.status for o in outcomes],
            "reason": [o.reason for o in outcomes],
            "study_name": [o.study_name for o in outcomes],
            "rows": [o.rows for o in outcomes],
            "missing_cols": [_join(o.missing_cols) for o in outcomes],
            "extra_cols": [_join(o.extra_cols) for o in outcomes],
        },
        columns=["file", "status", "reason", "study_name", "rows", "missing_cols", "extra_cols"],
    )


def build_exception_report(outcomes: Sequence[FileOutcome]) -> pd.DataFrame:
    """Only outcomes where status != STATUS_APPENDED. Exactly
    config.EXCEPTION_REPORT_COLUMNS, in that order. Returns an empty frame
    WITH those columns when there are no exceptions.
    """
    exceptions = [o for o in outcomes if o.status != config.STATUS_APPENDED]
    frame = pd.DataFrame(
        {
            "file": [o.file for o in exceptions],
            "status": [o.status for o in exceptions],
            "reason": [o.reason for o in exceptions],
            "missing_cols": [_join(o.missing_cols) for o in exceptions],
            "extra_cols": [_join(o.extra_cols) for o in exceptions],
        },
        columns=config.EXCEPTION_REPORT_COLUMNS,
    )
    return frame


def summarize(result: BatchResult) -> dict[str, int]:
    """Keys, in display order:
      'Total files processed', 'Files successfully appended',
      'Files skipped (already in master)', 'Files rejected',
      'Records appended this run', 'Total records in master'.

    Items 5/6 show both interpretations of "total records consolidated"
    (rows added this run, and rows in the final master).
    # DESIGN DEFAULT — pending confirmation, see spec section 8, item 1
    """
    return {
        "Total files processed": result.total_files,
        "Files successfully appended": result.appended,
        "Files skipped (already in master)": result.skipped,
        "Files rejected": result.rejected,
        "Records appended this run": result.rows_appended,
        "Total records in master": result.total_records,
    }
