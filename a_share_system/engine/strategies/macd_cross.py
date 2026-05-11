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


def _calc_dif_dea(closes: list[float], fast: int, slow: int, sig: int) -> tuple:
    """返回 (dif_today, dea_today, dif_yest, dea_yest)"""
    if len(closes) < slow + sig:
        return None, None, None, None
    difs = []
    for i in range(slow, len(closes) + 1):
        e12 = _ema(closes[:i], fast)
        e26 = _ema(closes[:i], slow)
        if e12 is not None and e26 is not None:
            difs.append(e12 - e26)
    if len(difs) < sig + 1:
        return None, None, None, None
    dea_today = _ema(difs, sig)
    dea_yest  = _ema(difs[:-1], sig)
    return difs[-1], dea_today, difs[-2], dea_yest


class MacdCrossStrategy(BaseStrategy):
    name = "MACD_CROSS"
    display_name = "MACD金叉"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        p   = STRATEGY_PARAMS["MACD_CROSS"]
        need = p["ema_slow"] + p["signal"] + 10

        # 批量拉取所有候选股的历史收盘价（一次 SQL，不逐股查）
        all_hist = con.execute("""
            SELECT ts_code, close, trade_date
            FROM daily
            WHERE trade_date <= ? AND ts_code IN (
                SELECT ts_code FROM daily
                WHERE trade_date <= ?
                GROUP BY ts_code HAVING COUNT(*) >= ?
            )
            ORDER BY ts_code, trade_date ASC
        """, [trade_date, trade_date, need]).fetchall()

        # 按股票分组
        from collections import defaultdict
        stock_closes: dict[str, list[float]] = defaultdict(list)
        for ts_code, close, _ in all_hist:
            stock_closes[ts_code].append(close)

        # 批量查名称和今日涨幅
        info = con.execute("""
            SELECT d.ts_code, COALESCE(s.name, d.ts_code), d.pct_chg, d.open, d.close,
                   d.vol, COALESCE(a5.avg_vol5, d.vol) AS avg_vol5
            FROM daily d
            LEFT JOIN stock_basic s ON d.ts_code = s.ts_code
            LEFT JOIN (
                SELECT ts_code, AVG(vol) AS avg_vol5
                FROM (
                    SELECT ts_code, vol,
                           ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
                    FROM daily WHERE trade_date < ?
                ) t WHERE rn <= 5 GROUP BY ts_code
            ) a5 ON d.ts_code = a5.ts_code
            WHERE d.trade_date = ?
        """, [trade_date, trade_date]).fetchall()
        info_map = {r[0]: r for r in info}

        signals = []
        for ts_code, closes in stock_closes.items():
            dif, dea, dif_y, dea_y = _calc_dif_dea(
                closes, p["ema_fast"], p["ema_slow"], p["signal"]
            )
            if None in (dif, dea, dif_y, dea_y):
                continue
            # 严格金叉：昨日 DIF ≤ DEA，今日 DIF > DEA
            if not (dif > dea and dif_y <= dea_y):
                continue

            row = info_map.get(ts_code)
            if not row:
                continue
            _, name, pct_chg, open_p, close, vol, avg_vol5 = row

            # 过滤：今日必须是阳线（close > open）
            if close <= open_p:
                continue

            # 量比
            vol_ratio = round(vol / avg_vol5, 2) if avg_vol5 > 0 else 1.0

            # 分类与评分
            if dif > 0:
                position = "零轴上方"
                score = 70.0 + min(10.0, dif * 20)         # 零轴上金叉：强势延续
            else:
                position = "零轴下方"
                score = 55.0 + min(10.0, abs(dif) * 10)    # 零轴下金叉：底部反转，但风险较高

            # 量比加分
            score += min(5.0, (vol_ratio - 1) * 2)
            score = round(min(100.0, score), 1)

            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=score, pct_chg=pct_chg,
                vol_ratio=vol_ratio,
                triggered=[self.name],
                extra={"dif": round(dif, 3), "dea": round(dea, 3), "position": position},
            ))
        return signals
