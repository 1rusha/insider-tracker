-- Q3. Do bigger buys mean more conviction? 3-month return vs SPY by purchase size.
WITH sized AS (
    SELECT *,
           CASE
               WHEN dollar_value < 50000   THEN '1. $10K-50K'
               WHEN dollar_value < 250000  THEN '2. $50K-250K'
               WHEN dollar_value < 1000000 THEN '3. $250K-1M'
               ELSE                             '4. $1M+'
           END AS size_bucket
    FROM forward_returns
    WHERE excess_3m IS NOT NULL
)
SELECT size_bucket,
       COUNT(*) AS buys,
       ROUND(AVG(excess_3m) * 100, 2) AS avg_vs_spy_3m_pct,
       ROUND(AVG(CASE WHEN excess_3m > 0 THEN 1.0 ELSE 0 END) * 100, 1) AS beat_spy_pct
FROM sized
GROUP BY size_bucket
ORDER BY size_bucket;
