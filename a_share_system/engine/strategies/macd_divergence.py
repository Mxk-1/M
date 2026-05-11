# a_share_system/engine/strategies/macd_divergence.py
import duckdb
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal
from a_share_system.engine.strategies.macd_cross import _ema


def _find_price_lows(prices: list[float], window: int = 3) -> list[tuple[int, float]]:
    """找局部低点，window 内左右各 window 根都高于它"""
    lows = []
    for i in range(window, len(prices) - window):
        if all(prices[i] <= prices[j] for j in range(i - window, i + window + 1) if j != i):
            lows.append((i, prices[i]))
    return lows


class MacdDivergenceStrategy(BaseStrategy):
    name = "MACD_DIVERGENCE"
    display_name = "MACD底背离"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        p = STRATEGY_PARAMS["MACD_DIVERGENCE"]
        lookback = p["lookback"]    # 回看 30 根
        need = 60

        # 批量拉数据
        all_hist = con.execute("""
            SELECT ts_code, close, pct_chg, open
            FROM daily
            WHERE trade_date <= ? AND ts_code IN (
                SELECT ts_code FROM daily
                WHERE trade_date <= ?
                GROUP BY ts_code HAVING COUNT(*) >= ?
            )
            ORDER BY ts_code, trade_date ASC
        """, [trade_date, trade_date, need]).fetchall()

        from collections import defaultdict
        stock_data: dict[str, list] = defaultdict(list)
        for ts_code, close, pct_chg, open_p in all_hist:
            stock_data[ts_code].append((close, pct_chg, open_p))

        info_map = {}
        rows = con.execute(
            "SELECT ts_code, COALESCE(name, ts_code) FROM stock_basic"
        ).fetchall()
        for ts_code, name in rows:
            info_map[ts_code] = name

        signals = []
        for ts_code, records in stock_data.items():
            closes   = [r[0] for r in records]
            today_pct  = records[-1][1]
            today_open = records[-1][2]
            today_close = closes[-1]

            if len(closes) < 40:
                continue

            # 今日必须是阳线且涨幅 ≥ 1%（明确的反弹确认）
            if today_close <= today_open or today_pct < 1.0:
                continue

            # 计算 DIF 序列
            difs = []
            for i in range(26, len(closes) + 1):
                e12 = _ema(closes[:i], 12)
                e26 = _ema(closes[:i], 26)
                if e12 is not None and e26 is not None:
                    difs.append(e12 - e26)

            if len(difs) < lookback:
                continue

            recent_closes = closes[-lookback:]
            recent_difs   = difs[-lookback:]

            # 找最近 lookback 内的局部价格低点（window=3，允许更多形态）
            price_lows = _find_price_lows(recent_closes, window=3)
            if len(price_lows) < 2:
                continue

            # 取最后两个低点
            idx1, p1 = price_lows[-2]
            idx2, p2 = price_lows[-1]

            # 价格：第二低点必须低于第一低点（下降趋势）
            if p2 >= p1:
                continue

            # DIF：第二低点对应的 DIF 必须高于第一低点（背离）
            if idx1 >= len(recent_difs) or idx2 >= len(recent_difs):
                continue
            dif1 = recent_difs[idx1]
            dif2 = recent_difs[idx2]

            # 背离条件：dif2 > dif1（DIF 不创新低）
            # 且 DIF 仍在零轴下方（真正的底部区域）
            if not (dif2 > dif1 and dif2 < 0):
                continue

            # 价格下跌幅度：越深越有意义
            drop_pct = (p1 - p2) / p1 * 100

            # 评分：下跌深度 + DIF 背离幅度 + 今日涨幅
            diverge_strength = (dif2 - dif1) / (abs(dif1) + 1e-6)
            score = 65.0 + min(15.0, drop_pct * 1.5) + min(10.0, diverge_strength * 20)
            score = round(min(100.0, score), 1)

            name = info_map.get(ts_code, ts_code)
            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=score, pct_chg=today_pct, vol_ratio=1.0,
                triggered=[self.name],
                extra={
                    "low1": round(p1, 2), "low2": round(p2, 2),
                    "dif1": round(dif1, 3), "dif2": round(dif2, 3),
                    "drop_pct": round(drop_pct, 1),
                },
            ))
        return signals
