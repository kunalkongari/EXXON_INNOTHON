"""
download_npp.py
---------------
Automated downloader for the National Power Portal (https://npp.gov.in) -
"Monthly Reports ACTUAL" generation archive (CEA 18-column monthly reports).

Discovery (Nov 2026 inspection of https://npp.gov.in/publishedReports):
  * Published Reports page lists the latest month of each report family.
  * Archive for monthly ACTUAL generation lives at /monthlyGenerationReportsAct.
    It is a form (POST rmonth=MM/YYYY + session CSRF token, no login) that
    returns links of the form
      /public-reports/cea/monthly/generation/18_col_act/<YYYY>/<MON>//18_col_act-<N>_<YYYY>-<MON>.<xls|pdf>
  * 20 report numbers (N = 1..20) are published each month.

Behaviour:
  * Walks every month in [--start, --end] through the official archive form
    (no URL guessing), so only links the portal itself publishes are fetched.
  * Prefers XLS; downloads PDF only if the XLS is missing or invalid.
  * Validates file signatures (OLE2 / ZIP / %PDF) and rejects HTML error pages.
  * Never overwrites an existing raw file.
  * Logs every attempt (success or failure) to data/metadata/npp_download_log.csv
    and logs/download_npp.log. Failed downloads are retried at most --retries times.

Only ACTUAL reports are downloaded. TENTATIVE reports, installed-capacity reports,
fuel-supply reports and transmission reports are deliberately not downloaded
(see reports/download_summary.md).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://npp.gov.in"
ARCHIVE = BASE + "/monthlyGenerationReportsAct"
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "npp"
META = ROOT / "data" / "metadata"
LOGS = ROOT / "logs"
LOG_CSV = META / "npp_download_log.csv"

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

# Report number -> (title as shown on portal, raw sub-folder, category)
REPORTS = {
    1: ("All India", "all_india", "all_india_generation"),
    2: ("Region Wise", "region_wise", "region_wise_generation"),
    3: ("Thermal, Hydro and Nuclear Consolidated", "source_wise", "source_wise_generation"),
    4: ("Sector Wise", "other_reports", "sector_wise_generation"),
    5: ("Central Sector Thermal", "other_reports", "sector_wise_generation"),
    6: ("State Sector Thermal", "other_reports", "sector_wise_generation"),
    7: ("Pvt. Sector Utilities & IPP Thermal", "other_reports", "sector_wise_generation"),
    8: ("Central Sector Hydro", "other_reports", "sector_wise_generation"),
    9: ("State Sector Hydro", "other_reports", "sector_wise_generation"),
    10: ("Pvt. & IPP Hydro and Central Sector Nuclear", "other_reports", "sector_wise_generation"),
    11: ("Coal/Lignite/Multi Fuel", "source_wise", "source_wise_generation"),
    12: ("Gas and Liquid Fuel (Central Sector)", "source_wise", "source_wise_generation"),
    13: ("Gas and Liquid Fuel (State Sector)", "source_wise", "source_wise_generation"),
    14: ("Gas and Liquid Fuel (Pvt. Sector)", "source_wise", "source_wise_generation"),
    15: ("Diesel", "source_wise", "source_wise_generation"),
    16: ("Region wise State wise and Station wise Detail", "station_wise", "station_wise_generation"),
    17: ("Summary All India", "all_india", "all_india_generation"),
    18: ("Sector Wise Details (Central, Gas Based Stations)", "other_reports", "sector_wise_generation"),
    19: ("Sector Wise Details (State, Gas Based Stations)", "other_reports", "sector_wise_generation"),
    20: ("Sector Wise Details (Private, Gas Based Stations)", "other_reports", "sector_wise_generation"),
}

LOG_FIELDS = [
    "file_name", "local_path", "report_no", "report_name", "report_category",
    "reporting_period", "download_date", "original_url", "file_format",
    "file_size_bytes", "download_status", "notes",
]

LINK_RE = re.compile(r"/public-reports/cea/monthly/generation/18_col_act/[^\"']+?\.(?:xls|xlsx|pdf)", re.I)
NUM_RE = re.compile(r"18_col_act-(\d+)_(\d{4})-([A-Z]{3})\.(xls|xlsx|pdf)$", re.I)


def setup_logging() -> logging.Logger:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("download_npp")
    log.setLevel(logging.INFO)
    if not log.handlers:
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        fh = logging.FileHandler(LOGS / "download_npp.log", encoding="utf-8")
        fh.setFormatter(fmt)
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        log.addHandler(fh)
        log.addHandler(sh)
    return log


def sniff_format(content: bytes) -> str:
    """Return the real file type from its magic bytes."""
    head = content[:8]
    if head.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"):
        return "xls"
    if head.startswith(b"PK\x03\x04"):
        return "xlsx"
    if head.startswith(b"%PDF"):
        return "pdf"
    stripped = content[:512].lstrip().lower()
    if stripped.startswith(b"<!doctype") or stripped.startswith(b"<html") or b"<html" in stripped:
        return "html"
    if stripped.startswith(b"<"):
        return "xml_or_html"
    return "unknown"


def month_iter(start: str, end: str):
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    while (y, m) <= (ey, em):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


class ArchiveClient:
    def __init__(self, log: logging.Logger, delay: float):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "Mozilla/5.0 (research data audit; INNOTHON)"
        self.log = log
        self.delay = delay
        self.token = None

    def _refresh_token(self, html: str):
        tag = BeautifulSoup(html, "lxml").find("input", {"name": "_csrf"})
        if tag:
            self.token = tag["value"]

    def links_for(self, year: int, month: int) -> list[str]:
        if self.token is None:
            r = self.s.get(ARCHIVE, timeout=60)
            r.raise_for_status()
            self._refresh_token(r.text)
        r = self.s.post(
            ARCHIVE,
            data={"rmonth": f"{month:02d}/{year}", "_csrf": self.token},
            headers={"Referer": ARCHIVE, "Origin": BASE},
            timeout=60,
        )
        r.raise_for_status()
        self._refresh_token(r.text)
        time.sleep(self.delay)
        return sorted(set(LINK_RE.findall(r.text)))

    def fetch(self, url: str, retries: int) -> tuple[bytes | None, str]:
        err = ""
        for attempt in range(1, retries + 1):
            try:
                r = self.s.get(BASE + url, timeout=120)
                time.sleep(self.delay)
                if r.status_code != 200:
                    err = f"HTTP {r.status_code}"
                    if r.status_code == 404:
                        break
                    continue
                return r.content, ""
            except requests.RequestException as e:  # network error
                err = f"{type(e).__name__}: {e}"
                self.log.warning("attempt %d failed for %s: %s", attempt, url, err)
                time.sleep(2 * attempt)
        return None, err


def load_existing_log() -> dict[str, dict]:
    if not LOG_CSV.exists():
        return {}
    with LOG_CSV.open(newline="", encoding="utf-8") as f:
        return {row["original_url"]: row for row in csv.DictReader(f)}


def write_log(rows: dict[str, dict]):
    META.mkdir(parents=True, exist_ok=True)
    with LOG_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        w.writeheader()
        for row in sorted(rows.values(), key=lambda r: (r["reporting_period"], int(r["report_no"] or 0), r["file_format"])):
            w.writerow(row)


def save_dashboard_snapshot(log: logging.Logger):
    """Save the NPP dashboard JSON (current-day snapshot only, used as evidence of
    what the dashboard exposes; it is NOT a historical series)."""
    url = BASE + "/dashBoard/getAllZone?ID=IND"
    today = dt.date.today().isoformat()
    dest = RAW / "other_reports" / "dashboard_snapshot" / f"getAllZone_IND_{today}.json"
    rows = load_existing_log()
    row = {"file_name": dest.name, "local_path": str(dest.relative_to(ROOT)).replace("\\", "/"),
           "report_no": "", "report_name": "NPP Dashboard getAllZone (current snapshot)",
           "report_category": "dashboard_snapshot", "reporting_period": today,
           "download_date": today, "original_url": url, "file_format": "json",
           "file_size_bytes": "", "download_status": "", "notes": ""}
    if dest.exists():
        log.info("dashboard snapshot for today already present; not overwritten")
        return
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest",
                                       "Referer": BASE + "/dashBoard/cp-map-dashboard"}, timeout=60)
        r.raise_for_status()
        r.json()  # validate JSON
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        row.update(file_size_bytes=len(r.content), download_status="SUCCESS",
                   notes="current-day snapshot; RE fields are installed capacity, not generation")
    except Exception as e:  # noqa: BLE001 - record any failure
        row.update(download_status="FAILED", notes=str(e))
        log.error("dashboard snapshot failed: %s", e)
    rows[url] = row
    write_log(rows)


def main():
    today = dt.date.today()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2010-01", help="first month YYYY-MM to query (default 2010-01)")
    ap.add_argument("--end", default=f"{today.year}-{today.month:02d}", help="last month YYYY-MM to query")
    ap.add_argument("--delay", type=float, default=0.4, help="seconds between requests (politeness)")
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--also-pdf", action="store_true", help="download PDF even when a valid XLS exists")
    ap.add_argument("--dashboard-only", action="store_true", help="only save the dashboard JSON snapshot")
    args = ap.parse_args()

    log = setup_logging()
    if args.dashboard_only:
        save_dashboard_snapshot(log)
        return
    client = ArchiveClient(log, args.delay)
    rows = load_existing_log()
    months_with_links, months_without = [], []

    for y, m in month_iter(args.start, args.end):
        period = f"{y}-{m:02d}"
        try:
            links = client.links_for(y, m)
        except requests.RequestException as e:
            log.error("archive query failed for %s: %s", period, e)
            months_without.append((period, f"query error: {e}"))
            continue
        if not links:
            months_without.append((period, "archive returned no links"))
            continue
        months_with_links.append(period)
        log.info("%s: %d links listed", period, len(links))

        by_report: dict[int, dict[str, str]] = {}
        for url in links:
            mm = NUM_RE.search(url)
            if not mm:
                log.warning("unrecognised link pattern: %s", url)
                continue
            by_report.setdefault(int(mm.group(1)), {})[mm.group(4).lower()] = url

        for no, fmts in sorted(by_report.items()):
            title, sub, cat = REPORTS.get(no, (f"Report {no} (unlisted)", "other_reports", "unknown"))
            order = ["xls", "xlsx", "pdf"]
            got_excel = False
            for fmt in order:
                if fmt not in fmts:
                    continue
                if fmt == "pdf" and got_excel and not args.also_pdf:
                    continue
                url = fmts[fmt]
                fname = url.rsplit("/", 1)[-1]
                dest = RAW / sub / str(y) / fname
                prev = rows.get(url)
                if dest.exists() and prev and prev["download_status"] == "SUCCESS":
                    if fmt in ("xls", "xlsx"):
                        got_excel = True
                    continue
                row = {
                    "file_name": fname, "local_path": str(dest.relative_to(ROOT)).replace("\\", "/"),
                    "report_no": no, "report_name": title, "report_category": cat,
                    "reporting_period": period, "download_date": today.isoformat(),
                    "original_url": BASE + url, "file_format": fmt,
                    "file_size_bytes": "", "download_status": "", "notes": "",
                }
                if dest.exists():
                    # never overwrite raw files; just re-verify
                    content = dest.read_bytes()
                    row["notes"] = "file already present; not re-downloaded"
                else:
                    content, err = client.fetch(url, args.retries)
                    if content is None:
                        row.update(download_status="FAILED", notes=err)
                        rows[BASE + url] = row
                        log.error("FAILED %s (%s)", url, err)
                        continue
                real = sniff_format(content)
                expected = {"xls": ("xls", "xlsx"), "xlsx": ("xlsx", "xls"), "pdf": ("pdf",)}[fmt]
                row["file_size_bytes"] = len(content)
                if real not in expected:
                    row.update(download_status="INVALID", notes=f"content sniffed as '{real}', not saved")
                    log.error("INVALID %s sniffed=%s", url, real)
                else:
                    if not dest.exists():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(content)
                    if real != fmt:
                        row["notes"] = (row["notes"] + f"; extension .{fmt} but content is {real}").strip("; ")
                    row["download_status"] = "SUCCESS"
                    if fmt in ("xls", "xlsx"):
                        got_excel = True
                rows[BASE + url] = row
        write_log(rows)

    write_log(rows)
    cov = META / "npp_archive_coverage.csv"
    with cov.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["reporting_period", "archive_has_links", "note"])
        for p in months_with_links:
            w.writerow([p, "YES", ""])
        for p, note in months_without:
            w.writerow([p, "NO", note])
    ok = sum(r["download_status"] == "SUCCESS" for r in rows.values())
    bad = sum(r["download_status"] != "SUCCESS" for r in rows.values())
    log.info("DONE. months with links=%d, without=%d, files ok=%d, not ok=%d",
             len(months_with_links), len(months_without), ok, bad)
    if months_with_links:
        log.info("archive coverage: %s .. %s", min(months_with_links), max(months_with_links))


if __name__ == "__main__":
    main()
