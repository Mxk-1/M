# a_share_system/engine/strategies/limit_up.py
import duckdb
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


def _limit_threshold(ts_code: str) -> float:
    """科创(688.SH)和创业(300/301.SZ)涨停线 20%，其余 10%"""
    if ts_code.startswith('688') and ts_code.endswith('.SH'):
        return 19.5
    if ts_code.endswith('.SZ') and (ts_code.startswith('300') or ts_code.startswith('301')):
        return 19.5
    if ts_code.endswith('.BJ'):
        return 29.5   # 北交所 30%
    return 9.5


class LimitUpStrategy(BaseStrategy):
    name = "LIMIT_UP"
    display_name = "N字涨停"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        # 1. 取当日所有疑似涨停（涨幅 ≥ 9.5%）
        rows = con.execute("""
            SELECT d.ts_code,
                   COALESCE(s.name, d.ts_code) AS name,
                   d.pct_chg,
                   d.close,
                   d.open,
                   d.vol,
                   d.amount,
                   a5.avg_vol5
            FROM daily d
            LEFT JOIN stock_basic s ON d.ts_code = s.ts_code
            LEFT JOIN (
                SELECT ts_code, AVG(vol) AS avg_vol5
                FROM (
                    SELECT ts_code, vol,
                           ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
                    FROM daily WHERE trade_date < ?
                ) t WHERE rn <= 5
                GROUP BY ts_code
            ) a5 ON d.ts_code = a5.ts_code
            WHERE d.trade_date = ? AND d.pct_chg >= 9.5
        """, [trade_date, trade_date]).fetchall()

        # 2. 查 limit_list 获取开板次数和封单
        ll_map = {}
        ll_rows = con.execute(
            "SELECT ts_code, open_times, fd_amount FROM limit_list WHERE trade_date = ?",
            [trade_date]
        ).fetchall()
        for ts_code, open_times, fd_amount in ll_rows:
            ll_map[ts_code] = (open_times or 0, fd_amount or 0)

        signals = []
        for ts_code, name, pct_chg, close, open_p, vol, amount, avg_vol5 in rows:
            # 过滤：必须达到该股票对应的涨停线
            if pct_chg < _limit_threshold(ts_code):
                continue

            open_times, fd_amount = ll_map.get(ts_code, (0, 0))

            # 量比（5日均量）
            vol_ratio = round(vol / avg_vol5, 2) if avg_vol5 and avg_vol5 > 0 else 1.0

            # 一字板（开盘即涨停）：open == close，加分
            is_one_word = abs(open_p - close) / close < 0.001

            # 评分逻辑：
            # 基础分 65，一字板 +10，零开板 +10，多次开板 -10/次，量比放大适当加分
            score = 65.0
            if is_one_word:
                score += 10
            if open_times == 0:
                score += 10
            else:
                score -= open_times * 10   # 每开一次板扣 10 分
            score += min(10.0, (vol_ratio - 1) * 3)
            score = round(max(20.0, min(100.0, score)), 1)

            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=score, pct_chg=pct_chg,
                vol_ratio=vol_ratio,
                triggered=[self.name],
                extra={
                    "open_times": open_times,
                    "fd_amount": fd_amount,
                    "one_word": is_one_word,
                },
            ))
        return signals
