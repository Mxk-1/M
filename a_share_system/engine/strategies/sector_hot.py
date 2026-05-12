# a_share_system/engine/strategies/sector_hot.py
"""
板块联动策略
核心逻辑：同行业当日涨停数 ≥ 3，且本股今日上涨 ≥ 2%
行业集体涨停说明主题正在发酵，跟进板块内尚未涨停的股票抓联动
"""
import duckdb
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


_INDUSTRY_LIMIT_MIN = 3    # 同行业至少 N 只涨停
_PCT_MIN            = 2.0  # 本股涨幅门槛


class SectorHotStrategy(BaseStrategy):
    name = "SECTOR_HOT"
    display_name = "板块联动"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        rows = con.execute("""
            WITH industry_heat AS (
                SELECT sb.industry, COUNT(*) AS limit_count
                FROM daily d
                JOIN stock_basic sb ON d.ts_code = sb.ts_code
                WHERE d.trade_date = ?
                  AND d.pct_chg >= 9.5
                  AND sb.industry IS NOT NULL AND sb.industry != ''
                GROUP BY sb.industry
                HAVING COUNT(*) >= ?
            ),
            avg_vol AS (
                SELECT ts_code, AVG(vol) AS avg_vol5
                FROM (
                    SELECT ts_code, vol,
                           ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
                    FROM daily WHERE trade_date < ?
                ) t WHERE rn <= 5
                GROUP BY ts_code
            )
            SELECT d.ts_code,
                   COALESCE(sb.name, d.ts_code) AS name,
                   sb.industry,
                   d.pct_chg,
                   d.vol,
                   d.amount,
                   ih.limit_count,
                   av.avg_vol5
            FROM daily d
            JOIN stock_basic sb ON d.ts_code = sb.ts_code
            JOIN industry_heat ih ON sb.industry = ih.industry
            LEFT JOIN avg_vol av ON d.ts_code = av.ts_code
            WHERE d.trade_date = ?
              AND d.pct_chg >= ?
        """, [trade_date, _INDUSTRY_LIMIT_MIN, trade_date, trade_date, _PCT_MIN]).fetchall()

        signals = []
        for ts_code, name, industry, pct_chg, vol, amount, limit_count, avg_vol5 in rows:
            vol_ratio = round(vol / avg_vol5, 2) if avg_vol5 and avg_vol5 > 0 else 1.0

            # 评分：行业涨停数越多越热，个股涨幅越高越强
            score = 50.0
            score += min(20.0, (limit_count - _INDUSTRY_LIMIT_MIN) * 5)
            score += min(15.0, (pct_chg - _PCT_MIN) * 2)
            score += min(10.0, (vol_ratio - 1) * 2)
            score = round(max(30.0, min(95.0, score)), 1)

            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=score, pct_chg=pct_chg,
                vol_ratio=vol_ratio,
                triggered=[self.name],
                extra={"industry": industry, "limit_count": limit_count},
            ))
        return sorted(signals, key=lambda s: s.score, reverse=True)
