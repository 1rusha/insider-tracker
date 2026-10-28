-- For every purchase: the stock's return 1, 3 and 6 months after it became public, and the return vs SPY.
-- 1 month = 21 trading days, 3 months = 63, 6 months = 126.

-- Step 1: entry point. Buy at the close of the first trading day AFTER the filing date.
-- Investors only see a Form 4 once it's filed, so using the trade date would be look-ahead bias.
-- (Saved as its own table so the joins below can use the price index.)
DROP TABLE IF EXISTS entry_points;
CREATE TABLE entry_points AS
SELECT e.*,
       (SELECT p.day_num
          FROM price_index p
         WHERE p.ticker = e.ticker AND p.date > e.filing_date
         ORDER BY p.date
         LIMIT 1) AS entry_day
FROM purchase_events e;

-- Step 2: look up prices at entry and 21 / 63 / 126 trading days later, for the stock and for SPY.
DROP TABLE IF EXISTS forward_returns;
CREATE TABLE forward_returns AS
WITH priced AS (
    SELECT e.*,
           p0.date    AS entry_date,  p0.close   AS entry_close,
           p21.date   AS date_1m,     p21.close  AS close_1m,
           p63.date   AS date_3m,     p63.close  AS close_3m,
           p126.date  AS date_6m,     p126.close AS close_6m
    FROM entry_points e
    JOIN price_index p0          ON p0.ticker   = e.ticker AND p0.day_num   = e.entry_day
    LEFT JOIN price_index p21    ON p21.ticker  = e.ticker AND p21.day_num  = e.entry_day + 21
    LEFT JOIN price_index p63    ON p63.ticker  = e.ticker AND p63.day_num  = e.entry_day + 63
    LEFT JOIN price_index p126   ON p126.ticker = e.ticker AND p126.day_num = e.entry_day + 126
    WHERE julianday(p0.date) - julianday(e.filing_date) <= 7   -- drop events with gaps in price history
)
SELECT pr.accession_number,
       pr.issuer_cik,
       pr.ticker,
       pr.issuer_name,
       pr.filing_date,
       pr.entry_date,
       pr.owner_cik,
       pr.owner_name,
       pr.role,
       pr.dollar_value,
       pr.is_10b5_1_plan,
       pr.entry_day,
       pr.entry_close,
       s0.close AS spy_entry_close,
       pr.close_1m / pr.entry_close - 1 AS ret_1m,
       pr.close_3m / pr.entry_close - 1 AS ret_3m,
       pr.close_6m / pr.entry_close - 1 AS ret_6m,
       (pr.close_1m / pr.entry_close - 1) - (s21.close  / s0.close - 1) AS excess_1m,
       (pr.close_3m / pr.entry_close - 1) - (s63.close  / s0.close - 1) AS excess_3m,
       (pr.close_6m / pr.entry_close - 1) - (s126.close / s0.close - 1) AS excess_6m
FROM priced pr
JOIN price_index s0          ON s0.ticker   = 'SPY' AND s0.date   = pr.entry_date
LEFT JOIN price_index s21    ON s21.ticker  = 'SPY' AND s21.date  = pr.date_1m
LEFT JOIN price_index s63    ON s63.ticker  = 'SPY' AND s63.date  = pr.date_3m
LEFT JOIN price_index s126   ON s126.ticker = 'SPY' AND s126.date = pr.date_6m;

CREATE INDEX idx_forward_returns_ticker ON forward_returns(ticker, filing_date);

-- Step 3: cluster signal. How many different insiders bought this stock in the 30 days up to this filing.
ALTER TABLE forward_returns ADD COLUMN insiders_last_30d INTEGER;
UPDATE forward_returns
SET insiders_last_30d = (
    SELECT COUNT(DISTINCT g.owner_cik)
    FROM forward_returns g
    WHERE g.ticker = forward_returns.ticker
      AND g.filing_date BETWEEN date(forward_returns.filing_date, '-30 days') AND forward_returns.filing_date
);
