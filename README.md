# Insider Trading Signal Tracker

**Question:** When company insiders (CEOs, CFOs, directors) buy their own stock on the open market, does the stock beat the market afterward?

This project loads every SEC Form 4 insider purchase since 2023 into a SQL database, matches each one to daily stock prices, and measures how the stock performed against the S&P 500 (SPY) 1, 3 and 6 months after the purchase became public. An interactive Streamlit dashboard presents the results.

**Live dashboard:** [insider-tracker-cheikhdia.streamlit.app](https://insider-tracker-cheikhdia.streamlit.app/)

## Findings

From 86,546 Form 4 purchase transactions filed between January 2023 and September 2026, 25,133 purchase filings passed the filters and had price data.

**Following insider buys did not beat the market in this period.**

| Horizon | Buys | Avg return | Avg vs SPY | Median vs SPY | Beat SPY |
|---|---|---|---|---|---|
| 1 month | 25,053 | +1.45% | −0.24% | −1.21% | 44.3% |
| 3 months | 23,702 | +4.87% | −0.85% | −3.32% | 41.1% |
| 6 months | 21,718 | +8.68% | −2.55% | −6.73% | 38.1% |

- **The gap widens over time.** Stocks rose after insider buys, but SPY rose more, and fewer than 4 in 10 buys beat it over 6 months.
- **CFO buys were the only role ahead of SPY** (+1.18% over 3 months, 1,228 buys). CEO buys trailed by 1.78% and 10% owners by 1.86%.
- **Bigger buys did worse, not better.** $1M+ purchases trailed SPY by 2.02% over 3 months, versus 0.73% for $10K–50K buys.
- **Cluster buys didn't help.** When 3+ insiders bought within 30 days, the stock trailed SPY by 1.30% over 3 months, versus 0.69% for solo or paired buys.
- **The true result is likely worse.** Yahoo Finance had no prices for 2,091 of 4,953 tickers, mostly delisted companies, so many of the biggest losers are missing (see Limitations).

A likely explanation: SPY was driven by a handful of mega-cap tech stocks from 2023 to 2026, while most insider buying happens in small caps.

## How it works

```
SEC Form 4 data sets ──> load_sec.py ──┐
                                       ├──> SQLite ──> sql/build ──> analyze.py ──> dashboard data ──> app.py
Yahoo Finance prices ──> load_prices.py┘                               │
                                                                       └──> research answers (sql/questions)
```

1. **`src/load_sec.py`** downloads the SEC's quarterly insider transaction files and loads original Form 4 open-market buys (code P) and sells (code S).
2. **`src/load_prices.py`** downloads adjusted daily prices for every stock with an insider buy, plus SPY as the benchmark.
3. **`sql/build/`** builds the analysis tables:
   - `purchase_events`: one row per purchase filing, with the insider's role and dollar size
   - `price_index`: trading days numbered per ticker with `ROW_NUMBER()`
   - `forward_returns`: each purchase's return and return vs SPY at 1, 3 and 6 months, plus a cluster-buy count
   - `event_paths`: each purchase's return vs SPY every 5 trading days for the event-study chart (recursive CTE)
4. **`sql/questions/`** answers the research questions: overall signal, role, purchase size, cluster buys, top insiders, and latest big buys.
5. **`src/analyze.py`** runs all the SQL, prints the answers, and exports a small `dashboard/insider_signals.db` for the app.
6. **`app.py`** is the Streamlit dashboard: an event-study chart, breakdowns by role, size, cluster and 10b5-1 plan, an insider leaderboard, and a feed of the latest buys with links to the SEC filings.

## Run it

You need Python 3.10 or newer ([python.org](https://www.python.org/downloads/)).

### Set up (once)

Create a virtual environment in the project folder and install the libraries into it.

**Windows (PowerShell)**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
If PowerShell says running scripts is disabled, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again.

**Mac / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

In each new terminal, activate the environment again (the second line above) before running the commands below.

### Just view the dashboard

The built dashboard data (`dashboard/insider_signals.db`) is included, so this works right away:

```bash
streamlit run app.py
```

It opens at http://localhost:8501. Press Ctrl+C in the terminal to stop it.

### Rebuild the data from scratch

```bash
# 1. Load SEC filings (the SEC requires your name and email on downloads)
python src/load_sec.py --start 2023q1 --end 2026q3 --user-agent "Your Name you@email.com"

# 2. Load prices for every ticker with a purchase, plus SPY
#    (add --top 200 for a quick test run with only the 200 most-bought tickers)
python src/load_prices.py

# 3. Run the analysis and build the dashboard data
python src/analyze.py
```

A full run downloads about 160 MB from the SEC and prices for about 5,000 tickers from Yahoo Finance. The price step is the slow part.

Re-running is safe. `load_sec.py` skips quarters already in `data/raw/`, and `load_prices.py` skips tickers already loaded. To pick up new quarters, change `--end` and re-run all three steps. Prices for tickers already loaded are not extended, so for fully up-to-date prices, delete `data/insiders.db` and rebuild.

## Put the dashboard online (free)

1. Create a GitHub repository and push this folder. The raw data in `data/` is git-ignored, but `dashboard/insider_signals.db` is committed: it's the small file the app reads.
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub, click **Create app**, pick the repository, and set the main file to `app.py`.
3. Paste the app's URL at the top of this README and on your resume.

To refresh with new filings, re-run steps 1–3 above and push the updated `dashboard/insider_signals.db`.

## Design choices

- **Filing date, not trade date.** The public only sees a trade once the Form 4 is filed, so returns start at the close of the first trading day after filing. Using the trade date would be look-ahead bias.
- **Market-adjusted returns.** Each buy's return minus SPY's return over the same days, so a rising market doesn't count as insider skill.
- **Open-market purchases only.** Sales are noisy (taxes, diversification, scheduled plans), while buying with your own cash is a deliberate bet.
- **Original Form 4s only.** Amendments (4/A) are skipped so trades aren't double-counted.
- **Joint filings count once.** When a CEO and their trust file together, the filing is one event.
- **Filters.** Price at least $1 per share and purchase at least $10,000.
- **Event study on a fixed set.** The 6-month curve only uses buys with a full 6 months of prices, so every point averages the same buys.

## Limitations

- **Survivorship bias.** Yahoo Finance often has no data for delisted stocks. Companies that went bankrupt drop out, which likely makes results look better than reality.
- **Overlapping buys.** Several insiders buying the same stock in the same weeks aren't independent bets, so the confidence band is narrower than it should be.
- **In-sample rankings.** The "top insiders" list looks backward, so it doesn't prove those insiders will keep winning.
- **No trading costs.** Small-cap stocks can have wide bid-ask spreads that eat into returns.

## Project structure

```
app.py                     Streamlit dashboard
schema.sql                 database tables
src/load_sec.py            SEC Form 4 loader
src/load_prices.py         price loader (Yahoo Finance)
src/analyze.py             runs the SQL, prints answers, exports dashboard data
sql/build/                 analysis tables (window functions, CTEs, recursive CTE)
sql/questions/             one SQL file per research question
sql/export/dashboard.sql   copies what the dashboard needs into dashboard/insider_signals.db
```
