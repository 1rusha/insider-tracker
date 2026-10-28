-- Insider Trading Signal Tracker: database schema (SQLite)
-- Source: SEC Insider Transactions Data Sets (Form 4 filings) + daily prices from Yahoo Finance

CREATE TABLE IF NOT EXISTS filings (
    accession_number  TEXT PRIMARY KEY,   -- SEC's unique ID for each filing
    filing_date       TEXT NOT NULL,      -- ISO date the trade became public
    period_of_report  TEXT,
    document_type     TEXT NOT NULL,      -- only original Form 4s ('4') are loaded
    issuer_cik        TEXT NOT NULL,
    issuer_name       TEXT,
    ticker            TEXT,               -- Yahoo-style symbol, e.g. BRK-B
    is_10b5_1_plan    INTEGER             -- 1 = pre-scheduled plan trade, 0 = not, NULL = not reported
);

CREATE TABLE IF NOT EXISTS insiders (
    accession_number  TEXT NOT NULL REFERENCES filings(accession_number),
    owner_cik         TEXT NOT NULL,
    owner_name        TEXT,
    relationship      TEXT,               -- Officer / Director / TenPercentOwner / Other
    title             TEXT,               -- e.g. "Chief Executive Officer"
    PRIMARY KEY (accession_number, owner_cik)
);

CREATE TABLE IF NOT EXISTS transactions (
    accession_number    TEXT NOT NULL REFERENCES filings(accession_number),
    trans_sk            INTEGER NOT NULL,
    trans_date          TEXT,
    trans_code          TEXT NOT NULL,    -- P = open-market purchase, S = open-market sale
    shares              REAL,
    price_per_share     REAL,
    acquired_disposed   TEXT,             -- A = acquired, D = disposed
    shares_owned_after  REAL,
    ownership_type      TEXT,             -- D = direct, I = indirect
    PRIMARY KEY (accession_number, trans_sk)
);

CREATE TABLE IF NOT EXISTS prices (
    ticker  TEXT NOT NULL,
    date    TEXT NOT NULL,
    close   REAL NOT NULL,                -- split- and dividend-adjusted close
    PRIMARY KEY (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_filings_ticker_date ON filings(ticker, filing_date);
CREATE INDEX IF NOT EXISTS idx_transactions_code ON transactions(trans_code);
