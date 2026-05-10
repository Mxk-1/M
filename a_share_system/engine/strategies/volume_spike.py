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
        vol_min = p["vol_ratio_min"]
        pct_min = p["pct_chg_min"]

        rows = con.execute(f"""
            WITH avg5 AS (
                SELECT ts_code, AVG(vol) AS avg_vol
                FROM (
                    SELECT ts_code, vol,
                           ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
                    FROM daily
                    WHERE trade_date < {trade_date}
                ) t WHERE rn <= 5
                GROUP BY ts_code
            )
            SELECT d.ts_code,
                   COALESCE(s.name, d.ts_code),
                   d.pct_chg,
                   d.vol / a.avg_vol AS vol_ratio
            FROM daily d
            JOIN avg5 a ON d.ts_code = a.ts_code
            LEFT JOIN stock_basic s ON d.ts_code = s.ts_code
            WHERE d.trade_date = {trade_date}
              AND a.avg_vol > 0
              AND d.vol / a.avg_vol >= {vol_min}
              AND d.pct_chg >= {pct_min}
        """).fetchall()

        return [
            Signal(
                ts_code=r[0], name=r[1],
                trade_date=trade_date, strategy=self.name,
                score=min(100.0, 50.0 + r[3] * 10),
                pct_chg=r[2], vol_ratio=round(r[3], 2),
                triggered=[self.name],
            )
            for r in rows
        ]
