# Handoff — Context for the Next Project

> Read once, at the start of a new "automate a manual process" project, to inherit what worked here without re-deriving it. Not maintained after that point — for this project's own live status, see `CLAUDE.md`.

---

## What This Project Is

An internal Streamlit tool for Circana's commercial team that automates appending Unify export rows into a P&G master benchmark tracker — a task a team member (Antara) previously did by hand each quarter. It runs locally, is stateless (no database — the user uploads the master file each run), and outputs a timestamped CSV. Full spec: `PG_AUTOMATION_CLAUDECODE_BRIEF.md`. End-user instructions: `USER_GUIDE.md`.

---

## Transferable Lessons

1. **Confirm scope in writing before building, and hold the line.** This project hit a scope-creep episode early on; the fix was a "Confirmed Scope (non-negotiable)" list agreed with the requester (see `PG_AUTOMATION_CLAUDECODE_BRIEF.md`, section 2). Do this up front on the next project too, not as damage control.

2. **Default to stateless unless there's a specific reason not to.** The master file is never persisted between runs — the user re-uploads it each time (`master_loader.py`). This was a deliberate choice to avoid silently overwriting or drifting from the real source of truth. Only add persistence if a concrete requirement demands it.

3. **Flat module structure for small local tools.** All code lives directly in `code/`, one file per responsibility, no subfolders. For a tool this size, run by a non-technical user, the extra navigation cost of nested packages isn't worth it.

4. **Don't pre-build flexibility — build the specific case first.** `rules_editor.py` and `tactic_mapper.py` were built to let users define row-level translation rules, then removed because real usage only ever needed one label per upload (see "Removed Features" in `CLAUDE.md`). Files were kept but disconnected rather than deleted, in case the general case becomes real later. Wait for actual demand before generalizing.

5. **Fuzzy-match as a warning, not a blocker, for manual free-text fields.** Brand/campaign/tactic-label fields are user-typed, so typos and near-duplicates are inevitable. The pattern used: warn at ≥85% similarity to an existing value, but never stop the user from proceeding (`metadata_form.py`, `tactic_category_mapper.py`).

6. **Output convention for a non-technical, Excel-bound user:** timestamped filename, UTF-8-BOM encoding (so Excel renders special characters correctly), and never overwrite the original input file (`csv_writer.py`).

7. **Agent workflow discipline:** `architect` before any code is written, `qc-reviewer` after every module change (not just at the end), `devops` as a distinct final pass before handoff to the end user. Skipping straight to code, or treating QC/devops as optional, is where this kind of project tends to accumulate rework.

---

## Module Map

Full reference — not just the lessons above — so anything specific can be pulled from a real, working implementation instead of re-described from memory.

| File | What it does |
|------|---------------|
| `app.py` | Orchestrator — the Streamlit entry point; run with `python -m streamlit run app.py` |
| `config.py` | All constants: column counts, dropdown option lists, fuzzy-match threshold |
| `mapping_config.py` | `COLUMN_MAP` + `COLUMN_ALIASES` — primary and fallback column-name mappings between source and master formats |
| `unify_loader.py` | Loads and validates the source export file (`.xlsx`/`.csv`) |
| `master_loader.py` | Loads and validates the master file; handles multi-sheet selection |
| `cleaner.py` | Numeric cleaning: `%` → decimal, strips commas, `-`/`<1%` → NaN |
| `tactic_mapper.py` | Unused — kept for reference; see lesson 4 |
| `transformer.py` | Orchestrates the pipeline; builds the final output row structure |
| `csv_writer.py` | Timestamped filename generation + UTF-8-BOM CSV byte encoding |
| `metadata_form.py` | Streamlit UI — user-input fields (dropdowns + free text) with fuzzy-match warnings |
| `tactic_category_mapper.py` | Streamlit UI — per-category mapping table with exclusion toggle |
| `rules_editor.py` | Unused — kept for reference; see lesson 4 |
| `test_pipeline.py` | QC script; run with `python test_pipeline.py` |
| `requirements.txt` | Pinned dependencies: streamlit, pandas, openpyxl, rapidfuzz, streamlit-searchbox |
