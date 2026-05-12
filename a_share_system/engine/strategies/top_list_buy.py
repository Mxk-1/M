# a_share_system/engine/strategies/top_list_buy.py
"""
龙虎榜净买入策略
核心逻辑：当日龙虎榜净买入 > 0，且当日上涨
龙虎榜资金行为是事实，净买入代表大资金真实意图
"""
import duckdb
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


_PCT_MIN    = 0.0    # 当日涨幅 ≥ 0（阳线即可）
_AMOUNT_MIN = 1000   # 成交额 ≥ 1000万（千元单位）


class TopListBuyStrategy(BaseStrategy):
    name = "TOP_LIST"
    display_name = "龙虎榜买入"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        rows = con.execute("""
            WITH top AS (
                SELECT ts_code, SUM(net_amount) AS total_net
                FROM top_list
                WHERE trade_date = ?
                GROUP BY ts_code
                HAVING SUM(net_amount) > 0
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
                   d.pct_chg,
                   d.close,
                   d.amount,
                   top.total_net,
                   av.avg_vol5
            FROM top
            JOIN daily d ON top.ts_code = d.ts_code AND d.trade_date = ?
            LEFT JOIN stock_basic sb ON d.ts_code = sb.ts_code
            LEFT JOIN avg_vol av ON d.ts_code = av.ts_code
            WHERE d.pct_chg >= ?
              AND d.amount >= ?
        """, [trade_date, trade_date, trade_date, _PCT_MIN, _AMOUNT_MIN]).fetchall()

        signals = []
        for ts_code, name, pct_chg, close, amount, total_net, avg_vol5 in rows:
            vol_ratio = round(1.0 if not avg_vol5 or avg_vol5 == 0 else
                              (amount / avg_vol5), 2)  # amount 近似量比

            # 净买入占成交额比例（单位对齐：total_net 万元，amount 千元 → /10）
            net_ratio = (total_net * 10) / amount if amount > 0 else 0

            score = 55.0
            score += min(25.0, net_ratio * 300)
            score += min(10.0, pct_chg * 1.5)
            score += min(10.0, (vol_ratio - 1) * 2)
            score = round(max(30.0, min(98.0, score)), 1)

            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=score, pct_chg=pct_chg,
                vol_ratio=vol_ratio,
                triggered=[self.name],
                extra={
                    "total_net_wan": round(total_net, 0),
                    "net_ratio_pct": round(net_ratio * 100, 1),
                },
            ))
        return sorted(signals, key=lambda s: s.score, reverse=True)
