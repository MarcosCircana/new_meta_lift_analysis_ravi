"""
test_meta_pipeline.py — End-to-end QC script for the Meta Analysis Consolidation
pipeline. Run with: python test_meta_pipeline.py
Uses real sample files and the deliberate test_fixtures edge cases. No mocking.
Prints PASS/FAIL for every check.

Sections (grows with each build phase — see ARCHITECTURE.md section 7):
  1. Imports and config sanity                       [Phase 1]
  2. Reading the real sample files                    [Phase 1]
  3. Precision round-trip (BLOCKING gate)              [Phase 1]
  4. normalize_column / compare_columns / align_to_master   [Phase 2]
  5. Master detection (0/1/2 candidates, name parsing)       [Phase 3]
  6. Full batch processing                                   [Phase 4]
  7. Edge-case fixtures (full set)                            [Phase 4]
  8. Exception report and summary shape                       [Phase 4]
  9. csv_writer.py + Phase 5 QC checkpoint (precision round-trip
     through the complete pipeline, filenames, BOM, streamlit-import grep) [Phase 5]

REFERENCE_STUDY_COLUMNS (the 31 names from META_BRIEF.md section 4) is defined
HERE AND NOWHERE ELSE. config.py must never carry this list.
"""

from __future__ import annotations

import ast
import csv
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths to real files
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "Samples"
FIXTURES_DIR = ROOT / "test_fixtures"

# ---------------------------------------------------------------------------
# Helpers — copied in style from new_pg_antara_6_24/code/test_pipeline.py
# ---------------------------------------------------------------------------
_passed = 0
_failed = 0


def check(label: str, result: bool, detail: str = "") -> None:
    global _passed, _failed
    status = "PASS" if result else "FAIL"
    line = f"[{status}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    if result:
        _passed += 1
    else:
        _failed += 1


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# SECTION 1 — Imports and config sanity
# ---------------------------------------------------------------------------
section("1. Imports and Config Sanity")

try:
    import config
    from models import UploadedItem, MasterCandidate, MasterContext, FileOutcome, BatchResult
    from file_reader import FileReadError, read_table
    check("config, models, file_reader import OK", True)
except Exception as e:
    check("config, models, file_reader import OK", False, str(e))
    print("\nCannot continue — fix imports first.")
    sys.exit(1)

check(
    "ACCEPTED_EXTENSIONS == ('.csv', '.xlsx')",
    config.ACCEPTED_EXTENSIONS == (".csv", ".xlsx"),
    str(config.ACCEPTED_EXTENSIONS),
)
check("EXCEL_SHEET_INDEX == 0", config.EXCEL_SHEET_INDEX == 0)
check("MASTER_FILENAME_PREFIX == 'master_'", config.MASTER_FILENAME_PREFIX == "master_")
check("STUDY_NAME_COL == 'Study_Name'", config.STUDY_NAME_COL == "Study_Name")
check("OUTPUT_ENCODING == 'utf-8-sig'", config.OUTPUT_ENCODING == "utf-8-sig")
check("REASON_NONE is the empty string", config.REASON_NONE == "")
check(
    "EXCEPTION_REPORT_COLUMNS is exactly the 5 brief-specified columns, in order",
    config.EXCEPTION_REPORT_COLUMNS == ["file", "status", "reason", "missing_cols", "extra_cols"],
    str(config.EXCEPTION_REPORT_COLUMNS),
)
check(
    "config.py carries no list of the 32 data columns",
    not any(
        isinstance(getattr(config, name), (list, tuple)) and len(getattr(config, name)) > 5
        for name in dir(config)
        if not name.startswith("_") and name != "ACCEPTED_EXTENSIONS"
    ),
)

# --- models sanity ---
item = UploadedItem(index=0, name="Instacart_Bounty_scored.csv", data=b"x")
check("UploadedItem.stem strips the extension", item.stem == "Instacart_Bounty_scored", item.stem)
check("UploadedItem.extension is lowercased, incl. dot", item.extension == ".csv", item.extension)

item_no_ext = UploadedItem(index=1, name="notes", data=b"x")
check("UploadedItem.stem is verbatim when there is no extension", item_no_ext.stem == "notes", item_no_ext.stem)
check("UploadedItem.extension is '' when there is no extension", item_no_ext.extension == "", repr(item_no_ext.extension))

valid_candidate = MasterCandidate(index=0, name="Master_X.csv", readable=True, has_study_name=True, error="")
invalid_candidate = MasterCandidate(index=1, name="Master_Y.csv", readable=True, has_study_name=False, error="")
unreadable_candidate = MasterCandidate(index=2, name="Master_Z.csv", readable=False, has_study_name=False, error="boom")
check("MasterCandidate.is_valid is True when readable and has_study_name", valid_candidate.is_valid is True)
check("MasterCandidate.is_valid is False when has_study_name is False", invalid_candidate.is_valid is False)
check("MasterCandidate.is_valid is False when unreadable", unreadable_candidate.is_valid is False)

# --- FileReadError sanity ---
err = FileReadError(config.REASON_UNREADABLE, "boom")
check(
    "FileReadError carries .reason and .detail",
    err.reason == config.REASON_UNREADABLE and err.detail == "boom",
)

# ---------------------------------------------------------------------------
# SECTION 2 — Reading the real sample files
# ---------------------------------------------------------------------------
section("2. Reading Real Sample Files")

# The 31-name reference schema. Defined HERE AND NOWHERE ELSE (ARCHITECTURE.md
# section 1 / META_BRIEF.md section 4). config.py must never carry this list.
REFERENCE_STUDY_COLUMNS: list[str] = [
    "MODEL_DESC", "Model", "TIME_AGG_PERIOD", "START_WEEK", "END_WEEK", "dependent_variable",
    "CNT_EXPSD_HH", "UDJ_AVG_EXPSD_HH_PRE", "UDJ_AVG_CNTRL_HH_PRE", "UDJ_AVG_EXPSD_HH_PST",
    "UDJ_AVG_CNTRL_HH_PST", "UDJ_DOD_EFFCT", "UDJ_DIFF_EFFCT", "ADJ_MEAN_EXPSD_GRP",
    "ADJ_MEAN_CNTRL_GRP", "ADJ_DOD_EFFCT", "TWOTAIL_PVAL", "ONETAIL_PVAL", "ABS_DIFF", "DOL_DIFF",
    "ONETAIL_80_PCT_INTRVL_UB", "ONETAIL_80_PCT_INTRVL_LB", "ONETAIL_90_PCT_INTRVL_UB",
    "ONETAIL_90_PCT_INTRVL_LB", "TWOTAIL_80_PCT_INTRVL_UB", "TWOTAIL_80_PCT_INTRVL_LB",
    "TWOTAIL_90_PCT_INTRVL_UB", "TWOTAIL_90_PCT_INTRVL_LB", "CNT_IMPRESSIONS", "CNT_Model_HH",
    "Channels",
]
check("REFERENCE_STUDY_COLUMNS has exactly 31 entries", len(REFERENCE_STUDY_COLUMNS) == 31, f"got {len(REFERENCE_STUDY_COLUMNS)}")

STUDY_FILES: list[str] = [
    "Holly_Rancher 27382_Scored.csv",
    "Instacart - LOreal 1P_scored.csv",
    "Instacart - Nates Honey_scored.csv",
    "Instacart Firehook of Virginia_scored.csv",
    "Instacart_Bel Brands_scored.csv",
    "Instacart_Bounty_scored.csv",
    "Instacart_Cascade_scored.csv",
    "Instacart_GoGo Squeez_scored.csv",
    "Instacart_Planters_scored.csv",
    "Instacart_Stella Artois_scored.csv",
]
MASTER_FILES: list[str] = [
    "MaserFile_XXXX_DATE.csv",
    "Master_Instacart_2026-09-07_1200.csv",
]


def _all_cells_are_str(df) -> bool:
    return all(isinstance(v, str) for v in df.to_numpy().ravel())


check(f"{len(STUDY_FILES)} study sample files enumerated", len(STUDY_FILES) == 10, f"got {len(STUDY_FILES)}")

for filename in STUDY_FILES:
    path = SAMPLES_DIR / filename
    try:
        df = read_table(filename, path.read_bytes())
        check(f"{filename} reads via read_table", True, f"{len(df)} rows, {len(df.columns)} cols")
        check(
            f"{filename} has the 31 reference columns, in order",
            list(df.columns) == REFERENCE_STUDY_COLUMNS,
            "" if list(df.columns) == REFERENCE_STUDY_COLUMNS else f"got {list(df.columns)}",
        )
        check(f"{filename} every cell is str after _finalize", _all_cells_are_str(df))
    except Exception as e:
        check(f"{filename} reads via read_table", False, str(e))

for filename in MASTER_FILES:
    path = SAMPLES_DIR / filename
    try:
        df = read_table(filename, path.read_bytes())
        check(f"{filename} reads via read_table", True, f"{len(df)} rows, {len(df.columns)} cols")
        expected_columns = REFERENCE_STUDY_COLUMNS + [config.STUDY_NAME_COL]
        check(
            f"{filename} has 32 columns (31 reference + Study_Name)",
            list(df.columns) == expected_columns,
            "" if list(df.columns) == expected_columns else f"got {list(df.columns)}",
        )
        check(f"{filename} every cell is str after _finalize", _all_cells_are_str(df))
    except Exception as e:
        check(f"{filename} reads via read_table", False, str(e))

check(
    "The two master samples are byte-identical (per spec section 8 item 9)",
    (SAMPLES_DIR / "MaserFile_XXXX_DATE.csv").read_bytes()
    == (SAMPLES_DIR / "Master_Instacart_2026-09-07_1200.csv").read_bytes(),
)

# --- test_fixtures edge cases reachable through read_table alone (Phase 1 subset) ---
try:
    read_table(
        "reject_empty_file_scored.csv",
        (FIXTURES_DIR / "reject_empty_file_scored.csv").read_bytes(),
    )
    check("reject_empty_file_scored.csv raises FileReadError", False, "no exception was raised")
except FileReadError as e:
    check(
        "reject_empty_file_scored.csv raises REASON_EMPTY_FILE",
        e.reason == config.REASON_EMPTY_FILE,
        f"got reason={e.reason!r}",
    )
except Exception as e:
    check(
        "reject_empty_file_scored.csv raises REASON_EMPTY_FILE",
        False,
        f"wrong exception type: {type(e).__name__}: {e}",
    )

try:
    read_table("no_header_line.csv", b"\n\n\n")
    check("non-zero bytes with no header line raise FileReadError", False, "no exception was raised")
except FileReadError as e:
    check(
        "non-zero bytes with no header line raise REASON_EMPTY_FILE",
        e.reason == config.REASON_EMPTY_FILE,
        f"got reason={e.reason!r}",
    )
except Exception as e:
    check(
        "non-zero bytes with no header line raise REASON_EMPTY_FILE",
        False,
        f"wrong exception type: {type(e).__name__}: {e}",
    )

try:
    headers_only_df = read_table(
        "edge_headers_only_scored.csv",
        (FIXTURES_DIR / "edge_headers_only_scored.csv").read_bytes(),
    )
    check(
        "edge_headers_only_scored.csv returns an empty frame, NOT an error",
        len(headers_only_df) == 0,
        f"got {len(headers_only_df)} rows",
    )
    check(
        "edge_headers_only_scored.csv has the 31 reference columns populated",
        list(headers_only_df.columns) == REFERENCE_STUDY_COLUMNS,
        "" if list(headers_only_df.columns) == REFERENCE_STUDY_COLUMNS else f"got {list(headers_only_df.columns)}",
    )
except Exception as e:
    check("edge_headers_only_scored.csv returns an empty frame, NOT an error", False, str(e))

# ---------------------------------------------------------------------------
# SECTION 3 — Precision round-trip (BLOCKING — the Phase 1 QC gate)
# ---------------------------------------------------------------------------
section("3. Precision Round-Trip (BLOCKING)")

BOUNTY_FILE = SAMPLES_DIR / "Instacart_Bounty_scored.csv"

# Step 1: read raw with the stdlib csv module into list[dict[str, str]].
raw_rows: list[dict[str, str]] = []
try:
    with open(BOUNTY_FILE, "r", encoding="utf-8-sig", newline="") as f:
        raw_rows = list(csv.DictReader(f))
    check("Instacart_Bounty_scored.csv parsed with stdlib csv", True, f"{len(raw_rows)} rows")
except Exception as e:
    check("Instacart_Bounty_scored.csv parsed with stdlib csv", False, str(e))

# Step 2 (Phase 1 subset — only read_table exists; tag_study_name / align_to_master /
# process_batch / to_csv_bytes are Phase 2/4/5 and do not exist yet).
bounty_df = None
try:
    bounty_df = read_table(BOUNTY_FILE.name, BOUNTY_FILE.read_bytes())
    check("Instacart_Bounty_scored.csv read via read_table", True, f"{len(bounty_df)} rows")
except Exception as e:
    check("Instacart_Bounty_scored.csv read via read_table", False, str(e))

if raw_rows and bounty_df is not None:
    check(
        "read_table row count matches stdlib csv row count",
        len(bounty_df) == len(raw_rows),
        f"stdlib={len(raw_rows)} read_table={len(bounty_df)}",
    )

    # Step 4: every field of every row is string-identical — not float-equal.
    mismatches: list[tuple[int, str, str, str]] = []
    non_str_cells: list[tuple[int, str, type]] = []
    for i, raw_row in enumerate(raw_rows):
        for col in REFERENCE_STUDY_COLUMNS:
            raw_value = raw_row[col]
            table_value = bounty_df.iloc[i][col]
            if not isinstance(table_value, str):
                non_str_cells.append((i, col, type(table_value)))
            elif raw_value != table_value:
                mismatches.append((i, col, raw_value, table_value))

    check(
        "Every field of every row is a Python str",
        len(non_str_cells) == 0,
        f"{len(non_str_cells)} non-str cells, first: {non_str_cells[0]}" if non_str_cells else "",
    )
    check(
        "Every field of every row is string-identical to the source (31 cols)",
        len(mismatches) == 0,
        f"{len(mismatches)} mismatches, first: {mismatches[0]}" if mismatches else "",
    )

    # Step 5: the literal 17-significant-digit value survives verbatim.
    literal_present = any(
        (bounty_df[col] == "0.19163628728414203").any() for col in REFERENCE_STUDY_COLUMNS
    )
    check("Literal '0.19163628728414203' survives read_table verbatim", literal_present)
else:
    check("Precision round-trip", False, "skipped — source parse or read_table failed")

print(
    "\n[NOTE] QC CHECKPOINT steps 6-7 (Study_Name is the only field the output "
    "adds\nbeyond the source; to_csv_bytes(df)[:3] == UTF-8 BOM) are completed "
    "in Section 9\nbelow, now that schema.py, study_processor.py and "
    "csv_writer.py all exist (Phase 5)."
)

# ---------------------------------------------------------------------------
# SECTION 4 — schema.py unit checks                              [Phase 2]
# ---------------------------------------------------------------------------
section("4. Schema Unit Checks")

from schema import (
    SchemaError,
    normalize_column,
    build_column_index,
    compare_columns,
    tag_study_name,
    align_to_master,
)

MASTER_FILE = SAMPLES_DIR / "Master_Instacart_2026-09-07_1200.csv"
master_df = read_table(MASTER_FILE.name, MASTER_FILE.read_bytes())
MASTER_COLUMNS: list[str] = list(master_df.columns)
check(
    "Master sample has 32 columns (31 reference + Study_Name), in order",
    MASTER_COLUMNS == REFERENCE_STUDY_COLUMNS + [config.STUDY_NAME_COL],
    "" if MASTER_COLUMNS == REFERENCE_STUDY_COLUMNS + [config.STUDY_NAME_COL] else f"got {MASTER_COLUMNS}",
)

# --- normalize_column -------------------------------------------------------
check("normalize_column lowercases", normalize_column("ABS_DIFF") == "abs_diff", normalize_column("ABS_DIFF"))
check(
    "normalize_column strips leading/trailing whitespace",
    normalize_column("  ABS_DIFF  ") == "abs_diff",
    repr(normalize_column("  ABS_DIFF  ")),
)
check(
    "normalize_column collapses internal multi-space runs to one space",
    normalize_column("ABS   DIFF") == "abs diff",
    repr(normalize_column("ABS   DIFF")),
)
check(
    "normalize_column collapses mixed whitespace runs (tabs/newlines) to one space",
    normalize_column("ABS\t\n DIFF") == "abs diff",
    repr(normalize_column("ABS\t\n DIFF")),
)
check(
    "Two names differing only by case/whitespace normalize identically (collide)",
    normalize_column(" Study_Name ") == normalize_column("study_name"),
    f"{normalize_column(' Study_Name ')!r} vs {normalize_column('study_name')!r}",
)

# --- build_column_index -----------------------------------------------------
happy_index = build_column_index(["MODEL_DESC", "Model", "Study_Name"])
check(
    "build_column_index happy path maps normalized -> verbatim",
    happy_index == {"model_desc": "MODEL_DESC", "model": "Model", "study_name": "Study_Name"},
    str(happy_index),
)

try:
    build_column_index(["ABS_DIFF", "abs_diff"])
    check("build_column_index raises SchemaError on duplicate normalized names", False, "no exception was raised")
except SchemaError as e:
    check(
        "build_column_index raises SchemaError(REASON_DUPLICATE_COLUMNS) on duplicate normalized names",
        e.reason == config.REASON_DUPLICATE_COLUMNS,
        f"got reason={e.reason!r}",
    )
except Exception as e:
    check(
        "build_column_index raises SchemaError(REASON_DUPLICATE_COLUMNS) on duplicate normalized names",
        False,
        f"wrong exception type: {type(e).__name__}: {e}",
    )

# --- compare_columns against the deliberate reject fixtures -----------------
missing_cols_df = read_table(
    "reject_missing_column_scored.csv",
    (FIXTURES_DIR / "reject_missing_column_scored.csv").read_bytes(),
)
missing, extra = compare_columns(MASTER_COLUMNS, list(missing_cols_df.columns), optional=[config.STUDY_NAME_COL])
check("reject_missing_column_scored.csv: missing == ['ABS_DIFF']", missing == ["ABS_DIFF"], str(missing))
check("reject_missing_column_scored.csv: extra == []", extra == [], str(extra))

extra_cols_df = read_table(
    "reject_extra_column_scored.csv",
    (FIXTURES_DIR / "reject_extra_column_scored.csv").read_bytes(),
)
missing, extra = compare_columns(MASTER_COLUMNS, list(extra_cols_df.columns), optional=[config.STUDY_NAME_COL])
check("reject_extra_column_scored.csv: extra == ['RETAILER_ID']", extra == ["RETAILER_ID"], str(extra))
check("reject_extra_column_scored.csv: missing == []", missing == [], str(missing))

missing_and_extra_df = read_table(
    "reject_missing_and_extra_scored.csv",
    (FIXTURES_DIR / "reject_missing_and_extra_scored.csv").read_bytes(),
)
missing, extra = compare_columns(MASTER_COLUMNS, list(missing_and_extra_df.columns), optional=[config.STUDY_NAME_COL])
check("reject_missing_and_extra_scored.csv: missing == ['DOL_DIFF']", missing == ["DOL_DIFF"], str(missing))
check(
    "reject_missing_and_extra_scored.csv: extra == ['BANNER', 'REGION']",
    extra == ["BANNER", "REGION"],
    str(extra),
)

# --- optional exempts Study_Name for a normal 31-column study file ----------
bounty_for_compare = read_table(BOUNTY_FILE.name, BOUNTY_FILE.read_bytes())
missing, extra = compare_columns(MASTER_COLUMNS, list(bounty_for_compare.columns), optional=[config.STUDY_NAME_COL])
check(
    "optional exempts Study_Name: 31-col study file vs 32-col master reports no missing",
    missing == [],
    str(missing),
)
check("optional exempts Study_Name: no extra either", extra == [], str(extra))

# --- pass_reordered_columns_scored.csv: clean compare + full reorder --------
REORDERED_FILE = FIXTURES_DIR / "pass_reordered_columns_scored.csv"
reordered_df = read_table(REORDERED_FILE.name, REORDERED_FILE.read_bytes())
missing, extra = compare_columns(MASTER_COLUMNS, list(reordered_df.columns), optional=[config.STUDY_NAME_COL])
check("pass_reordered_columns_scored.csv compares clean: missing == []", missing == [], str(missing))
check("pass_reordered_columns_scored.csv compares clean: extra == []", extra == [], str(extra))

# align_to_master's own precondition check has no `optional` — it mirrors the
# real pipeline order (study_processor step 7): tag_study_name runs BEFORE
# align_to_master, so the frame already carries all 32 master columns by the
# time align_to_master sees it.
reordered_tagged = tag_study_name(reordered_df, "pass_reordered_columns_scored", config.STUDY_NAME_COL)
aligned_reordered = align_to_master(reordered_tagged, MASTER_COLUMNS)
check(
    "align_to_master restores exact master column order on the reversed fixture",
    list(aligned_reordered.columns) == MASTER_COLUMNS,
    "" if list(aligned_reordered.columns) == MASTER_COLUMNS else f"got {list(aligned_reordered.columns)}",
)

# --- value-integrity assertion: reordering never alters a single character --
value_mismatches: list[tuple[int, str, str, str]] = []
for col in reordered_df.columns:
    before = reordered_df[col].tolist()
    after = aligned_reordered[col].tolist()
    for row_idx, (b, a) in enumerate(zip(before, after)):
        if b != a:
            value_mismatches.append((row_idx, col, b, a))
check(
    "align_to_master value-integrity: every cell string-identical before/after reorder",
    len(value_mismatches) == 0,
    f"{len(value_mismatches)} mismatches, first: {value_mismatches[0]}" if value_mismatches else "",
)

# --- pass_messy_header_case_scored.csv: mixed case + padded whitespace -----
MESSY_FILE = FIXTURES_DIR / "pass_messy_header_case_scored.csv"
messy_df = read_table(MESSY_FILE.name, MESSY_FILE.read_bytes())
missing, extra = compare_columns(MASTER_COLUMNS, list(messy_df.columns), optional=[config.STUDY_NAME_COL])
check("pass_messy_header_case_scored.csv compares clean: missing == []", missing == [], str(missing))
check("pass_messy_header_case_scored.csv compares clean: extra == []", extra == [], str(extra))

messy_tagged = tag_study_name(messy_df, "pass_messy_header_case_scored", config.STUDY_NAME_COL)
aligned_messy = align_to_master(messy_tagged, MASTER_COLUMNS)
check(
    "align_to_master aligns the messy-case/whitespace fixture to master order",
    list(aligned_messy.columns) == MASTER_COLUMNS,
    "" if list(aligned_messy.columns) == MASTER_COLUMNS else f"got {list(aligned_messy.columns)}",
)

# --- tag_study_name -----------------------------------------------------
tagged = tag_study_name(bounty_for_compare, "Instacart_Bounty_scored", config.STUDY_NAME_COL)
check(
    "tag_study_name sets the column on every row",
    (tagged[config.STUDY_NAME_COL] == "Instacart_Bounty_scored").all(),
)
other_cols_untouched = all(
    tagged[col].tolist() == bounty_for_compare[col].tolist()
    for col in bounty_for_compare.columns
    if col != config.STUDY_NAME_COL
)
check("tag_study_name leaves every other column untouched", other_cols_untouched)

master_with_existing_study_name = tag_study_name(master_df, "Overwritten_Name", config.STUDY_NAME_COL)
check(
    "tag_study_name overwrites a pre-existing Study_Name column",
    (master_with_existing_study_name[config.STUDY_NAME_COL] == "Overwritten_Name").all(),
)
other_cols_untouched_master = all(
    master_with_existing_study_name[col].tolist() == master_df[col].tolist()
    for col in master_df.columns
    if col != config.STUDY_NAME_COL
)
check(
    "tag_study_name overwrite path leaves every other column untouched",
    other_cols_untouched_master,
)

# --- align_to_master raises SchemaError on a violated precondition ---------
try:
    align_to_master(missing_cols_df, MASTER_COLUMNS)
    check("align_to_master raises SchemaError when a column is missing", False, "no exception was raised")
except SchemaError as e:
    check(
        "align_to_master raises SchemaError(REASON_COLUMN_MISMATCH) when a column is missing",
        e.reason == config.REASON_COLUMN_MISMATCH,
        f"got reason={e.reason!r}",
    )
except Exception as e:
    check(
        "align_to_master raises SchemaError(REASON_COLUMN_MISMATCH) when a column is missing",
        False,
        f"wrong exception type: {type(e).__name__}: {e}",
    )

try:
    align_to_master(extra_cols_df, MASTER_COLUMNS)
    check("align_to_master raises SchemaError when a column is extra", False, "no exception was raised")
except SchemaError as e:
    check(
        "align_to_master raises SchemaError(REASON_COLUMN_MISMATCH) when a column is extra",
        e.reason == config.REASON_COLUMN_MISMATCH,
        f"got reason={e.reason!r}",
    )
except Exception as e:
    check(
        "align_to_master raises SchemaError(REASON_COLUMN_MISMATCH) when a column is extra",
        False,
        f"wrong exception type: {type(e).__name__}: {e}",
    )

# ---------------------------------------------------------------------------
# SECTION 5 — Master detection                                   [Phase 3]
# ---------------------------------------------------------------------------
section("5. Master Detection")

import pandas as pd

from master_detector import (
    find_master_candidates,
    parse_master_base_name,
    sanitize_base_name,
    build_master_context_from_existing,
    build_master_context_from_first_file,
    collect_existing_study_names,
)

MASTER_FILE_NAME = "Master_Instacart_2026-09-07_1200.csv"
MASER_TYPO_FILE_NAME = "MaserFile_XXXX_DATE.csv"

# --- parse_master_base_name: all four documented forms ----------------------
check(
    "parse_master_base_name: 'Master_Instacart_2026-09-07_1430.csv' -> 'Instacart'",
    parse_master_base_name("Master_Instacart_2026-09-07_1430.csv") == "Instacart",
    parse_master_base_name("Master_Instacart_2026-09-07_1430.csv"),
)
check(
    "parse_master_base_name: 'Master_Instacart.csv' -> 'Instacart' (no timestamp suffix)",
    parse_master_base_name("Master_Instacart.csv") == "Instacart",
    parse_master_base_name("Master_Instacart.csv"),
)
check(
    "parse_master_base_name: 'master_A_B_2026-09-07_1430.csv' -> 'A_B' (lowercase prefix + timestamp)",
    parse_master_base_name("master_A_B_2026-09-07_1430.csv") == "A_B",
    parse_master_base_name("master_A_B_2026-09-07_1430.csv"),
)
check(
    "parse_master_base_name: lowercase-prefixed variant with no timestamp keeps the whole remainder",
    parse_master_base_name("master_simplename.csv") == "simplename",
    parse_master_base_name("master_simplename.csv"),
)
check(
    "parse_master_base_name: prefix stripped case-insensitively on the real sample master",
    parse_master_base_name(MASTER_FILE_NAME) == "Instacart",
    parse_master_base_name(MASTER_FILE_NAME),
)

# --- sanitize_base_name ------------------------------------------------------
check(
    "sanitize_base_name replaces every illegal character with the replacement char",
    sanitize_base_name('A<B>C:D"E/F\\G|H?I*J') == "A_B_C_D_E_F_G_H_I_J",
    sanitize_base_name('A<B>C:D"E/F\\G|H?I*J'),
)
check(
    "sanitize_base_name collapses repeated replacement characters into one",
    sanitize_base_name("A///B") == "A_B",
    sanitize_base_name("A///B"),
)
check(
    "sanitize_base_name strips leading/trailing whitespace",
    sanitize_base_name("  Instacart  ") == "Instacart",
    repr(sanitize_base_name("  Instacart  ")),
)
check(
    "sanitize_base_name strips trailing dots and spaces",
    sanitize_base_name("Instacart..  ") == "Instacart",
    repr(sanitize_base_name("Instacart..  ")),
)

# --- sanitize_base_name on pathological all-illegal-character inputs --------
# Fix (post-215 QC): a typed study name of "..." sanitizes to "" because dots
# are not in config.ILLEGAL_FILENAME_CHARS and are stripped entirely by the
# trailing .rstrip(". ") — that empty base_name used to flow straight into
# build_master_filename() unguarded, producing an unlabeled
# "Master__<timestamp>.csv". Verified behaviour below: only pure-dot /
# whitespace-and-dot inputs sanitize to "" — inputs made only of characters
# from ILLEGAL_FILENAME_CHARS (e.g. "*", "/") sanitize to a single "_"
# (replacement char, collapsed), which is non-empty and a legal — if terse —
# base name. Both shapes are asserted here so the distinction is locked in;
# the app.py gate below only rejects the true "" case.
check(
    'sanitize_base_name(\'...\') == \'\' (pure dots strip away entirely)',
    sanitize_base_name("...") == "",
    repr(sanitize_base_name("...")),
)
check(
    "sanitize_base_name('   ...   ') == '' (whitespace + dots, both stripped)",
    sanitize_base_name("   ...   ") == "",
    repr(sanitize_base_name("   ...   ")),
)
check(
    "sanitize_base_name('***') == '_' (illegal chars collapse to one replacement char, not empty)",
    sanitize_base_name("***") == "_",
    repr(sanitize_base_name("***")),
)
check(
    "sanitize_base_name('///') == '_' (illegal chars collapse to one replacement char, not empty)",
    sanitize_base_name("///") == "_",
    repr(sanitize_base_name("///")),
)
check(
    "sanitize_base_name('<<<>>>') == '_' (illegal chars collapse to one replacement char, not empty)",
    sanitize_base_name("<<<>>>") == "_",
    repr(sanitize_base_name("<<<>>>")),
)


def _first_master_gate_passes(typed_name: str) -> bool:
    """Mirrors app.py STEP 2b's first-master gate exactly (app.py cannot be
    imported here — it is the only module allowed to import streamlit and
    executes top-level Streamlit calls on import). When this returns False,
    app.py leaves `master` at None: Run stays disabled, no st.stop(), no
    default name substitution, and build_master_filename() is never reached.
    """
    return bool(typed_name.strip()) and bool(sanitize_base_name(typed_name))


for _pathological_name, _expect_gate_pass in [
    ("...", False),
    ("   ...   ", False),
    ("***", True),
    ("///", True),
    ("<<<>>>", True),
    ("Instacart", True),   # control: an ordinary name must still pass
    ("", False),           # control: blank was already rejected pre-fix
    ("   ", False),        # control: whitespace-only was already rejected pre-fix
]:
    check(
        f"first-master gate on {_pathological_name!r}: "
        f"{'passes (build_master_filename reachable)' if _expect_gate_pass else 'blocked (build_master_filename never reached)'}",
        _first_master_gate_passes(_pathological_name) is _expect_gate_pass,
        _first_master_gate_passes(_pathological_name),
    )

# For every input the gate blocks, prove the danger it prevents: applying
# build_master_filename directly to the unguarded sanitized result would have
# produced the unlabeled "Master__<timestamp>.csv" artifact described in the
# defect report.
from datetime import datetime as _datetime_s5
from csv_writer import build_master_filename

_fixed_now = _datetime_s5(2026, 9, 7, 14, 30)
for _blocked_name in ("...", "   ...   "):
    _unguarded_filename = build_master_filename(sanitize_base_name(_blocked_name), _fixed_now)
    check(
        f"unguarded build_master_filename({_blocked_name!r}) would yield the "
        "unlabeled 'Master__...' artifact the gate exists to prevent",
        _unguarded_filename == "Master__2026-09-07_1430.csv",
        _unguarded_filename,
    )
    check(
        f"the gate blocks {_blocked_name!r} before that call is ever reached",
        _first_master_gate_passes(_blocked_name) is False,
    )

# --- resume-path safety: parse_master_base_name has no sanitize step -------
# Checked per the task's instruction to confirm (not assume) the resume path
# is safe. Finding: parse_master_base_name CAN return "" — a filename like
# "master_.csv" has the entire stem consumed by the prefix, leaving an empty
# remainder that MASTER_TIMESTAMP_SUFFIX_RE (which requires 1+ chars via
# `.+`) does not match, so the empty remainder is returned as-is. This is a
# real, reachable case (not merely a shape lookalike), so app.py STEP 3 warns
# on it (see app.py: "master.base_name has no usable name" branch).
check(
    "parse_master_base_name('master_.csv') == '' — resume-path base_name can be empty",
    parse_master_base_name("master_.csv") == "",
    repr(parse_master_base_name("master_.csv")),
)
check(
    "parse_master_base_name('Master_.csv') == '' — case-insensitive prefix, same empty result",
    parse_master_base_name("Master_.csv") == "",
    repr(parse_master_base_name("Master_.csv")),
)


def _resume_path_needs_warning(filename: str) -> bool:
    """Mirrors app.py STEP 3's resume-path safety check for a master whose
    base_name parsed empty (created_this_run is always False on this path)."""
    return not parse_master_base_name(filename).strip()


check(
    "resume-path warning predicate fires for 'master_.csv'",
    _resume_path_needs_warning("master_.csv") is True,
)
check(
    "resume-path warning predicate does NOT fire for the real sample master filename",
    _resume_path_needs_warning(MASTER_FILE_NAME) is False,
)

# --- zero-candidate path: only study files -----------------------------------
zero_candidate_items = [
    UploadedItem(index=i, name=name, data=(SAMPLES_DIR / name).read_bytes())
    for i, name in enumerate(STUDY_FILES)
]
zero_candidates = find_master_candidates(zero_candidate_items)
check(
    "zero-candidate path: a batch of only study files yields no candidates",
    zero_candidates == [],
    str(zero_candidates),
)

# --- one-candidate path -------------------------------------------------------
one_candidate_items = zero_candidate_items + [
    UploadedItem(
        index=len(zero_candidate_items),
        name=MASTER_FILE_NAME,
        data=(SAMPLES_DIR / MASTER_FILE_NAME).read_bytes(),
    )
]
one_candidates = find_master_candidates(one_candidate_items)
one_valid = [c for c in one_candidates if c.is_valid]
check(
    "one-candidate path: exactly one valid candidate found",
    len(one_valid) == 1,
    str(one_candidates),
)
check(
    "one-candidate path: base_name parses to 'Instacart'",
    bool(one_valid) and parse_master_base_name(one_valid[0].name) == "Instacart",
    parse_master_base_name(one_valid[0].name) if one_valid else "no valid candidate",
)

# --- two-candidate path: second file built in memory, never written to disk -
master_bytes = (SAMPLES_DIR / MASTER_FILE_NAME).read_bytes()
two_candidate_items = [
    UploadedItem(index=0, name=MASTER_FILE_NAME, data=master_bytes),
    UploadedItem(index=1, name="Master_Second_2026-09-07_1300.csv", data=master_bytes),
]
two_candidates = find_master_candidates(two_candidate_items)
two_valid = [c for c in two_candidates if c.is_valid]
check(
    "two-candidate path: two differently-named Master_* files both returned as valid",
    len(two_valid) == 2,
    str(two_candidates),
)

# --- the 'Maser' typo is correctly NOT detected ------------------------------
maser_items = [
    UploadedItem(
        index=0,
        name=MASER_TYPO_FILE_NAME,
        data=(SAMPLES_DIR / MASER_TYPO_FILE_NAME).read_bytes(),
    )
]
maser_candidates = find_master_candidates(maser_items)
check(
    "'MaserFile_XXXX_DATE.csv' is NOT detected as a master candidate ('maserfile_' != 'master_')",
    maser_candidates == [],
    str(maser_candidates),
)

# --- Master_-prefixed file lacking Study_Name --------------------------------
no_study_name_item = UploadedItem(
    index=0,
    name="Master_NoStudyName.csv",
    data=(SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes(),
)
no_study_name_candidates = find_master_candidates([no_study_name_item])
check(
    "Master_-prefixed file lacking Study_Name still appears as a candidate",
    len(no_study_name_candidates) == 1,
    str(no_study_name_candidates),
)
if no_study_name_candidates:
    c = no_study_name_candidates[0]
    check("... it is readable", c.readable is True)
    check("... has_study_name is False", c.has_study_name is False)
    check("... is_valid is False", c.is_valid is False)

# --- unreadable Master_-prefixed file: find_master_candidates must not raise
unreadable_master_item = UploadedItem(index=0, name="Master_Empty.csv", data=b"")
unreadable_master_candidates = find_master_candidates([unreadable_master_item])
check(
    "find_master_candidates does not raise on an unreadable Master_-prefixed file",
    len(unreadable_master_candidates) == 1,
    str(unreadable_master_candidates),
)
if unreadable_master_candidates:
    c = unreadable_master_candidates[0]
    check("... readable is False", c.readable is False)
    check("... error is populated", c.error != "", repr(c.error))
    check("... is_valid is False", c.is_valid is False)

# --- Master_-prefixed file that reads fine but has duplicate normalized -----
# columns. Coverage gap closed per Phase 3 QC follow-up: this path was only
# verified by hand before (find_master_candidates catches SchemaError from
# build_column_index before `readable` is ever set True). Built in memory
# from a real study file's bytes — never written to disk.
import io as _io

duplicate_source_bytes = (SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes()
duplicate_source_text = duplicate_source_bytes.decode("utf-8-sig")
duplicate_source_rows = list(csv.reader(_io.StringIO(duplicate_source_text)))
duplicate_header = duplicate_source_rows[0]
abs_diff_index = duplicate_header.index("ABS_DIFF")

# Append a second column that normalizes to the same key as ABS_DIFF, plus
# Study_Name — so the only reason this candidate fails is the duplication.
duplicate_header_with_dupe = duplicate_header + ["Abs_Diff", config.STUDY_NAME_COL]
duplicate_data_rows = [
    row + [row[abs_diff_index], "Some_Study"] for row in duplicate_source_rows[1:]
]

duplicate_output = _io.StringIO()
csv.writer(duplicate_output).writerows([duplicate_header_with_dupe] + duplicate_data_rows)
duplicate_columns_bytes = duplicate_output.getvalue().encode("utf-8-sig")

duplicate_columns_item = UploadedItem(
    index=0, name="Master_DuplicateCols.csv", data=duplicate_columns_bytes
)
duplicate_columns_candidates = find_master_candidates([duplicate_columns_item])
check(
    "find_master_candidates does not raise on a Master_-prefixed file with duplicate normalized columns",
    len(duplicate_columns_candidates) == 1,
    str(duplicate_columns_candidates),
)
if duplicate_columns_candidates:
    c = duplicate_columns_candidates[0]
    check("... readable is False (duplicate ABS_DIFF/Abs_Diff columns)", c.readable is False)
    check("... is_valid is False", c.is_valid is False)
    check(
        "... error names both offending columns",
        c.error != "" and "ABS_DIFF" in c.error and "Abs_Diff" in c.error,
        repr(c.error),
    )

# --- build_master_context_from_existing on the real master -------------------
real_master_item = UploadedItem(
    index=0, name=MASTER_FILE_NAME, data=(SAMPLES_DIR / MASTER_FILE_NAME).read_bytes()
)
existing_context = build_master_context_from_existing(real_master_item)
check(
    "build_master_context_from_existing: 32 columns, in file order",
    existing_context.columns == REFERENCE_STUDY_COLUMNS + [config.STUDY_NAME_COL],
    "" if existing_context.columns == REFERENCE_STUDY_COLUMNS + [config.STUDY_NAME_COL] else str(existing_context.columns),
)
check(
    "build_master_context_from_existing: 52 rows",
    len(existing_context.frame) == 52,
    len(existing_context.frame),
)
check(
    "build_master_context_from_existing: created_this_run is False",
    existing_context.created_this_run is False,
)
check(
    "build_master_context_from_existing: base_name == 'Instacart'",
    existing_context.base_name == "Instacart",
    existing_context.base_name,
)
check(
    "build_master_context_from_existing: existing_study_names has exactly one normalized entry",
    existing_context.existing_study_names == {"holly_rancher 27382_scored"},
    str(existing_context.existing_study_names),
)

# --- build_master_context_from_first_file on a 31-column study file ---------
bounty_item = UploadedItem(
    index=0,
    name="Instacart_Bounty_scored.csv",
    data=(SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes(),
)
bounty_original_df = read_table(bounty_item.name, bounty_item.data)
first_file_context = build_master_context_from_first_file(bounty_item, "Instacart")
check(
    "build_master_context_from_first_file: Study_Name appended LAST as column 32",
    len(first_file_context.columns) == 32 and first_file_context.columns[-1] == config.STUDY_NAME_COL,
    str(first_file_context.columns),
)
check(
    "build_master_context_from_first_file: every row's Study_Name set to the file's stem",
    (first_file_context.frame[config.STUDY_NAME_COL] == bounty_item.stem).all(),
)
check(
    "build_master_context_from_first_file: created_this_run is True",
    first_file_context.created_this_run is True,
)
check(
    "build_master_context_from_first_file: base_name sanitized from the typed name",
    first_file_context.base_name == "Instacart",
    first_file_context.base_name,
)

first_file_value_mismatches: list[tuple[int, str, str, str]] = []
for col in REFERENCE_STUDY_COLUMNS:
    before = bounty_original_df[col].tolist()
    after = first_file_context.frame[col].tolist()
    for row_idx, (b, a) in enumerate(zip(before, after)):
        if b != a:
            first_file_value_mismatches.append((row_idx, col, b, a))
check(
    "build_master_context_from_first_file: every pre-existing value is character-identical to the source",
    len(first_file_value_mismatches) == 0,
    f"{len(first_file_value_mismatches)} mismatches, first: {first_file_value_mismatches[0]}" if first_file_value_mismatches else "",
)

# --- build_master_context_from_first_file on a file that ALREADY has Study_Name
# This is the guard for DESIGN DEFAULT section 8 item 2: the column and its
# values must be left completely untouched, not overwritten with the item's
# stem. Uses the real Holly_Rancher master sample as the "chosen first file".
already_tagged_item = UploadedItem(
    index=0,
    name=MASER_TYPO_FILE_NAME,
    data=(SAMPLES_DIR / MASER_TYPO_FILE_NAME).read_bytes(),
)
already_tagged_probe = read_table(already_tagged_item.name, already_tagged_item.data)
already_tagged_context = build_master_context_from_first_file(already_tagged_item, "SomeTypedName")
check(
    "pre-existing Study_Name column keeps its original position (not moved/re-appended)",
    list(already_tagged_context.frame.columns) == list(already_tagged_probe.columns),
    str(list(already_tagged_context.frame.columns)),
)
check(
    "pre-existing Study_Name values are untouched: all 52 rows still 'Holly_Rancher 27382_Scored'",
    (already_tagged_context.frame[config.STUDY_NAME_COL] == "Holly_Rancher 27382_Scored").sum() == 52,
    str(already_tagged_context.frame[config.STUDY_NAME_COL].value_counts().to_dict()),
)
check(
    "pre-existing Study_Name values were NOT overwritten with the item's stem 'MaserFile_XXXX_DATE'",
    not (already_tagged_context.frame[config.STUDY_NAME_COL] == "MaserFile_XXXX_DATE").any(),
)
check(
    "pre-existing Study_Name values were NOT overwritten with 'Master_Instacart_2026-09-07_1200'",
    not (already_tagged_context.frame[config.STUDY_NAME_COL] == "Master_Instacart_2026-09-07_1200").any(),
)

# --- collect_existing_study_names --------------------------------------------
study_name_probe_frame = pd.DataFrame(
    {config.STUDY_NAME_COL: ["Alpha", " alpha ", "", "   ", "Beta", "ALPHA"]}
)
collected_names = collect_existing_study_names(study_name_probe_frame, config.STUDY_NAME_COL)
check(
    "collect_existing_study_names excludes blanks and normalizes case/whitespace variants together",
    collected_names == {"alpha", "beta"},
    str(collected_names),
)

# ---------------------------------------------------------------------------
# SECTION 6 — Full batch processing                              [Phase 4]
# ---------------------------------------------------------------------------
section("6. Full Batch Processing")

from study_processor import process_file, process_batch


def _make_study_items(names: list[str]) -> list[UploadedItem]:
    return [
        UploadedItem(index=i, name=name, data=(SAMPLES_DIR / name).read_bytes())
        for i, name in enumerate(names)
    ]


def _fresh_master() -> MasterContext:
    master_item = UploadedItem(
        index=999,
        name=MASTER_FILE_NAME,
        data=(SAMPLES_DIR / MASTER_FILE_NAME).read_bytes(),
    )
    return build_master_context_from_existing(master_item)


# --- 10 study files into the real master -------------------------------------
full_batch_master = _fresh_master()
full_batch_items = _make_study_items(STUDY_FILES)
full_batch_study_names = {item.index: item.stem for item in full_batch_items}

expected_master_rows = len(full_batch_master.frame)

# NOTE: the real Master_Instacart_2026-09-07_1200.csv is byte-identical to
# MaserFile_XXXX_DATE.csv (spec section 8 item 9), i.e. it already contains
# Holly_Rancher's 52 rows under Study_Name "Holly_Rancher 27382_Scored"
# (confirmed in section 5: existing_study_names == {'holly_rancher 27382_scored'}).
# Feeding the real Holly_Rancher_27382_Scored.csv study file with its default
# stem name therefore collides with that pre-existing entry and is correctly
# skipped per decision 12 — it is NOT a clean 10-for-10 append. This is the
# exact same collision mechanic pinned down explicitly in THE TRAP below;
# it also fires here in the plain 10-file run because it happens to be the
# real sample master, not a synthetic empty one. Computed, not assumed:
already_present_files = [
    name for name in STUDY_FILES
    if Path(name).stem.strip().casefold() in full_batch_master.existing_study_names
]
expected_appended_files = [name for name in STUDY_FILES if name not in already_present_files]
expected_appended_count = len(expected_appended_files)
expected_study_rows_appended = sum(
    len(read_table(name, (SAMPLES_DIR / name).read_bytes())) for name in expected_appended_files
)
expected_total_rows = expected_master_rows + expected_study_rows_appended

full_batch_result = process_batch(full_batch_items, full_batch_master, full_batch_study_names)

check(
    "full batch: pre-existing collision detected — exactly 'Holly_Rancher 27382_Scored.csv' "
    "already lives in the real sample master",
    already_present_files == ["Holly_Rancher 27382_Scored.csv"],
    str(already_present_files),
)
check(
    "full batch: files not already in the master all append; the one pre-existing collision "
    "is skipped, 0 rejected",
    full_batch_result.appended == expected_appended_count
    and full_batch_result.skipped == len(already_present_files)
    and full_batch_result.rejected == 0,
    f"appended={full_batch_result.appended} skipped={full_batch_result.skipped} rejected={full_batch_result.rejected}",
)
check(
    "full batch: final row count == master rows + sum of the non-colliding files' data rows "
    "(computed from the files and the master's existing_study_names, not hardcoded)",
    len(full_batch_result.master_df) == expected_total_rows,
    f"expected={expected_total_rows} got={len(full_batch_result.master_df)}",
)
check(
    "full batch: total_records matches len(master_df)",
    full_batch_result.total_records == len(full_batch_result.master_df),
)
check(
    "full batch: master_df column order matches master's 32 columns exactly",
    list(full_batch_result.master_df.columns) == full_batch_master.columns,
    "" if list(full_batch_result.master_df.columns) == full_batch_master.columns else str(list(full_batch_result.master_df.columns)),
)
check(
    "full batch: rows_appended equals the sum of the non-colliding files' data rows",
    full_batch_result.rows_appended == expected_study_rows_appended,
    f"expected={expected_study_rows_appended} got={full_batch_result.rows_appended}",
)

# --- idempotency: feed the resulting master back in with the same 10 files --
rerun_master = MasterContext(
    frame=full_batch_result.master_df,
    columns=full_batch_master.columns,
    column_index=build_column_index(full_batch_master.columns),
    base_name=full_batch_master.base_name,
    source_file=full_batch_master.source_file,
    source_index=-1,
    existing_study_names=collect_existing_study_names(full_batch_result.master_df, config.STUDY_NAME_COL),
    created_this_run=False,
)
rerun_items = _make_study_items(STUDY_FILES)
rerun_study_names = {item.index: item.stem for item in rerun_items}
rerun_result = process_batch(rerun_items, rerun_master, rerun_study_names)

check(
    "idempotency: re-running the same batch appends 0 files",
    rerun_result.appended == 0,
    f"appended={rerun_result.appended}",
)
check(
    "idempotency: all 10 files are skipped / already in master",
    all(
        o.status == config.STATUS_SKIPPED and o.reason == config.REASON_ALREADY_IN_MASTER
        for o in rerun_result.outcomes
    ),
    str([(o.file, o.status, o.reason) for o in rerun_result.outcomes]),
)
check(
    "idempotency: row count is unchanged after the re-run",
    len(rerun_result.master_df) == len(full_batch_result.master_df),
    f"before={len(full_batch_result.master_df)} after={len(rerun_result.master_df)}",
)

# --- first-master path: a study file designated as the first master ---------
first_master_items = _make_study_items(STUDY_FILES)
BOUNTY_INDEX = STUDY_FILES.index("Instacart_Bounty_scored.csv")
first_master_ctx = build_master_context_from_first_file(first_master_items[BOUNTY_INDEX], "Instacart")
first_master_study_names = {item.index: item.stem for item in first_master_items}
first_master_result = process_batch(first_master_items, first_master_ctx, first_master_study_names)

check(
    "first-master path: the designated master file appears in NO outcome",
    all(o.index != BOUNTY_INDEX for o in first_master_result.outcomes),
    str([(o.index, o.file) for o in first_master_result.outcomes if o.index == BOUNTY_INDEX]),
)
expected_bounty_rows = len(
    read_table("Instacart_Bounty_scored.csv", (SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes())
)
bounty_rows_in_master = (
    first_master_result.master_df[config.STUDY_NAME_COL] == "Instacart_Bounty_scored"
).sum()
check(
    "first-master path: its rows appear exactly once, not twice",
    bounty_rows_in_master == expected_bounty_rows,
    f"expected={expected_bounty_rows} got={bounty_rows_in_master}",
)
check(
    "first-master path: 9 other files appended (Bounty itself excluded structurally)",
    first_master_result.appended == 9,
    f"appended={first_master_result.appended}",
)

# --- THE TRAP (spec section 8 item 9) ----------------------------------------
ALL_12_FILES = STUDY_FILES + ["MaserFile_XXXX_DATE.csv", "Master_Instacart_2026-09-07_1200.csv"]
trap_items = _make_study_items(ALL_12_FILES)
MASER_INDEX = ALL_12_FILES.index("MaserFile_XXXX_DATE.csv")
MASTER_INDEX_IN_TRAP = ALL_12_FILES.index("Master_Instacart_2026-09-07_1200.csv")
HOLLY_INDEX = ALL_12_FILES.index("Holly_Rancher 27382_Scored.csv")

trap_master_ctx = build_master_context_from_existing(trap_items[MASTER_INDEX_IN_TRAP])
trap_study_names = {item.index: item.stem for item in trap_items}
trap_result = process_batch(trap_items, trap_master_ctx, trap_study_names)

check(
    "THE TRAP: the selected master file produces no outcome (excluded by source_index)",
    all(o.index != MASTER_INDEX_IN_TRAP for o in trap_result.outcomes),
)
maser_outcome = next((o for o in trap_result.outcomes if o.index == MASER_INDEX), None)
check(
    "THE TRAP: MaserFile_XXXX_DATE.csv falls through as a study file and IS appended",
    maser_outcome is not None and maser_outcome.status == config.STATUS_APPENDED,
    str(maser_outcome),
)
check(
    "THE TRAP: MaserFile_XXXX_DATE.csv's Study_Name is overwritten to its own stem",
    maser_outcome is not None and maser_outcome.study_name == "MaserFile_XXXX_DATE",
    maser_outcome.study_name if maser_outcome else "no outcome",
)
duplicated_rows = (trap_result.master_df[config.STUDY_NAME_COL] == "MaserFile_XXXX_DATE").sum()
check(
    "THE TRAP: Holly_Rancher's 52 rows are duplicated under the second name 'MaserFile_XXXX_DATE'",
    duplicated_rows == 52,
    f"got {duplicated_rows}",
)
holly_outcome = next((o for o in trap_result.outcomes if o.index == HOLLY_INDEX), None)
check(
    "THE TRAP: the real Holly_Rancher study file is skipped as already in master "
    "(its Study_Name already exists in the loaded master)",
    holly_outcome is not None
    and holly_outcome.status == config.STATUS_SKIPPED
    and holly_outcome.reason == config.REASON_ALREADY_IN_MASTER,
    str(holly_outcome),
)
expected_trap_total_rows = expected_total_rows + duplicated_rows  # Maser's duplicate re-adds
# exactly what Holly_Rancher's own-file skip withheld (both are 52 rows), so the total
# lands back on "master + all 9 non-Holly files + one duplicate copy of Holly's 52 rows".
check(
    "THE TRAP: final row count == master rows + non-colliding study files' rows + "
    "Maser's 52 duplicated rows",
    len(trap_result.master_df) == expected_trap_total_rows,
    f"expected={expected_trap_total_rows} got={len(trap_result.master_df)}",
)

# --- duplicate within one batch: two items forced to the same Study_Name ----
dup_batch_master = _fresh_master()
dup_item_a = UploadedItem(
    index=0, name="Instacart_Cascade_scored.csv",
    data=(SAMPLES_DIR / "Instacart_Cascade_scored.csv").read_bytes(),
)
dup_item_b = UploadedItem(
    index=1, name="Instacart_GoGo Squeez_scored.csv",
    data=(SAMPLES_DIR / "Instacart_GoGo Squeez_scored.csv").read_bytes(),
)
dup_batch_study_names = {0: "Same_Study_Name", 1: "Same_Study_Name"}
dup_batch_result = process_batch([dup_item_a, dup_item_b], dup_batch_master, dup_batch_study_names)

check(
    "duplicate in batch: the first file (upload order) appends",
    dup_batch_result.outcomes[0].status == config.STATUS_APPENDED,
    str(dup_batch_result.outcomes[0]),
)
check(
    "duplicate in batch: the second file is skipped / duplicate in batch",
    dup_batch_result.outcomes[1].status == config.STATUS_SKIPPED
    and dup_batch_result.outcomes[1].reason == config.REASON_DUPLICATE_IN_BATCH,
    str(dup_batch_result.outcomes[1]),
)

# --- excluded_indices / excluded_outcomes: unselected master candidate ------
# ZERO test coverage before this. These two params exist to support
# ARCHITECTURE.md section 4 edge case 5 / section 8 item 5: two valid master
# candidates found, the user picks one via app.py's (Phase 5) st.selectbox,
# and the unselected one must be excluded from processing and reported as
# skipped / REASON_NOT_SELECTED_MASTER. Simulated here without app.py.
excluded_master_bytes = master_bytes  # real master bytes, reused in memory (never written to disk)
excluded_second_master_name = "Master_Unselected_2026-09-07_1300.csv"

EXCL_MASTER_INDEX = 0
EXCL_BOUNTY_INDEX = 1
EXCL_CASCADE_INDEX = 2
EXCL_SECOND_MASTER_INDEX = 3

excluded_batch_items = [
    UploadedItem(index=EXCL_MASTER_INDEX, name=MASTER_FILE_NAME, data=excluded_master_bytes),
    UploadedItem(
        index=EXCL_BOUNTY_INDEX, name="Instacart_Bounty_scored.csv",
        data=(SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes(),
    ),
    UploadedItem(
        index=EXCL_CASCADE_INDEX, name="Instacart_Cascade_scored.csv",
        data=(SAMPLES_DIR / "Instacart_Cascade_scored.csv").read_bytes(),
    ),
    UploadedItem(
        index=EXCL_SECOND_MASTER_INDEX, name=excluded_second_master_name,
        data=excluded_master_bytes,
    ),
]
excluded_batch_master = build_master_context_from_existing(excluded_batch_items[EXCL_MASTER_INDEX])
check(
    "excluded_indices setup: master.source_index == the real master's index (0)",
    excluded_batch_master.source_index == EXCL_MASTER_INDEX,
    excluded_batch_master.source_index,
)

excluded_batch_study_names = {
    EXCL_BOUNTY_INDEX: "Instacart_Bounty_scored",
    EXCL_CASCADE_INDEX: "Instacart_Cascade_scored",
}
excluded_second_master_outcome = FileOutcome(
    file=excluded_second_master_name,
    index=EXCL_SECOND_MASTER_INDEX,
    status=config.STATUS_SKIPPED,
    reason=config.REASON_NOT_SELECTED_MASTER,
    missing_cols=[],
    extra_cols=[],
    study_name="",
    rows=0,
)

excluded_batch_result = process_batch(
    excluded_batch_items,
    excluded_batch_master,
    excluded_batch_study_names,
    excluded_indices={EXCL_SECOND_MASTER_INDEX},
    excluded_outcomes=[excluded_second_master_outcome],
)

check(
    "excluded_indices: master.source_index (0) produces no outcome, independently of "
    "excluded_indices (which only contains 3)",
    all(o.index != EXCL_MASTER_INDEX for o in excluded_batch_result.outcomes),
    str([(o.index, o.file) for o in excluded_batch_result.outcomes if o.index == EXCL_MASTER_INDEX]),
)
check(
    "excluded_indices: the unselected second master (index 3) is NOT processed — its rows "
    "(a duplicate of Holly_Rancher's 52) do not appear in master_df",
    (excluded_batch_result.master_df[config.STUDY_NAME_COL] == excluded_second_master_name).sum() == 0,
)
check(
    "excluded_outcomes: the supplied FileOutcome for the unselected master is present "
    "verbatim in result.outcomes",
    excluded_second_master_outcome in excluded_batch_result.outcomes,
    str(excluded_batch_result.outcomes),
)
check(
    "excluded_outcomes: outcomes remain sorted by index after merging",
    [o.index for o in excluded_batch_result.outcomes]
    == sorted(o.index for o in excluded_batch_result.outcomes),
    str([o.index for o in excluded_batch_result.outcomes]),
)

expected_excluded_bounty_rows = len(
    read_table("Instacart_Bounty_scored.csv", (SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes())
)
expected_excluded_cascade_rows = len(
    read_table("Instacart_Cascade_scored.csv", (SAMPLES_DIR / "Instacart_Cascade_scored.csv").read_bytes())
)
expected_excluded_total_rows = (
    len(excluded_batch_master.frame) + expected_excluded_bounty_rows + expected_excluded_cascade_rows
)
check(
    "excluded_indices/excluded_outcomes: appended/skipped/total_files reconcile — 2 real "
    "study files appended, 1 injected skipped outcome, 3 total outcomes, 0 rejected",
    excluded_batch_result.appended == 2
    and excluded_batch_result.skipped == 1
    and excluded_batch_result.rejected == 0
    and excluded_batch_result.total_files == 3,
    f"appended={excluded_batch_result.appended} skipped={excluded_batch_result.skipped} "
    f"rejected={excluded_batch_result.rejected} total_files={excluded_batch_result.total_files}",
)
check(
    "excluded_indices/excluded_outcomes: final row count == master rows + the two real "
    "study files' rows only (the excluded second master contributes nothing)",
    len(excluded_batch_result.master_df) == expected_excluded_total_rows,
    f"expected={expected_excluded_total_rows} got={len(excluded_batch_result.master_df)}",
)

# ---------------------------------------------------------------------------
# SECTION 7 — Edge-case fixtures (full set)                      [Phase 4]
# ---------------------------------------------------------------------------
section("7. Edge-Case Fixtures — Full Set")

edge_case_master = _fresh_master()


def _fixture_item(name: str, index: int = 0) -> UploadedItem:
    return UploadedItem(index=index, name=name, data=(FIXTURES_DIR / name).read_bytes())


# --- the three rejection fixtures: column mismatch with correct missing/extra
reject_missing_item = _fixture_item("reject_missing_column_scored.csv")
_, reject_missing_outcome = process_file(
    reject_missing_item, edge_case_master, "reject_missing_column_scored", set()
)
check(
    "reject_missing_column_scored.csv: rejected / column mismatch",
    reject_missing_outcome.status == config.STATUS_REJECTED
    and reject_missing_outcome.reason == config.REASON_COLUMN_MISMATCH,
    str(reject_missing_outcome),
)
check(
    "reject_missing_column_scored.csv: missing_cols == ['ABS_DIFF']",
    reject_missing_outcome.missing_cols == ["ABS_DIFF"],
    str(reject_missing_outcome.missing_cols),
)
check(
    "reject_missing_column_scored.csv: extra_cols == []",
    reject_missing_outcome.extra_cols == [],
    str(reject_missing_outcome.extra_cols),
)

reject_extra_item = _fixture_item("reject_extra_column_scored.csv")
_, reject_extra_outcome = process_file(
    reject_extra_item, edge_case_master, "reject_extra_column_scored", set()
)
check(
    "reject_extra_column_scored.csv: rejected / column mismatch",
    reject_extra_outcome.status == config.STATUS_REJECTED
    and reject_extra_outcome.reason == config.REASON_COLUMN_MISMATCH,
    str(reject_extra_outcome),
)
check(
    "reject_extra_column_scored.csv: extra_cols == ['RETAILER_ID']",
    reject_extra_outcome.extra_cols == ["RETAILER_ID"],
    str(reject_extra_outcome.extra_cols),
)
check(
    "reject_extra_column_scored.csv: missing_cols == []",
    reject_extra_outcome.missing_cols == [],
    str(reject_extra_outcome.missing_cols),
)

reject_both_item = _fixture_item("reject_missing_and_extra_scored.csv")
_, reject_both_outcome = process_file(
    reject_both_item, edge_case_master, "reject_missing_and_extra_scored", set()
)
check(
    "reject_missing_and_extra_scored.csv: rejected / column mismatch",
    reject_both_outcome.status == config.STATUS_REJECTED
    and reject_both_outcome.reason == config.REASON_COLUMN_MISMATCH,
    str(reject_both_outcome),
)
check(
    "reject_missing_and_extra_scored.csv: missing_cols == ['DOL_DIFF']",
    reject_both_outcome.missing_cols == ["DOL_DIFF"],
    str(reject_both_outcome.missing_cols),
)
check(
    "reject_missing_and_extra_scored.csv: extra_cols == ['BANNER', 'REGION'], each listed separately",
    reject_both_outcome.extra_cols == ["BANNER", "REGION"],
    str(reject_both_outcome.extra_cols),
)

# --- unrelated spreadsheet ----------------------------------------------------
reject_unrelated_item = _fixture_item("reject_unrelated_notes.csv")
_, reject_unrelated_outcome = process_file(
    reject_unrelated_item, edge_case_master, "reject_unrelated_notes", set()
)
check(
    "reject_unrelated_notes.csv: rejected (unrelated spreadsheet, column mismatch)",
    reject_unrelated_outcome.status == config.STATUS_REJECTED,
    str(reject_unrelated_outcome),
)

# --- zero-byte file ------------------------------------------------------------
reject_empty_item = _fixture_item("reject_empty_file_scored.csv")
_, reject_empty_outcome = process_file(
    reject_empty_item, edge_case_master, "reject_empty_file_scored", set()
)
check(
    "reject_empty_file_scored.csv: rejected / empty file (via process_file, not raised)",
    reject_empty_outcome.status == config.STATUS_REJECTED
    and reject_empty_outcome.reason == config.REASON_EMPTY_FILE,
    str(reject_empty_outcome),
)

# --- valid headers, zero data rows: skipped AND does not reserve its name ----
headers_only_item = _fixture_item("edge_headers_only_scored.csv", index=0)
real_bounty_item = UploadedItem(
    index=1, name="Instacart_Bounty_scored.csv",
    data=(SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes(),
)
shared_name_study_names = {0: "Shared_Study_Name", 1: "Shared_Study_Name"}
headers_only_result = process_batch(
    [headers_only_item, real_bounty_item], edge_case_master, shared_name_study_names
)
check(
    "edge_headers_only_scored.csv: skipped / no data rows",
    headers_only_result.outcomes[0].status == config.STATUS_SKIPPED
    and headers_only_result.outcomes[0].reason == config.REASON_NO_DATA_ROWS,
    str(headers_only_result.outcomes[0]),
)
check(
    "edge_headers_only_scored.csv does NOT reserve its Study_Name: a later real file "
    "with the same name still appends",
    headers_only_result.outcomes[1].status == config.STATUS_APPENDED,
    str(headers_only_result.outcomes[1]),
)

# --- REAL order test: step 5 (no data rows) must fire before step 6 (name
# collision). The block above never actually forces a collision — it calls
# process_batch with taken_names seeded empty, so the zero-row file's name
# was never "already taken" when step 6 ran. Here the collision is forced
# directly: process_file is called on the zero-row fixture with its own
# normalized study name PRE-SEEDED into taken_names, so the file is
# simultaneously zero-row AND a duplicate. If step 6 ran first, this would
# be skipped / already-in-master or duplicate-in-batch; the spec's fixed
# order (ARCHITECTURE.md study_processor.py step 5 before step 6) requires
# REASON_NO_DATA_ROWS instead.
order_test_study_name = "Order_Collision_Study"
order_test_taken = {order_test_study_name.strip().casefold()}
order_test_item = _fixture_item("edge_headers_only_scored.csv")
_, order_test_outcome = process_file(
    order_test_item, edge_case_master, order_test_study_name, order_test_taken
)
check(
    "REAL order test: zero-row file whose name is ALREADY in taken_names still reports "
    "skipped / no data rows (step 5 fires before step 6)",
    order_test_outcome.status == config.STATUS_SKIPPED
    and order_test_outcome.reason == config.REASON_NO_DATA_ROWS,
    str(order_test_outcome),
)

# --- complementary order test: step 1 (blank study name) must fire before
# step 2 (read_table). Garbage bytes built in memory (never written to disk)
# paired with a blank study name: if step 2 ran first, read_table would
# raise FileReadError and the outcome would be rejected / unreadable (or
# empty file, depending on what the garbage parses as). The fixed order
# requires REASON_BLANK_STUDY_NAME instead, because the study_name check
# never lets execution reach read_table at all.
garbage_bytes = b"\x00\x01\xff\xfe\x02\x03not,a,real\x00csv\xffheader\n\x01\x02"
garbage_item = UploadedItem(index=0, name="garbage_unreadable.csv", data=garbage_bytes)
_, garbage_blank_outcome = process_file(garbage_item, edge_case_master, "   ", set())
check(
    "REAL order test: unreadable garbage bytes + blank study name still reports "
    "rejected / blank study name (step 1 fires before step 2)",
    garbage_blank_outcome.status == config.STATUS_REJECTED
    and garbage_blank_outcome.reason == config.REASON_BLANK_STUDY_NAME,
    str(garbage_blank_outcome),
)


# --- reordered / messy-case fixtures: append, every value character-identical
def _assert_values_identical(fixture_name: str, study_name: str) -> None:
    fixture_item = _fixture_item(fixture_name)
    original_df = read_table(fixture_name, fixture_item.data)
    aligned_df, outcome = process_file(fixture_item, edge_case_master, study_name, set())
    check(f"{fixture_name}: appended", outcome.status == config.STATUS_APPENDED, str(outcome))
    if aligned_df is None:
        check(f"{fixture_name}: value integrity (skipped, no frame)", False, "process_file returned None")
        return
    mismatches = []
    for col in original_df.columns:
        master_col = edge_case_master.column_index[normalize_column(col)]
        before = original_df[col].tolist()
        after = aligned_df[master_col].tolist()
        for row_idx, (b, a) in enumerate(zip(before, after)):
            if b != a:
                mismatches.append((row_idx, col, b, a))
    check(
        f"{fixture_name}: every value character-identical after align",
        len(mismatches) == 0,
        f"{len(mismatches)} mismatches, first: {mismatches[0]}" if mismatches else "",
    )
    check(
        f"{fixture_name}: Study_Name tagged correctly",
        (aligned_df[config.STUDY_NAME_COL] == study_name).all(),
    )


_assert_values_identical("pass_reordered_columns_scored.csv", "pass_reordered_columns_scored")
_assert_values_identical("pass_messy_header_case_scored.csv", "pass_messy_header_case_scored")

# --- blank study name rejects --------------------------------------------------
blank_name_item = UploadedItem(
    index=0, name="Instacart_Bounty_scored.csv",
    data=(SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes(),
)
_, blank_name_outcome = process_file(blank_name_item, edge_case_master, "   ", set())
check(
    "blank/whitespace-only study name: rejected / blank study name",
    blank_name_outcome.status == config.STATUS_REJECTED
    and blank_name_outcome.reason == config.REASON_BLANK_STUDY_NAME,
    str(blank_name_outcome),
)
check(
    "blank study name is checked before the file is read: missing_cols/extra_cols stay []",
    blank_name_outcome.missing_cols == [] and blank_name_outcome.extra_cols == [],
)

# --- missing study_names entry defaults to blank, not to item.stem ----------
_, missing_key_outcome = process_file(blank_name_item, edge_case_master, {}.get(0, ""), set())
check(
    "study_processor never invents a stem fallback for a missing study name: "
    "an empty default is rejected exactly like an explicit blank",
    missing_key_outcome.status == config.STATUS_REJECTED
    and missing_key_outcome.reason == config.REASON_BLANK_STUDY_NAME,
    str(missing_key_outcome),
)
missing_key_batch = process_batch(
    [blank_name_item], edge_case_master, {}  # deliberately no entry for index 0
)
check(
    "process_batch: a study_names dict missing an item's index defaults to '' "
    "(rejected / blank study name), never silently falls back to item.stem",
    missing_key_batch.outcomes[0].status == config.STATUS_REJECTED
    and missing_key_batch.outcomes[0].reason == config.REASON_BLANK_STUDY_NAME,
    str(missing_key_batch.outcomes[0]),
)

# --- duplicate columns within a study file reject ------------------------------
bounty_bytes = (SAMPLES_DIR / "Instacart_Bounty_scored.csv").read_bytes()
bounty_text = bounty_bytes.decode("utf-8-sig")
bounty_rows_raw = list(csv.reader(_io.StringIO(bounty_text)))
bounty_header = bounty_rows_raw[0]
bounty_abs_diff_index = bounty_header.index("ABS_DIFF")
dup_col_header = bounty_header + ["Abs_Diff"]
dup_col_rows = [row + [row[bounty_abs_diff_index]] for row in bounty_rows_raw[1:]]
dup_col_output = _io.StringIO()
csv.writer(dup_col_output).writerows([dup_col_header] + dup_col_rows)
dup_col_bytes = dup_col_output.getvalue().encode("utf-8-sig")

dup_col_item = UploadedItem(index=0, name="Instacart_DupCols_scored.csv", data=dup_col_bytes)
_, dup_col_outcome = process_file(dup_col_item, edge_case_master, "Instacart_DupCols_scored", set())
check(
    "study file with duplicate normalized columns: rejected / duplicate columns",
    dup_col_outcome.status == config.STATUS_REJECTED
    and dup_col_outcome.reason == config.REASON_DUPLICATE_COLUMNS,
    str(dup_col_outcome),
)
check(
    "duplicate columns rejection leaves missing_cols/extra_cols empty (only step 4 populates them)",
    dup_col_outcome.missing_cols == [] and dup_col_outcome.extra_cols == [],
)

# ---------------------------------------------------------------------------
# SECTION 8 — Exception report and summary shape                 [Phase 4]
# ---------------------------------------------------------------------------
section("8. Exception Report and Summary Shape")

from report import outcomes_to_frame, build_exception_report, summarize

# --- a mixed outcome set covering appended / skipped / rejected -------------
sample_outcomes = [
    FileOutcome(
        file="ok_study.csv", index=0, status=config.STATUS_APPENDED, reason=config.REASON_NONE,
        missing_cols=[], extra_cols=[], study_name="Ok_Study", rows=10,
    ),
    FileOutcome(
        file="dup_study.csv", index=1, status=config.STATUS_SKIPPED, reason=config.REASON_ALREADY_IN_MASTER,
        missing_cols=[], extra_cols=[], study_name="Ok_Study", rows=0,
    ),
    FileOutcome(
        file="bad_study.csv", index=2, status=config.STATUS_REJECTED, reason=config.REASON_COLUMN_MISMATCH,
        missing_cols=["ABS_DIFF", "DOL_DIFF"], extra_cols=["RETAILER_ID"], study_name="Bad_Study", rows=0,
    ),
]

outcomes_frame = outcomes_to_frame(sample_outcomes)
check(
    "outcomes_to_frame: has the 7 documented columns, in order",
    list(outcomes_frame.columns)
    == ["file", "status", "reason", "study_name", "rows", "missing_cols", "extra_cols"],
    str(list(outcomes_frame.columns)),
)
check("outcomes_to_frame: one row per outcome", len(outcomes_frame) == 3, len(outcomes_frame))
check(
    "outcomes_to_frame: missing_cols joined with LIST_JOIN_SEPARATOR",
    outcomes_frame.loc[2, "missing_cols"] == config.LIST_JOIN_SEPARATOR.join(["ABS_DIFF", "DOL_DIFF"]),
    outcomes_frame.loc[2, "missing_cols"],
)

exception_frame = build_exception_report(sample_outcomes)
check(
    "build_exception_report: exactly config.EXCEPTION_REPORT_COLUMNS, in order",
    list(exception_frame.columns) == config.EXCEPTION_REPORT_COLUMNS,
    str(list(exception_frame.columns)),
)
check(
    "build_exception_report: only non-appended outcomes (2 of 3)",
    len(exception_frame) == 2,
    len(exception_frame),
)
check(
    "build_exception_report: contains no appended rows",
    (exception_frame["status"] != config.STATUS_APPENDED).all(),
)
check(
    "build_exception_report: extra_cols joined with LIST_JOIN_SEPARATOR",
    exception_frame.loc[exception_frame["file"] == "bad_study.csv", "extra_cols"].iloc[0] == "RETAILER_ID",
)

# --- empty exception report still carries the 5 columns ----------------------
all_appended_outcomes = [
    FileOutcome(
        file="a.csv", index=0, status=config.STATUS_APPENDED, reason=config.REASON_NONE,
        missing_cols=[], extra_cols=[], study_name="A", rows=5,
    ),
]
empty_exception_frame = build_exception_report(all_appended_outcomes)
check(
    "build_exception_report: empty frame (no exceptions) still has the 5 columns",
    list(empty_exception_frame.columns) == config.EXCEPTION_REPORT_COLUMNS,
    str(list(empty_exception_frame.columns)),
)
check("build_exception_report: empty frame has 0 rows", len(empty_exception_frame) == 0, len(empty_exception_frame))

# --- summarize: six keys, in display order, reconciling against a real result
summary = summarize(full_batch_result)
expected_summary_keys = [
    "Total files processed",
    "Files successfully appended",
    "Files skipped (already in master)",
    "Files rejected",
    "Records appended this run",
    "Total records in master",
]
check(
    "summarize: exactly the six documented keys, in display order",
    list(summary.keys()) == expected_summary_keys,
    str(list(summary.keys())),
)
check(
    "summarize: 'Total files processed' == appended + skipped + rejected",
    summary["Total files processed"]
    == summary["Files successfully appended"]
    + summary["Files skipped (already in master)"]
    + summary["Files rejected"],
    str(summary),
)
check(
    "summarize: counts reconcile against the full-batch BatchResult directly",
    summary["Total files processed"] == full_batch_result.total_files
    and summary["Files successfully appended"] == full_batch_result.appended
    and summary["Files skipped (already in master)"] == full_batch_result.skipped
    and summary["Files rejected"] == full_batch_result.rejected
    and summary["Records appended this run"] == full_batch_result.rows_appended
    and summary["Total records in master"] == full_batch_result.total_records,
    str(summary),
)
check(
    "summarize: 'Total records in master' == len(master_df)",
    summary["Total records in master"] == len(full_batch_result.master_df),
)

# ---------------------------------------------------------------------------
# SECTION 9 — csv_writer.py and the Phase 5 QC checkpoint
# ---------------------------------------------------------------------------
section("9. csv_writer.py and Phase 5 QC Checkpoint")

from datetime import datetime as _datetime

from csv_writer import build_exception_filename, build_master_filename, to_csv_bytes

_FIXED_NOW = _datetime(2026, 9, 7, 14, 30)

check(
    "build_master_filename: exact pattern with an injected fixed 'now'",
    build_master_filename("Instacart", _FIXED_NOW) == "Master_Instacart_2026-09-07_1430.csv",
    build_master_filename("Instacart", _FIXED_NOW),
)
check(
    "build_exception_filename: exact pattern with an injected fixed 'now'",
    build_exception_filename("Instacart", _FIXED_NOW) == "Exceptions_Instacart_2026-09-07_1430.csv",
    build_exception_filename("Instacart", _FIXED_NOW),
)

# --- to_csv_bytes: UTF-8 BOM on a minimal frame -----------------------------
_bom_probe_df = pd.DataFrame({"A": ["1"], "B": ["2"]})
_bom_bytes = to_csv_bytes(_bom_probe_df)
check(
    "to_csv_bytes: output starts with the UTF-8 BOM",
    _bom_bytes[:3] == b"\xef\xbb\xbf",
    repr(_bom_bytes[:3]),
)

# --- grep-style check: no module other than app.py imports streamlit -------
_CODE_DIR = Path(__file__).resolve().parent
_non_app_streamlit_importers: list[str] = []
for _py_file in sorted(_CODE_DIR.glob("*.py")):
    if _py_file.name in ("app.py", "test_meta_pipeline.py"):
        continue
    _tree = ast.parse(_py_file.read_text(encoding="utf-8"))
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.Import) and any(
            "streamlit" in (alias.name or "") for alias in _node.names
        ):
            _non_app_streamlit_importers.append(_py_file.name)
        elif isinstance(_node, ast.ImportFrom) and _node.module and "streamlit" in _node.module:
            _non_app_streamlit_importers.append(_py_file.name)
check(
    "no module other than app.py imports streamlit",
    _non_app_streamlit_importers == [],
    str(_non_app_streamlit_importers),
)
check(
    "app.py itself does import streamlit (sanity — the grep check above isn't vacuous)",
    any(
        (isinstance(_node, ast.Import) and any("streamlit" in (a.name or "") for a in _node.names))
        or (isinstance(_node, ast.ImportFrom) and _node.module and "streamlit" in _node.module)
        for _node in ast.walk(ast.parse((_CODE_DIR / "app.py").read_text(encoding="utf-8")))
    ),
)

# --- Final end-to-end precision check ---------------------------------------
# Completes ARCHITECTURE.md section 5's QC CHECKPOINT steps 6-7, which
# Section 3 above deferred as a "[PHASE 5 STUB]" before csv_writer.py and
# study_processor.py existed. Runs Instacart_Bounty_scored.csv through the
# COMPLETE pipeline (read_table -> tag_study_name -> align_to_master, all
# inside process_batch -> to_csv_bytes), then decodes and re-parses the
# output bytes with the stdlib csv module and compares every field back
# against `raw_rows` (parsed directly from the source file in Section 3)
# character-by-character.
precision_master_item = UploadedItem(
    index=0, name=MASTER_FILE_NAME, data=(SAMPLES_DIR / MASTER_FILE_NAME).read_bytes()
)
precision_master_ctx = build_master_context_from_existing(precision_master_item)

precision_bounty_item = UploadedItem(index=1, name=BOUNTY_FILE.name, data=BOUNTY_FILE.read_bytes())
precision_result = process_batch(
    [precision_bounty_item], precision_master_ctx, {1: precision_bounty_item.stem}
)
check(
    "precision checkpoint: Instacart_Bounty_scored.csv appended via the full pipeline",
    any(
        o.index == 1 and o.status == config.STATUS_APPENDED
        for o in precision_result.outcomes
    ),
    str([o for o in precision_result.outcomes if o.index == 1]),
)

precision_csv_bytes = to_csv_bytes(precision_result.master_df)
check(
    "precision checkpoint: to_csv_bytes(df)[:3] == UTF-8 BOM on the real consolidated master",
    precision_csv_bytes[:3] == b"\xef\xbb\xbf",
    repr(precision_csv_bytes[:3]),
)
check(
    "precision checkpoint: literal '0.19163628728414203' survives into the output bytes",
    b"0.19163628728414203" in precision_csv_bytes,
)

precision_text = precision_csv_bytes.decode(config.OUTPUT_ENCODING)
precision_output_rows = list(csv.DictReader(_io.StringIO(precision_text)))
precision_bounty_rows = [
    r for r in precision_output_rows if r[config.STUDY_NAME_COL] == precision_bounty_item.stem
]

check(
    "precision checkpoint: output row count for Bounty matches the source row count",
    len(precision_bounty_rows) == len(raw_rows),
    f"source={len(raw_rows)} output={len(precision_bounty_rows)}",
)

if len(precision_bounty_rows) == len(raw_rows):
    precision_mismatches: list[tuple[int, str, str, str]] = []
    for i, (raw_row, out_row) in enumerate(zip(raw_rows, precision_bounty_rows)):
        for col in REFERENCE_STUDY_COLUMNS:
            if raw_row[col] != out_row[col]:
                precision_mismatches.append((i, col, raw_row[col], out_row[col]))
    check(
        "precision checkpoint: every one of the 31 source columns is character-identical "
        "in the output, for every row (re-parsed with stdlib csv after the full pipeline "
        "and to_csv_bytes round-trip)",
        len(precision_mismatches) == 0,
        f"{len(precision_mismatches)} mismatches, first: {precision_mismatches[0]}"
        if precision_mismatches
        else "",
    )

    extra_field_sets = {
        frozenset(out_row.keys()) - frozenset(raw_rows[0].keys()) for out_row in precision_bounty_rows
    }
    missing_field_sets = {
        frozenset(raw_rows[0].keys()) - frozenset(out_row.keys()) for out_row in precision_bounty_rows
    }
    check(
        "precision checkpoint: Study_Name is the only field the output row has that the "
        "source row does not",
        extra_field_sets == {frozenset({config.STUDY_NAME_COL})},
        str(extra_field_sets),
    )
    check(
        "precision checkpoint: no source field was dropped in the output",
        missing_field_sets == {frozenset()},
        str(missing_field_sets),
    )
else:
    check("precision checkpoint: field-by-field comparison", False, "skipped — row counts did not match")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
total = _passed + _failed
print(f"\n{'='*60}")
print(f"  RESULT: {_passed}/{total} checks passed  |  {_failed} failed")
print(f"{'='*60}\n")

if _failed > 0:
    sys.exit(1)
