-- Number each ticker's trading days so "21 trading days later" becomes a simple join.
DROP TABLE IF EXISTS price_index;
CREATE TABLE price_index AS
SELECT ticker,
       date,
       close,
       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date) AS day_num
FROM prices;

CREATE INDEX idx_price_index_day  ON price_index(ticker, day_num);
CREATE INDEX idx_price_index_date ON price_index(ticker, date);
