# a_share_system/engine/runner.py
import duckdb
from a_share_system.engine.signal import Signal
from a_share_system.engine.strategies.limit_up import LimitUpStrategy
from a_share_system.engine.strategies.volume_spike import VolumeSpikeStrategy
from a_share_system.engine.strategies.consecutive import ConsecutiveStrategy
from a_share_system.engine.strategies.ma_breakout import MaBreakoutStrategy
from a_share_system.engine.strategies.macd_cross import MacdCrossStrategy
from a_share_system.engine.strategies.macd_divergence import MacdDivergenceStrategy
from a_share_system.engine.strategies.big_money import BigMoneyStrategy
from a_share_system.engine.strategies.pullback import PullbackStrategy
from a_share_system.engine.strategies.sector_hot import SectorHotStrategy
from a_share_system.engine.strategies.top_list_buy import TopListBuyStrategy
from a_share_system.engine.strategies.brooks_h2 import BrooksH2Strategy
from a_share_system.engine.strategies.resonance import ResonanceStrategy

STRATEGIES = [
    LimitUpStrategy(),
    VolumeSpikeStrategy(),
    ConsecutiveStrategy(),
    MaBreakoutStrategy(),
    MacdCrossStrategy(),
    MacdDivergenceStrategy(),
    BigMoneyStrategy(),
    PullbackStrategy(),
    SectorHotStrategy(),
    TopListBuyStrategy(),
    BrooksH2Strategy(),
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
    import time
    import sys

    all_signals: list[Signal] = []
    total = len(STRATEGIES) + 1   # +1 for resonance
    width = max(len(s.display_name) for s in STRATEGIES) + 2

    t0_total = time.time()

    for i, strategy in enumerate(STRATEGIES, 1):
        label = f"{strategy.display_name}"
        # 打印进度前缀
        bar = f"[{i:2d}/{total}]"
        print(f"  {bar} {label:<{width}} ...", end="", flush=True)
        t0 = time.time()
        try:
            found = strategy.scan(con, trade_date)
            all_signals.extend(found)
            elapsed = time.time() - t0
            print(f"\r  {bar} {label:<{width}} {len(found):4d} 条  {elapsed:.1f}s")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"\r  {bar} {label:<{width}} ⚠ 出错: {e}")

    # 共振
    bar = f"[{total:2d}/{total}]"
    label = "多策略共振"
    print(f"  {bar} {label:<{width}} ...", end="", flush=True)
    t0 = time.time()
    resonance = ResonanceStrategy().detect(all_signals)
    all_signals.extend(resonance)
    elapsed = time.time() - t0
    print(f"\r  {bar} {label:<{width}} {len(resonance):4d} 条  {elapsed:.1f}s")

    print(f"  {'─'*40}")
    save_signals(con, all_signals)
    total_time = time.time() - t0_total
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
