-- Q1. Does insider buying beat the market? Average return vs SPY at each horizon.
SELECT '1 month' AS horizon,
       COUNT(*) AS buys,
       ROUND(AVG(ret_1m) * 100, 2)    AS avg_return_pct,
       ROUND(AVG(excess_1m) * 100, 2) AS avg_vs_spy_pct,
       ROUND(AVG(CASE WHEN excess_1m > 0 THEN 1.0 ELSE 0 END) * 100, 1) AS beat_spy_pct
FROM forward_returns WHERE excess_1m IS NOT NULL
UNION ALL
SELECT '3 months', COUNT(*),
       ROUND(AVG(ret_3m) * 100, 2),
       ROUND(AVG(excess_3m) * 100, 2),
       ROUND(AVG(CASE WHEN excess_3m > 0 THEN 1.0 ELSE 0 END) * 100, 1)
FROM forward_returns WHERE excess_3m IS NOT NULL
UNION ALL
SELECT '6 months', COUNT(*),
       ROUND(AVG(ret_6m) * 100, 2),
       ROUND(AVG(excess_6m) * 100, 2),
       ROUND(AVG(CASE WHEN excess_6m > 0 THEN 1.0 ELSE 0 END) * 100, 1)
FROM forward_returns WHERE excess_6m IS NOT NULL;
