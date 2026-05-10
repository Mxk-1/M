# a_share_system/engine/strategies/macd_divergence.py
import duckdb
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal
from a_share_system.engine.strategies.macd_cross import _ema


def _find_local_lows(data: list[float], window: int = 4) -> list[tuple[int, float]]:
    lows = []
    for i in range(window, len(data) - window):
        if all(data[i] <= data[j] for j in range(i - window, i + window + 1) if j != i):
            lows.append((i, data[i]))
    return lows[-2:] if len(lows) >= 2 else []


class MacdDivergenceStrategy(BaseStrategy):
    name = "MACD_DIVERGENCE"
    display_name = "MACD底背离"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        p = STRATEGY_PARAMS["MACD_DIVERGENCE"]
        lookback = p["lookback"]
        need = 60

        candidates = con.execute(f"""
            SELECT DISTINCT ts_code FROM daily
            WHERE trade_date <= {trade_date}
            GROUP BY ts_code HAVING COUNT(*) >= {need}
        """).fetchall()

        signals = []
        for (ts_code,) in candidates:
            hist = con.execute(f"""
                SELECT close, pct_chg FROM daily
                WHERE ts_code = '{ts_code}' AND trade_date <= {trade_date}
                ORDER BY trade_date ASC
            """).fetchall()
            closes = [r[0] for r in hist]
            today_pct = hist[-1][1]

            if len(closes) < 40:
                continue

            difs = []
            for i in range(26, len(closes) + 1):
                e12 = _ema(closes[:i], 12)
                e26 = _ema(closes[:i], 26)
                if e12 and e26:
                    difs.append(e12 - e26)

            if len(difs) < lookback:
                continue

            recent_closes = closes[-lookback:]
            recent_difs   = difs[-lookback:]

            price_lows = _find_local_lows(recent_closes)
            if len(price_lows) < 2:
                continue

            idx1, p1 = price_lows[0]
            idx2, p2 = price_lows[1]
            if p2 >= p1:
                continue

            dif1 = recent_difs[idx1] if idx1 < len(recent_difs) else 0
            dif2 = recent_difs[idx2] if idx2 < len(recent_difs) else 0
            if not (dif2 > dif1 and dif2 < 0):
                continue

            if today_pct <= 0:
                continue

            name_row = con.execute(
                f"SELECT name FROM stock_basic WHERE ts_code='{ts_code}'"
            ).fetchone()
            name = name_row[0] if name_row else ts_code

            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=72.0, pct_chg=today_pct, vol_ratio=1.0,
                triggered=[self.name],
                extra={"low1": round(p1, 2), "low2": round(p2, 2),
                       "dif1": round(dif1, 3), "dif2": round(dif2, 3)},
            ))
        return signals
