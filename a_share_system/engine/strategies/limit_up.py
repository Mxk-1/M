# a_share_system/engine/strategies/limit_up.py
import duckdb
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


class LimitUpStrategy(BaseStrategy):
    name = "LIMIT_UP"
    display_name = "N字涨停"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        threshold = STRATEGY_PARAMS["LIMIT_UP"]["threshold"]
        rows = con.execute(f"""
            SELECT d.ts_code,
                   COALESCE(s.name, d.ts_code) AS name,
                   d.pct_chg,
                   CASE WHEN d.vol > 0 AND prev.avg_vol > 0
                        THEN d.vol / prev.avg_vol ELSE 1.0 END AS vol_ratio
            FROM daily d
            LEFT JOIN stock_basic s ON d.ts_code = s.ts_code
            LEFT JOIN (
                SELECT ts_code, AVG(vol) AS avg_vol
                FROM daily
                WHERE trade_date < {trade_date}
                GROUP BY ts_code
            ) prev ON d.ts_code = prev.ts_code
            WHERE d.trade_date = {trade_date}
              AND d.pct_chg >= {threshold}
        """).fetchall()

        signals = []
        for ts_code, name, pct_chg, vol_ratio in rows:
            score = min(100.0, 60.0 + pct_chg * 4)
            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=score, pct_chg=pct_chg,
                vol_ratio=round(vol_ratio, 2),
                triggered=[self.name],
            ))
        return signals
