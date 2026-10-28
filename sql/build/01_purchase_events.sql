-- One row per insider purchase filing: who bought, their role, how much, and when it went public.
DROP VIEW IF EXISTS purchase_events;
CREATE VIEW purchase_events AS
WITH one_owner AS (
    -- Joint filings list several owners (e.g. a CEO and their trust). Keep one so each filing counts once.
    SELECT accession_number, owner_cik, owner_name, relationship, title,
           ROW_NUMBER() OVER (PARTITION BY accession_number ORDER BY owner_cik) AS rn
    FROM insiders
),
buys AS (
    SELECT accession_number,
           SUM(shares)                   AS shares,
           SUM(shares * price_per_share) AS dollar_value,
           MIN(trans_date)               AS first_trade_date
    FROM transactions
    WHERE trans_code = 'P'
      AND acquired_disposed = 'A'
      AND shares > 0
      AND price_per_share >= 1          -- skip penny stocks and blank prices
    GROUP BY accession_number
)
SELECT f.accession_number,
       f.issuer_cik,
       f.ticker,
       f.issuer_name,
       f.filing_date,
       b.first_trade_date,
       o.owner_cik,
       o.owner_name,
       CASE
           WHEN UPPER(o.title) LIKE '%CEO%' OR UPPER(o.title) LIKE '%CHIEF EXECUTIVE%' THEN 'CEO'
           WHEN UPPER(o.title) LIKE '%CFO%' OR UPPER(o.title) LIKE '%CHIEF FINANCIAL%' THEN 'CFO'
           WHEN UPPER(o.relationship) LIKE '%OFFICER%'  THEN 'Other officer'
           WHEN UPPER(o.relationship) LIKE '%DIRECTOR%' THEN 'Director'
           WHEN UPPER(o.relationship) LIKE '%TEN%'      THEN '10% owner'
           ELSE 'Other'
       END AS role,
       b.shares,
       b.dollar_value,
       f.is_10b5_1_plan
FROM buys b
JOIN filings f   ON f.accession_number = b.accession_number
JOIN one_owner o ON o.accession_number = b.accession_number AND o.rn = 1
WHERE f.ticker IS NOT NULL
  AND b.dollar_value >= 10000;          -- ignore token buys under $10K
