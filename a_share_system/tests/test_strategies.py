# a_share_system/tests/test_strategies.py
import duckdb
import pytest
from a_share_system.data.db import init_schema


def make_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    init_schema(con)
    con.execute("""
        INSERT INTO stock_basic VALUES
        ('600111.SH', '北方稀土', '小金属', 19970924),
        ('600519.SH', '贵州茅台', '白酒',   20010827),
        ('300750.SZ', '宁德时代', '电池',   20180611)
    """)
    return con


def insert_daily(con, rows: list[tuple]) -> None:
    for row in rows:
        con.execute(
            "INSERT OR IGNORE INTO daily VALUES (?,?,?,?,?,?,?,?,?,?,?)", row
        )


# ---------- LimitUp ----------
def test_limit_up_detects_limit_up_stock():
    from a_share_system.engine.strategies.limit_up import LimitUpStrategy
    con = make_db()
    insert_daily(con, [
        ("600111.SH", 20260508, 50.0, 55.0, 49.5, 55.0, 50.0, 9.98, 9.98, 1000000, 5000000),
    ])
    signals = LimitUpStrategy().scan(con, 20260508)
    assert len(signals) == 1
    assert signals[0].ts_code == "600111.SH"
    assert signals[0].strategy == "LIMIT_UP"


def test_limit_up_ignores_non_limit_stock():
    from a_share_system.engine.strategies.limit_up import LimitUpStrategy
    con = make_db()
    insert_daily(con, [
        ("600519.SH", 20260508, 1800.0, 1850.0, 1790.0, 1820.0, 1800.0, 20.0, 1.11, 50000, 9000000),
    ])
    signals = LimitUpStrategy().scan(con, 20260508)
    assert len(signals) == 0


# ---------- VolumeSpike ----------
def test_volume_spike_detects_spike():
    from a_share_system.engine.strategies.volume_spike import VolumeSpikeStrategy
    con = make_db()
    for d in [20260502, 20260503, 20260506, 20260507]:
        insert_daily(con, [("300750.SZ", d, 100.0, 102.0, 99.0, 101.0, 100.0, 1.0, 1.0, 100000, 10000000)])
    insert_daily(con, [("300750.SZ", 20260508, 101.0, 106.0, 100.5, 105.0, 101.0, 4.0, 3.96, 350000, 36000000)])
    signals = VolumeSpikeStrategy().scan(con, 20260508)
    assert len(signals) == 1
    assert signals[0].ts_code == "300750.SZ"
    assert signals[0].vol_ratio > 3.0


def test_volume_spike_ignores_low_volume():
    from a_share_system.engine.strategies.volume_spike import VolumeSpikeStrategy
    con = make_db()
    for d in [20260502, 20260503, 20260506, 20260507]:
        insert_daily(con, [("300750.SZ", d, 100.0, 102.0, 99.0, 101.0, 100.0, 1.0, 1.0, 100000, 10000000)])
    insert_daily(con, [("300750.SZ", 20260508, 101.0, 106.0, 100.5, 105.0, 101.0, 4.0, 3.96, 150000, 15000000)])
    signals = VolumeSpikeStrategy().scan(con, 20260508)
    assert len(signals) == 0


# ---------- Consecutive ----------
def test_consecutive_detects_2_boards():
    from a_share_system.engine.strategies.consecutive import ConsecutiveStrategy
    con = make_db()
    insert_daily(con, [
        ("600111.SH", 20260507, 50.0, 55.0, 49.5, 55.0, 50.0, 5.0, 10.0, 1000000, 5000000),
        ("600111.SH", 20260508, 55.0, 60.5, 54.5, 60.5, 55.0, 5.5, 10.0, 1200000, 7000000),
    ])
    signals = ConsecutiveStrategy().scan(con, 20260508)
    assert len(signals) == 1
    assert signals[0].boards == 2


def test_consecutive_ignores_single_board():
    from a_share_system.engine.strategies.consecutive import ConsecutiveStrategy
    con = make_db()
    insert_daily(con, [
        ("600111.SH", 20260507, 50.0, 52.0, 49.5, 51.0, 50.0, 1.0, 2.0, 500000, 2500000),
        ("600111.SH", 20260508, 51.0, 56.1, 50.5, 56.1, 51.0, 5.1, 10.0, 1200000, 6500000),
    ])
    signals = ConsecutiveStrategy().scan(con, 20260508)
    assert len(signals) == 0


# ---------- MA Breakout ----------
def test_ma_breakout_detects_ma5_cross_ma10():
    from a_share_system.engine.strategies.ma_breakout import MaBreakoutStrategy
    con = make_db()
    # 前9天均价100，今天收盘115 → MA5 会超过 MA10
    for d, c in zip(
        [20260425, 20260426, 20260427, 20260428, 20260429,
         20260502, 20260503, 20260506, 20260507],
        [100] * 9
    ):
        insert_daily(con, [("600111.SH", d, float(c), float(c)+1, float(c)-1, float(c), float(c), 0.0, 0.0, 500000, 50000000)])
    insert_daily(con, [("600111.SH", 20260508, 100.0, 116.0, 99.0, 115.0, 100.0, 0.0, 15.0, 800000, 90000000)])
    signals = MaBreakoutStrategy().scan(con, 20260508)
    assert len(signals) >= 1
    assert signals[0].ts_code == "600111.SH"


# ---------- MACD Cross ----------
def test_macd_cross_detects_golden_cross():
    from a_share_system.engine.strategies.macd_cross import MacdCrossStrategy
    con = make_db()
    prices = [100 - i * 0.5 for i in range(28)] + [90.0, 95.0]
    dates = [20260301, 20260302, 20260303, 20260304, 20260305,
             20260306, 20260309, 20260310, 20260311, 20260312,
             20260313, 20260316, 20260317, 20260318, 20260319,
             20260320, 20260323, 20260324, 20260325, 20260326,
             20260327, 20260330, 20260331, 20260401, 20260402,
             20260403, 20260407, 20260408, 20260409, 20260410]
    for d, p in zip(dates, prices):
        insert_daily(con, [("600111.SH", d, p, p+1, p-1, p, p, 0.0, 0.0, 500000, 500000*p)])
    signals = MacdCrossStrategy().scan(con, 20260410)
    assert isinstance(signals, list)


# ---------- MACD Divergence ----------
def test_macd_divergence_returns_list():
    from a_share_system.engine.strategies.macd_divergence import MacdDivergenceStrategy
    con = make_db()
    prices = [100 - i * 0.3 for i in range(60)]
    dates = list(range(20260101, 20260101 + 60))
    for d, p in zip(dates, prices):
        insert_daily(con, [("600111.SH", d, p, p+1, p-1, p, p, 0.0, 0.0, 500000, 500000*p)])
    signals = MacdDivergenceStrategy().scan(con, dates[-1])
    assert isinstance(signals, list)


# ---------- Brooks H2 ----------
def _seed_brooks(con):
    """构造一只上行→浅回调→H2 的合成 K 线（含 adj_factor，使 daily_qfq 可用）。"""
    import datetime
    bars = []          # (date, o, h, l, c, pct)
    base = datetime.date(2026, 1, 1)
    price = 10.0
    seq = 0

    def nextdate():
        nonlocal seq
        d = base + datetime.timedelta(days=seq)
        seq += 1
        return int(d.strftime("%Y%m%d"))

    # 70 根稳步上行阳趋势棒 → EMA20 上行、always_in=LONG（满足上市≥60交易日）
    for _ in range(70):
        o = price
        c = price + 0.25
        bars.append((nextdate(), o, c + 0.03, o - 0.03, c, 2.5))
        price = c
    top = price
    # 浅回调腿1（high 递减，回调 close 不破 ema20×0.97）
    bars.append((nextdate(), top, top + 0.01, top - 0.25, top - 0.2, -1.5))
    bars.append((nextdate(), top - 0.2, top - 0.18, top - 0.4, top - 0.35, -1.2))
    # H1：higher-high
    bars.append((nextdate(), top - 0.35, top + 0.08, top - 0.38, top - 0.1, 1.5))
    # 回调新低
    bars.append((nextdate(), top - 0.1, top - 0.05, top - 0.45, top - 0.4, -1.2))
    # H2：higher-high，收在区间上半
    bars.append((nextdate(), top - 0.4, top + 0.05, top - 0.42, top + 0.02, 1.5))

    rows = []
    prev_close = None
    for d, o, h, l, c, pct in bars:
        pre = prev_close if prev_close is not None else o
        # daily: (ts, date, open, high, low, close, pre_close, change, pct_chg, vol, amount)
        rows.append(("600111.SH", d, o, h, l, c, pre, c - pre, pct, 5_000_000, 2.0e8))
        con.execute(
            "INSERT OR IGNORE INTO adj_factor VALUES (?,?,?)", ("600111.SH", d, 1.0)
        )
        prev_close = c
    insert_daily(con, rows)
    return rows[-1][1]   # 最后一个交易日


def test_brooks_h2_detects_h2_setup():
    from a_share_system.engine.strategies.brooks_h2 import BrooksH2Strategy
    con = make_db()
    last_date = _seed_brooks(con)
    signals = BrooksH2Strategy().scan(con, last_date)
    assert isinstance(signals, list)
    assert len(signals) == 1
    s = signals[0]
    assert s.ts_code == "600111.SH"
    assert s.strategy == "BROOKS_H2"
    # 风控字段齐备
    assert "stop_price" in s.extra and "target_2r" in s.extra
    assert s.score >= 60.0


def test_brooks_h2_skips_st_and_low_amount():
    from a_share_system.engine.strategies.brooks_h2 import BrooksH2Strategy
    con = make_db()
    # 600111 名称改成 ST → 应被过滤
    con.execute("UPDATE stock_basic SET name='ST北方' WHERE ts_code='600111.SH'")
    last_date = _seed_brooks(con)
    signals = BrooksH2Strategy().scan(con, last_date)
    assert all(s.ts_code != "600111.SH" for s in signals)


def test_brooks_h2_returns_empty_on_downtrend():
    from a_share_system.engine.strategies.brooks_h2 import BrooksH2Strategy
    con = make_db()
    rows = []
    price = 50.0
    prev = None
    for i in range(70):
        d = 20260101 + i
        o = price
        c = price - 0.3
        pre = prev if prev is not None else o
        rows.append(("600519.SH", d, o + 0.02, o + 0.02, c - 0.02, c, pre, c - pre, -2.0, 5_000_000, 2.0e8))
        con.execute("INSERT OR IGNORE INTO adj_factor VALUES (?,?,?)", ("600519.SH", d, 1.0))
        prev = c
        price = c
    insert_daily(con, rows)
    signals = BrooksH2Strategy().scan(con, rows[-1][1])
    assert all(s.ts_code != "600519.SH" for s in signals)
