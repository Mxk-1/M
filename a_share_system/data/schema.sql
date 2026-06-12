-- a_share_system/data/schema.sql

CREATE TABLE IF NOT EXISTS daily (
    ts_code    VARCHAR NOT NULL,
    trade_date INTEGER NOT NULL,
    open       DOUBLE,
    high       DOUBLE,
    low        DOUBLE,
    close      DOUBLE,
    pre_close  DOUBLE,
    change     DOUBLE,
    pct_chg    DOUBLE,
    vol        DOUBLE,
    amount     DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS index_daily (
    ts_code    VARCHAR NOT NULL,
    trade_date INTEGER NOT NULL,
    close      DOUBLE,
    pct_chg    DOUBLE,
    vol        DOUBLE,
    amount     DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS moneyflow (
    ts_code        VARCHAR NOT NULL,
    trade_date     INTEGER NOT NULL,
    net_mf_amount  DOUBLE,
    buy_lg_amount  DOUBLE,
    sell_lg_amount DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS limit_list (
    ts_code    VARCHAR NOT NULL,
    trade_date INTEGER NOT NULL,
    lmt        VARCHAR,
    fd_amount  DOUBLE,
    open_times INTEGER,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS top_list (
    ts_code    VARCHAR NOT NULL,
    trade_date INTEGER NOT NULL,
    net_amount DOUBLE,
    reason     VARCHAR,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS daily_basic (
    ts_code      VARCHAR NOT NULL,
    trade_date   INTEGER NOT NULL,
    pe_ttm       DOUBLE,
    pb           DOUBLE,
    ps_ttm       DOUBLE,
    total_mv     DOUBLE,
    circ_mv      DOUBLE,
    turnover_rate DOUBLE,
    volume_ratio DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS adj_factor (
    ts_code    VARCHAR NOT NULL,
    trade_date INTEGER NOT NULL,
    adj_factor DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS stock_basic (
    ts_code   VARCHAR PRIMARY KEY,
    name      VARCHAR,
    industry  VARCHAR,
    list_date INTEGER
);

CREATE TABLE IF NOT EXISTS news (
    url        VARCHAR PRIMARY KEY,
    ts_code    VARCHAR,
    pub_date   VARCHAR,
    title      VARCHAR NOT NULL,
    source     VARCHAR,
    summary    VARCHAR,
    keyword    VARCHAR,
    saved_at   VARCHAR
);

CREATE TABLE IF NOT EXISTS signals (
    ts_code    VARCHAR  NOT NULL,
    trade_date INTEGER  NOT NULL,
    strategy   VARCHAR  NOT NULL,
    score      DOUBLE,
    triggered  VARCHAR,
    pct_chg    DOUBLE,
    vol_ratio  DOUBLE,
    boards     INTEGER  DEFAULT 0,
    PRIMARY KEY (ts_code, trade_date, strategy)
);

-- 后复权：价格 × 复权因子，锚定上市首日，历史值恒定，适合回测
CREATE OR REPLACE VIEW daily_hfq AS
SELECT d.ts_code, d.trade_date,
       d.open  * a.adj_factor AS open,
       d.high  * a.adj_factor AS high,
       d.low   * a.adj_factor AS low,
       d.close * a.adj_factor AS close,
       d.pct_chg, d.vol, d.amount
FROM daily d
JOIN adj_factor a ON d.ts_code = a.ts_code AND d.trade_date = a.trade_date;

-- 前复权：价格 × 复权因子 ÷ 该股最新因子，锚定最新价，适合看图和形态分析
CREATE OR REPLACE VIEW daily_qfq AS
SELECT d.ts_code, d.trade_date,
       d.open  * a.adj_factor / l.latest_factor AS open,
       d.high  * a.adj_factor / l.latest_factor AS high,
       d.low   * a.adj_factor / l.latest_factor AS low,
       d.close * a.adj_factor / l.latest_factor AS close,
       d.pct_chg, d.vol, d.amount
FROM daily d
JOIN adj_factor a ON d.ts_code = a.ts_code AND d.trade_date = a.trade_date
JOIN (
    SELECT ts_code, arg_max(adj_factor, trade_date) AS latest_factor
    FROM adj_factor GROUP BY ts_code
) l ON d.ts_code = l.ts_code;
