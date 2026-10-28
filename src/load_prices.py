"""Download daily adjusted prices for every stock with insider purchases, plus SPY
as the market benchmark, and load them into SQLite.

Usage:
    python src/load_prices.py            # every ticker with a purchase
    python src/load_prices.py --top 200  # only the 200 most-bought tickers (quick test run)

Already-downloaded tickers are skipped, so you can stop and re-run safely.
"""
import argparse
import sqlite3
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "insiders.db"
BENCHMARK = "SPY"
BATCH_SIZE = 50


def tickers_to_fetch(conn: sqlite3.Connection, top: int | None) -> list[str]:
    sql = """
        SELECT f.ticker, COUNT(DISTINCT f.accession_number) AS buys
        FROM filings f
        JOIN transactions t ON t.accession_number = f.accession_number
        WHERE t.trans_code = 'P' AND f.ticker IS NOT NULL
        GROUP BY f.ticker
        ORDER BY buys DESC
    """
    if top:
        sql += f" LIMIT {int(top)}"
    tickers = [row[0] for row in conn.execute(sql)]
    return [BENCHMARK] + [t for t in tickers if t != BENCHMARK]


def to_long(data: pd.DataFrame, batch: list[str]) -> pd.DataFrame:
    """Turn yfinance's wide download into rows of (ticker, date, close)."""
    frames = []
    if isinstance(data.columns, pd.MultiIndex):
        available = set(data.columns.get_level_values(0))
        for t in batch:
            if t in available and "Close" in data[t]:
                s = data[t]["Close"].dropna()
                frames.append(pd.DataFrame({"ticker": t, "date": s.index, "close": s.values}))
    elif "Close" in data and len(batch) == 1:
        s = data["Close"].dropna()
        frames.append(pd.DataFrame({"ticker": batch[0], "date": s.index, "close": s.values}))
    if not frames:
        return pd.DataFrame(columns=["ticker", "date", "close"])
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    return out


def main():
    import yfinance as yf

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--top", type=int, help="only fetch the N most-bought tickers")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    first_filing = conn.execute("SELECT MIN(filing_date) FROM filings").fetchone()[0]
    if not first_filing:
        raise SystemExit("No filings in the database yet. Run src/load_sec.py first.")
    start = (pd.Timestamp(first_filing) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")

    have = {row[0] for row in conn.execute("SELECT DISTINCT ticker FROM prices")}
    todo = [t for t in tickers_to_fetch(conn, args.top) if t not in have]
    print(f"{len(todo):,} tickers to download (from {start}); {len(have):,} already loaded")

    missing = 0
    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i:i + BATCH_SIZE]
        data = yf.download(batch, start=start, auto_adjust=True, group_by="ticker",
                           progress=False, threads=True)
        rows = to_long(data, batch)
        missing += len(set(batch) - set(rows["ticker"]))
        with conn:
            conn.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?)",
                             rows[["ticker", "date", "close"]].itertuples(index=False, name=None))
        print(f"  {min(i + BATCH_SIZE, len(todo)):,}/{len(todo):,} done")
        time.sleep(1)  # be polite to Yahoo

    n = conn.execute("SELECT COUNT(DISTINCT ticker), COUNT(*) FROM prices").fetchone()
    print(f"\nPrices loaded for {n[0]:,} tickers ({n[1]:,} rows). "
          f"{missing:,} tickers had no data (usually delisted or renamed).")
    conn.close()


if __name__ == "__main__":
    main()
