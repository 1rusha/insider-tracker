-- Q6. Latest big insider buys (over $100K): the live feed for the dashboard.
SELECT filing_date,
       ticker,
       issuer_name,
       owner_name,
       role,
       CAST(ROUND(dollar_value) AS INTEGER) AS dollar_value
FROM purchase_events
WHERE dollar_value >= 100000
ORDER BY filing_date DESC, dollar_value DESC
LIMIT 25;
