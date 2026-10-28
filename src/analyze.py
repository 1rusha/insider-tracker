"""Build the analysis tables in SQL, answer each research question, and export the
small database the dashboard reads.

Usage:
    python src/analyze.py

Results print to the terminal and save as CSVs in output/.
The dashboard data goes to dashboard/insider_signals.db.
"""
import sqlite3
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "insiders.db"
SQL_DIR = ROOT / "sql"
OUT_DIR = ROOT / "output"
DASHBOARD_DB = ROOT / "dashboard" / "insider_signals.db"


def build(conn: sqlite3.Connection) -> None:
    for path in sorted((SQL_DIR / "build").glob("*.sql")):
        t0 = time.time()
        conn.executescript(path.read_text())
        print(f"built {path.stem} ({time.time() - t0:.1f}s)")


def answer_questions(conn: sqlite3.Connection) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    for path in sorted((SQL_DIR / "questions").glob("*.sql")):
        sql = path.read_text()
        title = sql.splitlines()[0].lstrip("- ").strip()
        df = pd.read_sql_query(sql, conn)
        df.to_csv(OUT_DIR / f"{path.stem}.csv", index=False)
        print(f"\n{title}\n{'-' * len(title)}")
        print(df.to_string(index=False) if len(df) else "(no rows yet)")


def medians(conn: sqlite3.Connection) -> None:
    """SQLite has no MEDIAN(). A few huge winners can drag the average up, so check the median too."""
    df = pd.read_sql_query("SELECT excess_1m, excess_3m, excess_6m FROM forward_returns", conn)
    med = (df.median() * 100).round(2)
    title = "Median return vs SPY (less sensitive to outliers than the average)"
    print(f"\n{title}\n{'-' * len(title)}")
    for horizon, col in [("1 month", "excess_1m"), ("3 months", "excess_3m"), ("6 months", "excess_6m")]:
        print(f"{horizon:>9}: {med[col]:+.2f}%  (n={df[col].notna().sum():,})")


def export_dashboard(conn: sqlite3.Connection) -> None:
    DASHBOARD_DB.parent.mkdir(exist_ok=True)
    DASHBOARD_DB.unlink(missing_ok=True)
    conn.execute("ATTACH DATABASE ? AS dash", (str(DASHBOARD_DB),))
    conn.executescript((SQL_DIR / "export" / "dashboard.sql").read_text())
    conn.commit()
    conn.execute("DETACH DATABASE dash")
    with sqlite3.connect(DASHBOARD_DB) as dash:
        dash.execute("VACUUM")
    print(f"\nDashboard data exported to {DASHBOARD_DB} ({DASHBOARD_DB.stat().st_size / 1e6:.1f} MB)")


def main():
    conn = sqlite3.connect(DB_PATH)
    build(conn)
    n = conn.execute("SELECT COUNT(*) FROM forward_returns").fetchone()[0]
    print(f"\n{n:,} insider purchases matched to price data")
    answer_questions(conn)
    medians(conn)
    print(f"\nCSVs saved to {OUT_DIR}")
    export_dashboard(conn)
    conn.close()


if __name__ == "__main__":
    main()
