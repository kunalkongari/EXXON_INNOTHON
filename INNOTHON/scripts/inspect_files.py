"""
inspect_files.py
----------------
Recursively inventories EVERY file under data/raw/ (read-only; nothing in raw is modified).

For each file: name, path, format (extension + sniffed magic bytes), size, and
  * XLS/XLSX : every sheet, raw used-range rows/cols, header text, CEA report title,
               PERIOD declared inside the sheet, units found in header, regions/states detected
  * CSV      : rows, cols, column names, dtypes
  * PDF      : pages and first text lines (pdfplumber)
  * other    : text preview / type note

Outputs (outside raw):
  data/metadata/file_inventory.csv     one row per file
  data/metadata/sheet_inventory.csv    one row per Excel sheet / CSV table
  logs/inspect_files.log               unreadable files are logged as ERROR and listed in the inventory
"""
from __future__ import annotations

import csv
import logging
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
META = ROOT / "data" / "metadata"
LOGS = ROOT / "logs"

REGIONS = ["NORTHERN", "WESTERN", "SOUTHERN", "EASTERN", "NORTH EASTERN", "BHUTAN"]
UNIT_PATTERNS = {"GWh": r"\bGWH\b", "MU": r"\bMU\b", "MW": r"\(MW|\bMW\b", "%": r"%|PLANT LOAD FACTOR"}


def setup_logging():
    LOGS.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("inspect")
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for h in (logging.FileHandler(LOGS / "inspect_files.log", encoding="utf-8", mode="w"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        h.setLevel(logging.INFO if isinstance(h, logging.FileHandler) else logging.WARNING)
        log.addHandler(h)
    return log


def sniff(path: Path) -> str:
    head = path.open("rb").read(8)
    if head.startswith(b"\xD0\xCF\x11\xE0"):
        return "ole2(xls)"
    if head.startswith(b"PK\x03\x04"):
        return "zip(xlsx/zip)"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.lstrip().startswith(b"<"):
        return "html/xml"
    return "text/other"


def header_text(df: pd.DataFrame, nrows: int = 14) -> str:
    vals = []
    for v in df.head(nrows).values.ravel():
        if pd.notna(v) and str(v).strip():
            vals.append(re.sub(r"\s+", " ", str(v)).strip())
    return " | ".join(vals)


def find_period(df: pd.DataFrame) -> str:
    txt = header_text(df, 8)
    m = re.search(r"PERIOD\s*:?\s*\|?\s*([A-Za-z]{3}-\d{4})", txt, re.I)
    return m.group(1).upper() if m else ""


def inspect_sheet(df: pd.DataFrame) -> dict:
    hdr = header_text(df)
    first_col = df.iloc[:, 0].dropna().astype(str).str.strip().str.upper()
    regions = sorted({r for r in REGIONS for v in first_col if v.startswith(r)})
    units = [u for u, p in UNIT_PATTERNS.items() if re.search(p, hdr, re.I)]
    title = ""
    m = re.search(r"(SUB-?\s*REPORT\s*\d+)", hdr, re.I)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).upper()
    num_cells = pd.to_numeric(df.stack(), errors="coerce").notna().sum()
    return {
        "rows_used": df.dropna(how="all").shape[0],
        "cols_used": df.dropna(axis=1, how="all").shape[1],
        "numeric_cells": int(num_cells),
        "sub_report": title,
        "period_in_sheet": find_period(df),
        "units_in_header": ";".join(units),
        "regions_detected": ";".join(regions),
        "header_text": hdr[:600],
    }


def main():
    log = setup_logging()
    META.mkdir(parents=True, exist_ok=True)
    files, sheets = [], []
    all_paths = sorted(p for p in RAW.rglob("*") if p.is_file() and ".git" not in p.relative_to(RAW).parts)
    for i, p in enumerate(all_paths, 1):
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        ext = p.suffix.lower().lstrip(".")
        rec = {"file_name": p.name, "file_path": rel, "extension": ext, "sniffed_format": sniff(p),
               "file_size_bytes": p.stat().st_size, "n_sheets": "", "sheet_names": "",
               "rows": "", "cols": "", "column_names": "", "dtypes": "", "period_in_file": "",
               "readable": "YES", "error": ""}
        try:
            if ext in ("xls", "xlsx"):
                xf = pd.ExcelFile(p)
                rec["n_sheets"] = len(xf.sheet_names)
                rec["sheet_names"] = ";".join(xf.sheet_names)
                periods = set()
                for sh in xf.sheet_names:
                    df = xf.parse(sh, header=None)
                    info = inspect_sheet(df)
                    periods.add(info["period_in_sheet"])
                    sheets.append({"file_name": p.name, "file_path": rel, "sheet_name": sh,
                                   "raw_rows": df.shape[0], "raw_cols": df.shape[1], **info})
                    rec["rows"], rec["cols"] = df.shape
                rec["period_in_file"] = ";".join(sorted(x for x in periods if x))
                rec["column_names"] = "multi-row CEA header (see sheet_inventory.header_text)"
            elif ext == "csv":
                df = pd.read_csv(p)
                rec.update(rows=df.shape[0], cols=df.shape[1], column_names=";".join(df.columns),
                           dtypes=";".join(f"{c}:{t}" for c, t in df.dtypes.astype(str).items()))
                sheets.append({"file_name": p.name, "file_path": rel, "sheet_name": "(csv)",
                               "raw_rows": df.shape[0], "raw_cols": df.shape[1], "rows_used": df.shape[0],
                               "cols_used": df.shape[1], "numeric_cells": int(df.select_dtypes("number").count().sum()),
                               "sub_report": "", "period_in_sheet": "", "units_in_header": "",
                               "regions_detected": "", "header_text": ";".join(df.columns)})
            elif ext == "pdf":
                import pdfplumber
                with pdfplumber.open(p) as pdf:
                    rec["n_sheets"] = len(pdf.pages)
                    txt = (pdf.pages[0].extract_text() or "")[:300]
                    rec["column_names"] = "PDF pages; first text: " + re.sub(r"\s+", " ", txt)
            elif ext == "json":
                import json
                d = json.loads(p.read_text(encoding="utf-8"))
                rec["column_names"] = ";".join(d.keys()) if isinstance(d, dict) else type(d).__name__
            else:
                rec["column_names"] = "non-tabular file (" + (ext or "no extension") + ")"
        except Exception as e:  # noqa: BLE001
            rec.update(readable="NO", error=f"{type(e).__name__}: {e}")
            log.error("UNREADABLE %s: %s", rel, e)
        files.append(rec)
        if i % 200 == 0:
            print(f"  inspected {i}/{len(all_paths)}", flush=True)

    with (META / "file_inventory.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(files[0].keys()))
        w.writeheader()
        w.writerows(files)
    if sheets:
        with (META / "sheet_inventory.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(sheets[0].keys()))
            w.writeheader()
            w.writerows(sheets)
    bad = sum(r["readable"] == "NO" for r in files)
    log.info("inspected %d files (%d unreadable), %d sheets", len(files), bad, len(sheets))
    print(f"inspected {len(files)} files, unreadable={bad}, sheets={len(sheets)}")


if __name__ == "__main__":
    main()
