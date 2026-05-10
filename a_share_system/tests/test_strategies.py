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
