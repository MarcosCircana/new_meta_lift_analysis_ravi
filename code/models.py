"""
models.py — Data contracts passed between modules. No behaviour beyond the
documented @property helpers. Nothing here reads a file or touches pandas
beyond typing a DataFrame field.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class UploadedItem:
    """One file as handed to the pipeline. app.py builds these from st.file_uploader."""

    index: int      # position in the upload list — the ONLY stable identity key
    name: str       # verbatim filename incl. extension
    data: bytes     # full file bytes, read once by app.py

    @property
    def stem(self) -> str:
        """Filename minus final extension, otherwise verbatim."""
        return Path(self.name).stem

    @property
    def extension(self) -> str:
        """Lowercased, incl. dot."""
        return Path(self.name).suffix.lower()


@dataclass(frozen=True)
class MasterCandidate:
    """A file whose stem starts with 'master_' (case-insensitive)."""

    index: int
    name: str
    readable: bool
    has_study_name: bool
    error: str                       # "" when readable

    @property
    def is_valid(self) -> bool:
        """readable and has_study_name."""
        return self.readable and self.has_study_name


@dataclass(frozen=True, eq=False)
class MasterContext:
    """The runtime schema authority. Built once per run, never mutated."""

    frame: pd.DataFrame              # master rows, every column dtype=object holding str
    columns: list[str]               # verbatim master column names, in master order
    column_index: dict[str, str]     # normalized name -> verbatim master column name
    base_name: str                   # <Name> for Master_<Name>_<stamp>.csv
    source_file: str                 # filename the master came from ("" if created this run)
    source_index: int                # UploadedItem.index of the master; -1 if none
    existing_study_names: set[str]   # normalized (strip+casefold), blanks excluded
    created_this_run: bool           # True on the "first master" path


@dataclass(frozen=True)
class FileOutcome:
    """One row of the on-screen table AND the source of the exception report."""

    file: str                   # UploadedItem.name, verbatim
    index: int                  # UploadedItem.index
    status: str                 # config.STATUS_*
    reason: str                 # config.REASON_* ("" only when status == appended)
    missing_cols: list[str]     # master columns absent from the file (verbatim master names)
    extra_cols: list[str]       # file columns absent from the master (verbatim file names)
    study_name: str             # name used/attempted; "" if never determined
    rows: int                   # rows appended; 0 for skipped/rejected


@dataclass(frozen=True, eq=False)
class BatchResult:
    master_df: pd.DataFrame          # final consolidated master, master column order
    outcomes: list[FileOutcome]      # one per candidate study file, in upload order
    total_files: int                 # len(outcomes) — excludes the master itself
    appended: int
    skipped: int
    rejected: int
    rows_appended: int               # sum of FileOutcome.rows
    total_records: int               # len(master_df)
