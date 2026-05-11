# a_share_system/engine/strategies/volume_spike.py
import duckdb
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


class VolumeSpikeStrategy(BaseStrategy):
    name = "VOLUME_SPIKE"
    display_name = "突然爆量"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        p = STRATEGY_PARAMS["VOLUME_SPIKE"]
        vol_min = p["vol_ratio_min"]   # 默认 3.0
        pct_min = p["pct_chg_min"]     # 默认 3.0

        rows = con.execute("""
            WITH avg5 AS (
                SELECT ts_code, AVG(vol) AS avg_vol5
                FROM (
                    SELECT ts_code, vol,
                           ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
                    FROM daily WHERE trade_date < ?
                ) t WHERE rn <= 5
                GROUP BY ts_code
            )
            SELECT d.ts_code,
                   COALESCE(s.name, d.ts_code) AS name,
                   d.pct_chg,
                   d.open,
                   d.close,
                   d.vol / a.avg_vol5 AS vol_ratio,
                   d.amount,
                   d.amount / d.vol   AS avg_price    -- 近似均价，用于换手率估算
            FROM daily d
            JOIN avg5 a ON d.ts_code = a.ts_code
            LEFT JOIN stock_basic s ON d.ts_code = s.ts_code
            WHERE d.trade_date = ?
              AND a.avg_vol5 > 0
              AND d.vol / a.avg_vol5 >= ?
              AND d.pct_chg >= ?
              AND d.close > d.open          -- 必须阳线（实心）
              AND d.close > d.pre_close     -- 排除跳空低开大阳
        """, [trade_date, trade_date, vol_min, pct_min]).fetchall()

        signals = []
        for ts_code, name, pct_chg, open_p, close, vol_ratio, amount, avg_price in rows:
            # 成交额过小的票过滤（< 3000万，避免小盘无效爆量）
            if amount < 3000:   # amount 单位是千元
                continue

            # 评分：量比越大越高，涨幅适当加分
            score = 50.0 + min(20.0, (vol_ratio - vol_min) * 5) + min(15.0, pct_chg * 2)
            score = round(min(100.0, score), 1)

            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=score, pct_chg=pct_chg,
                vol_ratio=round(vol_ratio, 2),
                triggered=[self.name],
                extra={"amount_wan": round(amount / 10, 1)},
            ))
        return signals
