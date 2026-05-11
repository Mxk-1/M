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
        need = trend + 2   # 需要 62 根才能算 MA60 的严格穿越

        candidates = con.execute("""
            SELECT DISTINCT ts_code FROM daily
            WHERE trade_date <= ?
            GROUP BY ts_code HAVING COUNT(*) >= ?
        """, [trade_date, need]).fetchall()

        signals = []
        for (ts_code,) in candidates:
            hist = con.execute("""
                SELECT close, vol FROM daily
                WHERE ts_code = ? AND trade_date <= ?
                ORDER BY trade_date DESC LIMIT ?
            """, [ts_code, trade_date, trend + 2]).fetchall()
            hist = list(reversed(hist))
            closes = [r[0] for r in hist]
            vols   = [r[1] for r in hist]
            if len(closes) < long_ + 2:
                continue

            ma5_t  = sum(closes[-(short):])  / short
            ma5_y  = sum(closes[-(short+1):-1]) / short
            ma10_t = sum(closes[-(long_):])  / long_
            ma10_y = sum(closes[-(long_+1):-1]) / long_

            # 量比（今日量 / 5日均量）
            vol_today  = vols[-1]
            avg_vol5   = sum(vols[-6:-1]) / 5 if len(vols) >= 6 else vol_today
            vol_ratio  = vol_today / avg_vol5 if avg_vol5 > 0 else 1.0

            signal_type = None
            score       = 60.0

            # 条件 1：MA5 严格上穿 MA10（昨日在下方，今日在上方）
            # 额外要求今日量比 ≥ 1.2（有量支撑）
            if ma5_t > ma10_t and ma5_y <= ma10_y and vol_ratio >= 1.2:
                signal_type = "MA5上穿MA10"
                score = 65.0 + min(10.0, (vol_ratio - 1.2) * 5)

            # 条件 2：价格严格站上 MA60（昨低于MA60，今高于MA60）
            if signal_type is None and len(closes) >= trend + 1:
                ma60_t = sum(closes[-trend:])    / trend
                ma60_y = sum(closes[-(trend+1):-1]) / trend
                if closes[-1] > ma60_t and closes[-2] <= ma60_y and vol_ratio >= 1.5:
                    signal_type = "站上MA60"
                    score = 68.0 + min(12.0, (vol_ratio - 1.5) * 4)

            if signal_type is None:
                continue

            # 额外过滤：今日必须是阳线
            pct_row = con.execute(
                "SELECT pct_chg, open, close FROM daily WHERE ts_code=? AND trade_date=?",
                [ts_code, trade_date]
            ).fetchone()
            if not pct_row or pct_row[2] <= pct_row[1]:  # 非阳线过滤
                continue
            pct_chg = pct_row[0]

            name_row = con.execute(
                "SELECT name FROM stock_basic WHERE ts_code=?", [ts_code]
            ).fetchone()
            name = name_row[0] if name_row else ts_code

            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=round(min(100.0, score), 1),
                pct_chg=pct_chg, vol_ratio=round(vol_ratio, 2),
                triggered=[self.name],
                extra={
                    "signal_type": signal_type,
                    "ma5": round(ma5_t, 2), "ma10": round(ma10_t, 2),
                    "vol_ratio": round(vol_ratio, 2),
                },
            ))
        return signals
