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
