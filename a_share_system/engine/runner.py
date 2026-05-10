# a_share_system/engine/runner.py
import duckdb
from a_share_system.engine.signal import Signal
from a_share_system.engine.strategies.limit_up import LimitUpStrategy
from a_share_system.engine.strategies.volume_spike import VolumeSpikeStrategy
from a_share_system.engine.strategies.consecutive import ConsecutiveStrategy
from a_share_system.engine.strategies.ma_breakout import MaBreakoutStrategy
from a_share_system.engine.strategies.macd_cross import MacdCrossStrategy
from a_share_system.engine.strategies.macd_divergence import MacdDivergenceStrategy
from a_share_system.engine.strategies.resonance import ResonanceStrategy

STRATEGIES = [
    LimitUpStrategy(),
    VolumeSpikeStrategy(),
    ConsecutiveStrategy(),
    MaBreakoutStrategy(),
    MacdCrossStrategy(),
    MacdDivergenceStrategy(),
]


def save_signals(con: duckdb.DuckDBPyConnection, signals: list[Signal]) -> None:
    if not signals:
        return
    con.executemany(
        """
        INSERT OR REPLACE INTO signals
        (ts_code, trade_date, strategy, score, triggered, pct_chg, vol_ratio, boards)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (s.ts_code, s.trade_date, s.strategy, s.score,
             s.to_dict()["triggered"], s.pct_chg, s.vol_ratio, s.boards)
            for s in signals
        ],
    )


def run_daily(con: duckdb.DuckDBPyConnection, trade_date: int) -> int:
    all_signals: list[Signal] = []
    for strategy in STRATEGIES:
        try:
            found = strategy.scan(con, trade_date)
            all_signals.extend(found)
        except Exception as e:
            print(f"  ⚠ {strategy.name} 出错: {e}")

    resonance = ResonanceStrategy().detect(all_signals)
    all_signals.extend(resonance)

    save_signals(con, all_signals)
    return len(all_signals)


if __name__ == "__main__":
    from a_share_system.data.db import get_conn
    con = get_conn()
    latest = con.execute("SELECT MAX(trade_date) FROM daily").fetchone()[0]
    print(f"扫描 {latest}...")
    count = run_daily(con, latest)
    print(f"✅ 写入 {count} 个信号")
    result = con.execute(
        f"SELECT ts_code, score, triggered FROM signals WHERE trade_date={latest} AND strategy='RESONANCE' ORDER BY score DESC LIMIT 5"
    ).df()
    print(result.to_string(index=False))
