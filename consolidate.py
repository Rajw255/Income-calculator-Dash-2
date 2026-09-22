"""
CONSOLIDATION LAYER
====================
Central Data Folder  ->  this script  ->  Processed Partner Data

Turns many per-RM Excel exports sitting in one folder into a single,
already-cleaned set of tables the Streamlit app reads. Designed to run
as a SCHEDULED JOB (cron / Windows Task Scheduler) rather than inside
the app itself -- with ~120 RM files, re-parsing every file on every
dashboard page load would be slow and wasteful. Run this once (e.g.
every morning), then the app just reads the already-processed output.

Usage:
    python consolidate.py --raw-folder ./raw_data --out-folder ./processed_data

Each file in --raw-folder should follow the partner360_data_template.xlsx
column layout. A per-RM file commonly only has Partner Master / Client
Master / Transaction Fact filled in (their own rows) -- Partner Target
and Partner Review are usually maintained centrally by RM managers/
Cluster Managers in ONE separate file that also lives in the same
folder. Both patterns are handled the same way: every file's sheets are
read leniently (missing sheets are fine) and merged in.

Resilience: one bad file (wrong headers, corrupt, wrong format) is
logged and skipped -- it never blocks the other 119 files from
processing. Check consolidation_report.json after every run.

De-duplication: if the same partner_id / client_id / transaction_id
shows up in more than one file (e.g. an RM re-sends a corrected file),
the LAST file processed (alphabetically, then by file modified time)
wins. Point this at a folder that only contains the files you want
included in today's run -- move or archive older exports out of it.
"""

import argparse
import glob
import json
import os
from datetime import datetime

import pandas as pd

import excel_loader

TABLES = ["partner_master", "client_master", "transaction_fact", "partner_target", "partner_review"]
SHEET_NAME_FOR_TABLE = {
    "partner_master": "Partner Master", "client_master": "Client Master",
    "transaction_fact": "Transaction Fact", "partner_target": "Partner Target",
    "partner_review": "Partner Review",
}
PRIMARY_KEY = {
    "partner_master": "partner_id", "client_master": "client_id",
    "transaction_fact": "transaction_id", "partner_target": None, "partner_review": None,
}
# columns that must be re-parsed as dates after a CSV round-trip
DATE_COLS_OUT = {
    "partner_master": ["joining_date"], "client_master": ["joining_date"],
    "transaction_fact": ["transaction_date", "month"],
    "partner_target": ["period", "last_updated"], "partner_review": ["review_date", "due_date"],
}


def consolidate_folder(raw_folder: str, out_folder: str, pattern: str = "*.xlsx") -> tuple:
    """Read every workbook in raw_folder, merge into 5 tables, write them
    (plus a JSON report) into out_folder. Returns (data_dict, report_dict).
    """
    files = sorted(glob.glob(os.path.join(raw_folder, pattern)))
    os.makedirs(out_folder, exist_ok=True)

    collected = {t: [] for t in TABLES}
    report = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "raw_folder": raw_folder, "files_found": len(files),
        "files_ok": [], "files_failed": [],
    }

    for f in files:
        try:
            data, messages = excel_loader.load_excel_workbook(f, strict=False)
        except Exception as e:
            report["files_failed"].append({"file": os.path.basename(f), "error": str(e)})
            continue
        if data is None:
            reason = "; ".join(m for _, m in messages)
            report["files_failed"].append({"file": os.path.basename(f), "error": reason})
            continue
        for t in TABLES:
            df = data[t].copy()
            if not df.empty:
                df["_source_file"] = os.path.basename(f)
            collected[t].append(df)
        warn = [m for level, m in messages if level == "warning"]
        report["files_ok"].append({"file": os.path.basename(f), "warnings": warn})

    final = {}
    for t in TABLES:
        parts = [d for d in collected[t] if not d.empty]
        df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        pk = PRIMARY_KEY[t]
        if pk and pk in df.columns and not df.empty:
            df = df.drop_duplicates(subset=[pk], keep="last")
        elif t == "transaction_fact" and "transaction_id" in df.columns and not df.empty:
            df = df.drop_duplicates(subset=["transaction_id"], keep="last")
        final[t] = df
        df.to_csv(os.path.join(out_folder, f"{t}.csv"), index=False)

    report["row_counts"] = {t: len(final[t]) for t in TABLES}
    report["partners_seen"] = int(final["partner_master"]["partner_id"].nunique()) if not final["partner_master"].empty else 0
    with open(os.path.join(out_folder, "consolidation_report.json"), "w") as fh:
        json.dump(report, fh, indent=2, default=str)

    return final, report


def load_processed(out_folder: str):
    """Used by the Streamlit app's 'Load Processed Data' mode. Returns
    (data_dict, report_dict, error_message). error_message is None on
    success.
    """
    missing = [t for t in TABLES if not os.path.exists(os.path.join(out_folder, f"{t}.csv"))]
    if missing:
        return None, None, (f"No processed data found in '{out_folder}' "
                             f"(missing {', '.join(t + '.csv' for t in missing)}). "
                             f"Run `python consolidate.py --raw-folder ... --out-folder {out_folder}` first.")

    data = {}
    for t in TABLES:
        df = pd.read_csv(os.path.join(out_folder, f"{t}.csv"))
        for col in DATE_COLS_OUT.get(t, []):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
                if col != "month":  # month stays a Timestamp for groupby elsewhere
                    df[col] = df[col].dt.date
        data[t] = df

    report = None
    report_path = os.path.join(out_folder, "consolidation_report.json")
    if os.path.exists(report_path):
        with open(report_path) as fh:
            report = json.load(fh)

    return data, report, None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Consolidate per-RM Excel exports into Processed Partner Data.")
    parser.add_argument("--raw-folder", default="./raw_data", help="Folder the 120 RM files land in.")
    parser.add_argument("--out-folder", default="./processed_data", help="Where consolidated CSVs + report are written.")
    parser.add_argument("--pattern", default="*.xlsx", help="Glob pattern for which files to include.")
    args = parser.parse_args()

    _, rpt = consolidate_folder(args.raw_folder, args.out_folder, args.pattern)
    print(json.dumps(rpt, indent=2, default=str))
    if rpt["files_failed"]:
        print(f"\n{len(rpt['files_failed'])} file(s) failed and were skipped — see consolidation_report.json.")
