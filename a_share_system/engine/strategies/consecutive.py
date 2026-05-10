# a_share_system/engine/strategies/consecutive.py
import duckdb
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


class ConsecutiveStrategy(BaseStrategy):
    name = "CONSECUTIVE"
    display_name = "连板龙头"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        min_boards = STRATEGY_PARAMS["CONSECUTIVE"]["min_boards"]
        threshold = STRATEGY_PARAMS["LIMIT_UP"]["threshold"]

        today_limit = con.execute(f"""
            SELECT d.ts_code, COALESCE(s.name, d.ts_code), d.pct_chg, d.vol,
                   CASE WHEN prev.avg_vol > 0 THEN d.vol / prev.avg_vol ELSE 1.0 END AS vol_ratio
            FROM daily d
            LEFT JOIN stock_basic s ON d.ts_code = s.ts_code
            LEFT JOIN (
                SELECT ts_code, AVG(vol) AS avg_vol FROM daily
                WHERE trade_date < {trade_date} GROUP BY ts_code
            ) prev ON d.ts_code = prev.ts_code
            WHERE d.trade_date = {trade_date} AND d.pct_chg >= {threshold}
        """).fetchall()

        signals = []
        for ts_code, name, pct_chg, vol, vol_ratio in today_limit:
            hist = con.execute(f"""
                SELECT pct_chg FROM daily
                WHERE ts_code = '{ts_code}' AND trade_date < {trade_date}
                ORDER BY trade_date DESC LIMIT 10
            """).fetchall()

            boards = 1
            for row in hist:
                if row[0] >= threshold:
                    boards += 1
                else:
                    break

            if boards >= min_boards:
                score = min(100.0, 60.0 + boards * 8)
                signals.append(Signal(
                    ts_code=ts_code, name=name,
                    trade_date=trade_date, strategy=self.name,
                    score=score, pct_chg=pct_chg,
                    vol_ratio=round(vol_ratio, 2),
                    boards=boards,
                    triggered=[self.name],
                ))
        return signals
