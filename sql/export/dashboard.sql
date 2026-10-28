-- Copy just what the dashboard needs into a small database (attached as "dash") that can be
-- committed to GitHub and served by Streamlit Community Cloud. Run from src/analyze.py.

-- Every analyzed buy, with a compact integer id.
CREATE TABLE dash.signals AS
SELECT ROW_NUMBER() OVER (ORDER BY filing_date, accession_number) AS event_id,
       accession_number, issuer_cik, ticker, issuer_name, filing_date, entry_date,
       owner_cik, owner_name, role, dollar_value, is_10b5_1_plan, insiders_last_30d,
       ret_1m, ret_3m, ret_6m, excess_1m, excess_3m, excess_6m
FROM forward_returns;

-- Event-study paths, keyed by event_id instead of the long accession number to keep the file small.
CREATE TABLE dash.event_paths AS
SELECT s.event_id, ep.day, ep.excess
FROM event_paths ep
JOIN dash.signals s ON s.accession_number = ep.accession_number;

-- The last 6 months of purchases (including ones too recent to have returns yet).
CREATE TABLE dash.latest_buys AS
SELECT pe.filing_date, pe.ticker, pe.issuer_name, pe.issuer_cik, pe.accession_number,
       pe.owner_name, pe.role, pe.dollar_value, pe.is_10b5_1_plan,
       fr.excess_1m, fr.excess_3m
FROM purchase_events pe
LEFT JOIN forward_returns fr ON fr.accession_number = pe.accession_number
WHERE pe.filing_date >= (SELECT date(MAX(filing_date), '-182 days') FROM purchase_events);

CREATE TABLE dash.meta AS
SELECT datetime('now')                                   AS built_at,
       (SELECT MIN(filing_date) FROM purchase_events)   AS first_filing,
       (SELECT MAX(filing_date) FROM purchase_events)   AS last_filing,
       (SELECT COUNT(*) FROM forward_returns)           AS analyzed_buys;

CREATE INDEX dash.idx_event_paths ON event_paths(event_id);
