"""
download_github.py
------------------
Downloads the competition-authorised Renewable India dataset
(https://github.com/chrisjaimyantony/renewable-india-dataset) into
data/raw/renewable_india/ and records provenance.

Method: `git clone --depth 1` (official Git transport). If git is unavailable,
falls back to GitHub's official ZIP archive for the default branch.

Records repository URL, retrieval date, branch, commit SHA and every file
(name, relative path, format, size, sha256) in
data/metadata/github_download_log.csv. Existing raw files are never overwritten:
if the target folder already contains a clone, the script only re-inventories it.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import logging
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import requests

REPO = "https://github.com/chrisjaimyantony/renewable-india-dataset"
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "raw" / "renewable_india" / "renewable-india-dataset"
META = ROOT / "data" / "metadata"
LOGS = ROOT / "logs"
LOG_CSV = META / "github_download_log.csv"


def setup_logging() -> logging.Logger:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("download_github")
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for h in (logging.FileHandler(LOGS / "download_github.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        log.addHandler(h)
    return log


def git(*args, cwd=None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def main():
    log = setup_logging()
    branch, commit, method = "", "", ""
    if DEST.exists() and any(DEST.iterdir()):
        log.info("target already populated; not re-downloading (raw files are never overwritten)")
        method = "existing"
    else:
        DEST.parent.mkdir(parents=True, exist_ok=True)
        try:
            git("clone", "--depth", "1", REPO + ".git", str(DEST))
            method = "git clone --depth 1"
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            log.warning("git clone failed (%s); falling back to ZIP", e)
            if DEST.exists():
                shutil.rmtree(DEST)
            r = requests.get(REPO + "/archive/HEAD.zip", timeout=120)
            r.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                top = z.namelist()[0].split("/")[0]
                z.extractall(DEST.parent)
            (DEST.parent / top).rename(DEST)
            method = "github zip (HEAD)"
    if (DEST / ".git").exists():
        try:
            branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=DEST)
            commit = git("rev-parse", "HEAD", cwd=DEST)
        except subprocess.CalledProcessError as e:
            log.warning("could not read git metadata: %s", e)

    today = dt.date.today().isoformat()
    rows = []
    for p in sorted(DEST.rglob("*")):
        if p.is_dir() or ".git" in p.relative_to(DEST).parts:
            continue
        data = p.read_bytes()
        rows.append({
            "file_name": p.name,
            "local_path": str(p.relative_to(ROOT)).replace("\\", "/"),
            "repo_url": REPO,
            "branch": branch,
            "commit": commit,
            "retrieval_method": method,
            "download_date": today,
            "original_url": f"{REPO}/blob/{commit or 'HEAD'}/{p.relative_to(DEST).as_posix()}",
            "file_format": p.suffix.lstrip(".").lower() or "none",
            "file_size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "download_status": "SUCCESS" if len(data) > 0 else "EMPTY",
        })
    META.mkdir(parents=True, exist_ok=True)
    with LOG_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["file_name"])
        w.writeheader()
        w.writerows(rows)
    log.info("repo=%s branch=%s commit=%s files=%d", REPO, branch, commit, len(rows))


if __name__ == "__main__":
    main()
