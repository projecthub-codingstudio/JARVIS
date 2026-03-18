-- Sample SQL file for indexing tests
-- Database: stock_analysis

CREATE TABLE tbl_daily_price (
    code        VARCHAR(7)  NOT NULL,
    trade_date  VARCHAR(8)  NOT NULL,
    open_price  INT         NULL,
    high_price  INT         NULL,
    low_price   INT         NULL,
    close_price INT         NULL,
    volume      BIGINT      NULL,
    CONSTRAINT PK_tbl_daily_price PRIMARY KEY (code, trade_date)
);

CREATE INDEX idx_daily_price_date ON tbl_daily_price(trade_date);

-- 종목 마스터 테이블
CREATE TABLE tbl_stock_master (
    code        VARCHAR(7)  NOT NULL PRIMARY KEY,
    name        NVARCHAR(50) NOT NULL,
    market      CHAR(1)     NOT NULL,  -- K: KOSPI, Q: KOSDAQ
    sector      NVARCHAR(50) NULL,
    listed_date VARCHAR(8)  NULL
);
