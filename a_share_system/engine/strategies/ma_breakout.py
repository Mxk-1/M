# a_share_system/engine/strategies/ma_breakout.py
import duckdb
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


class MaBreakoutStrategy(BaseStrategy):
    name = "MA_BREAKOUT"
    display_name = "均线突破"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        p = STRATEGY_PARAMS["MA_BREAKOUT"]
        short, long_, trend = p["ma_short"], p["ma_long"], p["ma_trend"]
        # Need at least long_ rows to compute MA10 for today
        need_min = long_

        candidates = con.execute(f"""
            SELECT DISTINCT ts_code FROM daily
            WHERE trade_date <= {trade_date}
            GROUP BY ts_code HAVING COUNT(*) >= {need_min}
        """).fetchall()

        signals = []
        for (ts_code,) in candidates:
            hist = con.execute(f"""
                SELECT close FROM daily
                WHERE ts_code = '{ts_code}' AND trade_date <= {trade_date}
                ORDER BY trade_date DESC LIMIT {trend + 1}
            """).fetchall()
            closes = [r[0] for r in reversed(hist)]
            if len(closes) < need_min:
                continue

            ma5_today  = sum(closes[-short:]) / short
            ma10_today = sum(closes[-long_:]) / long_

            # MA60 only computed when enough data available
            ma60 = sum(closes[-trend:]) / trend if len(closes) >= trend + 1 else None

            signal_type = None

            # MA5 crossover MA10: check yesterday if enough data
            if len(closes) >= long_ + 1:
                ma5_yest  = sum(closes[-short-1:-1]) / short
                ma10_yest = sum(closes[-long_-1:-1]) / long_
                if ma5_today > ma10_today and ma5_yest <= ma10_yest:
                    signal_type = "MA5上穿MA10"
            else:
                # Only today's data — fire if MA5 > MA10 (bullish alignment)
                if ma5_today > ma10_today:
                    signal_type = "MA5上穿MA10"

            if signal_type is None:
                if ma60 is not None and closes[-1] > ma60 and closes[-2] <= ma60:
                    signal_type = "站上MA60"

            if signal_type is None:
                continue

            name_row = con.execute(
                f"SELECT name FROM stock_basic WHERE ts_code='{ts_code}'"
            ).fetchone()
            name = name_row[0] if name_row else ts_code
            pct_row = con.execute(
                f"SELECT pct_chg FROM daily WHERE ts_code='{ts_code}' AND trade_date={trade_date}"
            ).fetchone()
            pct_chg = pct_row[0] if pct_row else 0.0

            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=65.0, pct_chg=pct_chg, vol_ratio=1.0,
                triggered=[self.name],
                extra={"signal_type": signal_type,
                       "ma5": round(ma5_today, 2), "ma10": round(ma10_today, 2),
                       "ma60": round(ma60, 2) if ma60 is not None else None},
            ))
        return signals
