-- Q4. Cluster buys: when 3+ different insiders buy the same stock within 30 days, is the signal stronger?
SELECT CASE WHEN insiders_last_30d >= 3 THEN 'Cluster (3+ insiders)' ELSE 'Solo or pair' END AS buy_type,
       COUNT(*) AS buys,
       ROUND(AVG(excess_3m) * 100, 2) AS avg_vs_spy_3m_pct,
       ROUND(AVG(CASE WHEN excess_3m > 0 THEN 1.0 ELSE 0 END) * 100, 1) AS beat_spy_pct
FROM forward_returns
WHERE excess_3m IS NOT NULL
GROUP BY buy_type;
