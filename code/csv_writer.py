"""
csv_writer.py — Timestamped filenames + UTF-8-BOM bytes for download.
No streamlit import, no filesystem writes, zero arithmetic. This module
never reads or transforms data — it only formats a filename string and
encodes an already-final DataFrame to bytes.

`now` is injectable on both filename builders purely so tests can assert
the exact filename string deterministically (ARCHITECTURE.md section 1).
"""

from __future__ import annotations

from datetime import datetime

import config


def build_master_filename(base_name: str, now: datetime | None = None) -> str:
    """'Instacart' -> 'Master_Instacart_2026-09-07_1430.csv' (given now)."""
    timestamp = (now or datetime.now()).strftime(config.TIMESTAMP_FORMAT)
    return config.MASTER_FILENAME_PATTERN.format(name=base_name, timestamp=timestamp)


def build_exception_filename(base_name: str, now: datetime | None = None) -> str:
    """'Instacart' -> 'Exceptions_Instacart_2026-09-07_1430.csv' (given now)."""
    timestamp = (now or datetime.now()).strftime(config.TIMESTAMP_FORMAT)
    return config.EXCEPTION_FILENAME_PATTERN.format(name=base_name, timestamp=timestamp)


def to_csv_bytes(df) -> bytes:
    """df.to_csv(index=False).encode(config.OUTPUT_ENCODING).

    MUST NOT pass float_format. MUST NOT be preceded by any rounding —
    see ARCHITECTURE.md section 5's banned-call list. Every cell entering
    this function is already a Python str (guaranteed upstream by
    file_reader._finalize and schema.py), so to_csv never has anything to
    coerce.
    """
    return df.to_csv(index=False).encode(config.OUTPUT_ENCODING)
