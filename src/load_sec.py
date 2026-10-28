"""Download the SEC's quarterly insider transaction data sets and load Form 4
open-market buys and sells into SQLite.

Usage:
    python src/load_sec.py --start 2023q1 --end 2026q3 --user-agent "Your Name you@email.com"

The SEC requires a User-Agent with your name and email on every download.
You can also set it once with the SEC_USER_AGENT environment variable.
"""
import argparse
import csv
import os
import sqlite3
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "insiders.db"
SCHEMA_PATH = ROOT / "schema.sql"

# The SEC moved newer quarters to a different folder in 2026, so try both.
URL_TEMPLATES = [
    "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{q}_form345.zip",
    "https://www.sec.gov/files/datastandardsinnovation/data/insider-transactions-data-sets/{q}_form345.zip",
]

KEEP_CODES = {"P", "S"}  # open-market purchases and sales
BAD_TICKERS = {"", "NONE", "N/A", "NA", "NULL", "-"}


def quarter_range(start: str, end: str) -> list[str]:
    """'2023q1', '2023q3' -> ['2023q1', '2023q2', '2023q3']"""
    sy, sq = int(start[:4]), int(start[-1])
    ey, eq = int(end[:4]), int(end[-1])
    out = []
    y, q = sy, sq
    while (y, q) <= (ey, eq):
        out.append(f"{y}q{q}")
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)
    return out


def download(quarter: str, user_agent: str | None) -> Path | None:
    """Download one quarter's zip into data/raw (skipped if already there)."""
    path = RAW_DIR / f"{quarter}_form345.zip"
    if path.exists() and path.stat().st_size > 0:
        return path
    if not user_agent:
        sys.exit("Set --user-agent or SEC_USER_AGENT to your name and email (the SEC requires it).")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for template in URL_TEMPLATES:
        url = template.format(q=quarter)
        resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=120)
        time.sleep(0.5)  # stay well under the SEC's rate limit
        if resp.status_code == 200 and resp.content[:2] == b"PK":
            path.write_bytes(resp.content)
            print(f"  downloaded {quarter} ({len(resp.content) / 1e6:.1f} MB)")
            return path
    print(f"  {quarter}: not found on SEC.gov (not published yet?), skipping")
    return None


def read_tsv(zf: zipfile.ZipFile, name: str, columns: list[str]) -> pd.DataFrame:
    """Read one tab-separated file from the zip, keeping only the columns we need."""
    member = next(m for m in zf.namelist() if m.upper().endswith(name))
    with zf.open(member) as f:
        df = pd.read_csv(
            f,
            sep="\t",
            dtype=str,
            usecols=lambda c: c in columns,
            quoting=csv.QUOTE_NONE,
            encoding_errors="replace",
            on_bad_lines="skip",
        )
    for col in columns:  # older quarters lack some columns (e.g. AFF10B5ONE)
        if col not in df:
            df[col] = pd.NA
    return df[columns]


def to_iso(dates: pd.Series) -> pd.Series:
    """SEC dates look like 02-JAN-2024; convert to 2024-01-02."""
    parsed = pd.to_datetime(dates, format="%d-%b-%Y", errors="coerce")
    if len(parsed) and parsed.isna().mean() > 0.5:  # fallback if the SEC ever changes the format
        parsed = pd.to_datetime(dates, format="mixed", errors="coerce")
    return parsed.dt.strftime("%Y-%m-%d")


def clean_ticker(t) -> str | None:
    if not isinstance(t, str):
        return None
    t = t.strip().upper()
    if t in BAD_TICKERS or " " in t or "," in t:
        return None
    return t.replace(".", "-").replace("/", "-")  # BRK.B -> BRK-B (Yahoo format)


def plan_flag(v) -> int | None:
    if not isinstance(v, str):
        return None
    v = v.strip().upper()
    if v in {"1", "TRUE", "Y", "YES"}:
        return 1
    if v in {"0", "FALSE", "N", "NO"}:
        return 0
    return None


def nullify(df: pd.DataFrame) -> list[tuple]:
    """DataFrame -> rows with NaN/NA turned into None for SQLite."""
    return [tuple(None if pd.isna(v) else v for v in row) for row in df.itertuples(index=False)]


def load_quarter(conn: sqlite3.Connection, zip_path: Path) -> tuple[int, int]:
    with zipfile.ZipFile(zip_path) as zf:
        sub = read_tsv(zf, "SUBMISSION.TSV", [
            "ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT", "DOCUMENT_TYPE",
            "ISSUERCIK", "ISSUERNAME", "ISSUERTRADINGSYMBOL", "AFF10B5ONE"])
        tx = read_tsv(zf, "NONDERIV_TRANS.TSV", [
            "ACCESSION_NUMBER", "NONDERIV_TRANS_SK", "TRANS_DATE", "TRANS_CODE",
            "TRANS_SHARES", "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD",
            "SHRS_OWND_FOLWNG_TRANS", "DIRECT_INDIRECT_OWNERSHIP"])
        owners = read_tsv(zf, "REPORTINGOWNER.TSV", [
            "ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME",
            "RPTOWNER_RELATIONSHIP", "RPTOWNER_TITLE"])

    # Original Form 4s only; amendments (4/A) would double-count trades.
    sub = sub[sub["DOCUMENT_TYPE"].str.strip() == "4"]
    tx = tx[tx["TRANS_CODE"].str.strip().isin(KEEP_CODES)]
    tx = tx[tx["ACCESSION_NUMBER"].isin(sub["ACCESSION_NUMBER"])]
    sub = sub[sub["ACCESSION_NUMBER"].isin(tx["ACCESSION_NUMBER"])]
    owners = owners[owners["ACCESSION_NUMBER"].isin(sub["ACCESSION_NUMBER"])]

    filings = pd.DataFrame({
        "accession_number": sub["ACCESSION_NUMBER"],
        "filing_date": to_iso(sub["FILING_DATE"]),
        "period_of_report": to_iso(sub["PERIOD_OF_REPORT"]),
        "document_type": "4",
        "issuer_cik": sub["ISSUERCIK"],
        "issuer_name": sub["ISSUERNAME"],
        "ticker": sub["ISSUERTRADINGSYMBOL"].map(clean_ticker),
        "is_10b5_1_plan": sub["AFF10B5ONE"].map(plan_flag),
    }).dropna(subset=["filing_date"])

    transactions = pd.DataFrame({
        "accession_number": tx["ACCESSION_NUMBER"],
        "trans_sk": pd.to_numeric(tx["NONDERIV_TRANS_SK"], errors="coerce"),
        "trans_date": to_iso(tx["TRANS_DATE"]),
        "trans_code": tx["TRANS_CODE"].str.strip(),
        "shares": pd.to_numeric(tx["TRANS_SHARES"], errors="coerce"),
        "price_per_share": pd.to_numeric(tx["TRANS_PRICEPERSHARE"], errors="coerce"),
        "acquired_disposed": tx["TRANS_ACQUIRED_DISP_CD"].str.strip(),
        "shares_owned_after": pd.to_numeric(tx["SHRS_OWND_FOLWNG_TRANS"], errors="coerce"),
        "ownership_type": tx["DIRECT_INDIRECT_OWNERSHIP"].str.strip(),
    }).dropna(subset=["trans_sk"])
    transactions = transactions[transactions["accession_number"].isin(filings["accession_number"])]

    insiders = pd.DataFrame({
        "accession_number": owners["ACCESSION_NUMBER"],
        "owner_cik": owners["RPTOWNERCIK"],
        "owner_name": owners["RPTOWNERNAME"],
        "relationship": owners["RPTOWNER_RELATIONSHIP"],
        "title": owners["RPTOWNER_TITLE"],
    })
    insiders = insiders[insiders["accession_number"].isin(filings["accession_number"])]

    with conn:
        conn.executemany("INSERT OR REPLACE INTO filings VALUES (?,?,?,?,?,?,?,?)", nullify(filings))
        conn.executemany("INSERT OR REPLACE INTO insiders VALUES (?,?,?,?,?)", nullify(insiders))
        conn.executemany("INSERT OR REPLACE INTO transactions VALUES (?,?,?,?,?,?,?,?,?)",
                         nullify(transactions))
    return len(filings), len(transactions)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default="2023q1", help="first quarter, e.g. 2023q1")
    parser.add_argument("--end", default="2026q3", help="last quarter, e.g. 2026q3")
    parser.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT"),
                        help='your name and email, e.g. "Jane Doe jane@email.com"')
    args = parser.parse_args()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text())

    for q in quarter_range(args.start, args.end):
        print(q)
        path = download(q, args.user_agent)
        if path:
            n_filings, n_tx = load_quarter(conn, path)
            print(f"  loaded {n_filings:,} filings, {n_tx:,} buy/sell transactions")

    totals = conn.execute("""
        SELECT SUM(trans_code = 'P'), SUM(trans_code = 'S') FROM transactions""").fetchone()
    print(f"\nDatabase now holds {totals[0] or 0:,} purchases and {totals[1] or 0:,} sales -> {DB_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
