# a_share_system/engine/strategies/resonance.py
from collections import defaultdict
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.signal import Signal


class ResonanceStrategy:
    name = "RESONANCE"
    display_name = "多策略共振"

    def detect(self, signals: list[Signal]) -> list[Signal]:
        """输入所有策略信号，输出触发 >= min_strategies 个不同策略的共振 Signal"""
        min_n = STRATEGY_PARAMS["RESONANCE"]["min_strategies"]
        by_stock: dict[tuple, list[Signal]] = defaultdict(list)
        for s in signals:
            by_stock[(s.ts_code, s.trade_date)].append(s)

        resonance = []
        for (ts_code, trade_date), stock_signals in by_stock.items():
            strategies = list({s.strategy for s in stock_signals})
            if len(strategies) < min_n:
                continue
            base = stock_signals[0]
            score = min(100.0, 70.0 + len(strategies) * 8)
            resonance.append(Signal(
                ts_code=ts_code,
                name=base.name,
                trade_date=trade_date,
                strategy=self.name,
                score=score,
                pct_chg=base.pct_chg,
                vol_ratio=base.vol_ratio,
                boards=max(s.boards for s in stock_signals),
                triggered=strategies,
            ))
        resonance.sort(key=lambda s: s.score, reverse=True)
        return resonance
