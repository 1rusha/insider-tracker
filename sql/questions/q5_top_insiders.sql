-- Q5. Best track records: insiders with 3+ buys, ranked by average 3-month return vs SPY.
WITH stats AS (
    SELECT owner_cik,
           MAX(owner_name)            AS insider,
           GROUP_CONCAT(DISTINCT ticker) AS tickers,
           COUNT(*)                   AS buys,
           AVG(excess_3m)             AS avg_excess
    FROM forward_returns
    WHERE excess_3m IS NOT NULL
    GROUP BY owner_cik
    HAVING COUNT(*) >= 3
)
SELECT RANK() OVER (ORDER BY avg_excess DESC) AS rank,
       insider,
       tickers,
       buys,
       ROUND(avg_excess * 100, 2) AS avg_vs_spy_3m_pct
FROM stats
ORDER BY rank
LIMIT 20;
