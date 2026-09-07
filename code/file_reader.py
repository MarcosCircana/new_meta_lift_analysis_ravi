"""
file_reader.py — bytes -> all-string DataFrame (.csv / .xlsx sheet 1).

Zero arithmetic happens here or anywhere downstream: every read is dtype=str,
na_filter=False, and _finalize() guarantees every remaining cell is a Python
str. See ARCHITECTURE.md section 5 for the full precision contract and the
banned-call list. This module performs no filesystem writes.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

import config

_CSV_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "cp1252", "latin-1")


class FileReadError(Exception):
    """Carries a config.REASON_* token so callers classify without string-sniffing."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


def read_table(filename: str, data: bytes) -> pd.DataFrame:
    """Dispatch on extension. Returns a DataFrame whose every cell is a str.

    Raises FileReadError(REASON_EMPTY_FILE) for zero-length bytes or a CSV with no
    header line. Raises FileReadError(REASON_UNREADABLE) for anything else that fails
    to parse, or an unrecognised extension.

    Valid headers with zero data rows is NOT an error — it returns an empty DataFrame
    with populated .columns. The caller classifies that.
    """
    if len(data) == 0:
        raise FileReadError(config.REASON_EMPTY_FILE, "zero-length file")

    extension = Path(filename).suffix.lower()

    if extension == ".csv":
        df = _read_csv_bytes(data)
    elif extension == ".xlsx":
        df = _read_excel_bytes(data)
    else:
        raise FileReadError(config.REASON_UNREADABLE, f"unrecognised extension: {extension!r}")

    return _finalize(df)


def _read_csv_bytes(data: bytes) -> pd.DataFrame:
    """Try the encoding fallback chain in order. Only if all three fail (or the
    content genuinely has no header line) does this raise."""
    last_error: Exception | None = None
    for encoding in _CSV_ENCODINGS:
        try:
            return pd.read_csv(
                io.BytesIO(data),
                dtype=str,
                na_filter=False,
                encoding=encoding,
                engine="c",
            )
        except pd.errors.EmptyDataError as e:
            raise FileReadError(config.REASON_EMPTY_FILE, str(e)) from e
        except Exception as e:
            last_error = e
            continue

    raise FileReadError(
        config.REASON_UNREADABLE,
        str(last_error) if last_error else "unreadable CSV",
    )


def _read_excel_bytes(data: bytes) -> pd.DataFrame:
    """Reads sheet index config.EXCEL_SHEET_INDEX only (brief decision 6)."""
    try:
        return pd.read_excel(
            io.BytesIO(data),
            sheet_name=config.EXCEL_SHEET_INDEX,
            dtype=str,
        )
    except Exception as e:
        raise FileReadError(config.REASON_UNREADABLE, str(e)) from e


def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    """Strip column-name whitespace; fillna(''); guarantee every cell is a str."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.fillna("").astype(str)
    return df
