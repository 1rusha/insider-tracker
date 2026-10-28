-- Event study: each buy's return vs SPY every 5 trading days for 6 months after the filing.
-- Only buys with a full 6 months of prices are included, so every point on the curve
-- averages the same set of buys.
DROP TABLE IF EXISTS event_paths;
CREATE TABLE event_paths AS
WITH RECURSIVE steps(k) AS (
    SELECT 0
    UNION ALL
    SELECT k + 5 FROM steps WHERE k + 5 <= 125
),
checkpoints AS (
    SELECT k FROM steps
    UNION
    SELECT 126                                  -- end exactly at 6 months (126 trading days)
)
SELECT e.accession_number,
       c.k AS day,
       (p.close / e.entry_close - 1) - (s.close / e.spy_entry_close - 1) AS excess
FROM forward_returns e
CROSS JOIN checkpoints c
-- In SQLite, CROSS JOIN fixes the loop order (buy -> checkpoint -> price), so the price lookup
-- can use the (ticker, day_num) index. A plain JOIN let the planner pick a slower order (~30x slower).
CROSS JOIN price_index p ON p.ticker = e.ticker AND p.day_num = e.entry_day + c.k
JOIN price_index s       ON s.ticker = 'SPY'     AND s.date = p.date
WHERE e.excess_6m IS NOT NULL;
