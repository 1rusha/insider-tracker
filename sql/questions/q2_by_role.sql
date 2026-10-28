-- Q2. Whose buys matter most? 3-month return vs SPY by insider role.
SELECT role,
       COUNT(*) AS buys,
       ROUND(AVG(excess_3m) * 100, 2) AS avg_vs_spy_3m_pct,
       ROUND(AVG(CASE WHEN excess_3m > 0 THEN 1.0 ELSE 0 END) * 100, 1) AS beat_spy_pct
FROM forward_returns
WHERE excess_3m IS NOT NULL
GROUP BY role
ORDER BY avg_vs_spy_3m_pct DESC;
