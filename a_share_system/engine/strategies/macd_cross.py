# a_share_system/engine/strategies/macd_cross.py
import duckdb
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _calc_dif_dea(closes: list[float], fast: int, slow: int, signal: int) -> tuple:
    """返回 (dif_today, dea_today, dif_yest, dea_yest)"""
    if len(closes) < slow + signal:
        return None, None, None, None
    difs = []
    for i in range(slow, len(closes) + 1):
        e12 = _ema(closes[:i], fast)
        e26 = _ema(closes[:i], slow)
        if e12 and e26:
            difs.append(e12 - e26)
    if len(difs) < signal:
        return None, None, None, None
    dea_today = _ema(difs, signal)
    dea_yest  = _ema(difs[:-1], signal) if len(difs) > signal else dea_today
    return difs[-1], dea_today, difs[-2] if len(difs) >= 2 else difs[-1], dea_yest


class MacdCrossStrategy(BaseStrategy):
    name = "MACD_CROSS"
    display_name = "MACD金叉"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        p = STRATEGY_PARAMS["MACD_CROSS"]
        need = p["ema_slow"] + p["signal"] + 5

        candidates = con.execute(f"""
            SELECT DISTINCT ts_code FROM daily
            WHERE trade_date <= {trade_date}
            GROUP BY ts_code HAVING COUNT(*) >= {need}
        """).fetchall()

        signals = []
        for (ts_code,) in candidates:
            hist = con.execute(f"""
                SELECT close FROM daily
                WHERE ts_code = '{ts_code}' AND trade_date <= {trade_date}
                ORDER BY trade_date ASC
            """).fetchall()
            closes = [r[0] for r in hist]

            dif, dea, dif_y, dea_y = _calc_dif_dea(
                closes, p["ema_fast"], p["ema_slow"], p["signal"]
            )
            if dif is None or dea is None or dif_y is None or dea_y is None:
                continue
            if not (dif > dea and dif_y <= dea_y):
                continue

            name_row = con.execute(
                f"SELECT name FROM stock_basic WHERE ts_code='{ts_code}'"
            ).fetchone()
            name = name_row[0] if name_row else ts_code
            pct_row = con.execute(
                f"SELECT pct_chg FROM daily WHERE ts_code='{ts_code}' AND trade_date={trade_date}"
            ).fetchone()
            pct_chg = pct_row[0] if pct_row else 0.0
            position = "零轴上方" if dif > 0 else "零轴下方"

            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=70.0 if dif > 0 else 55.0,
                pct_chg=pct_chg, vol_ratio=1.0,
                triggered=[self.name],
                extra={"dif": round(dif, 3), "dea": round(dea, 3), "position": position},
            ))
        return signals
