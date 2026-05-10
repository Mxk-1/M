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

CREATE TABLE IF NOT EXISTS stock_basic (
    ts_code   VARCHAR PRIMARY KEY,
    name      VARCHAR,
    industry  VARCHAR,
    list_date INTEGER
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
