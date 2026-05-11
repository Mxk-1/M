# a_share_system/engine/strategies/big_money.py
"""
大单净流入策略
核心逻辑：大单净买入 / 当日成交额 ≥ 阈值，且当日价格上涨（阳线）
大单净买入代表机构/主力的真实动向，散户追涨时大单多为净卖出
"""
import duckdb
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


_BIG_MONEY_RATIO = 0.08    # 大单净流入 / 成交额 ≥ 8%
_PCT_MIN         = 1.0     # 当日涨幅 ≥ 1%
_AMOUNT_MIN      = 5000    # 成交额 ≥ 5000万（千元单位）


class BigMoneyStrategy(BaseStrategy):
    name = "BIG_MONEY"
    display_name = "大单净流入"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        rows = con.execute("""
            SELECT d.ts_code,
                   COALESCE(s.name, d.ts_code) AS name,
                   d.pct_chg,
                   d.open,
                   d.close,
                   d.amount,
                   m.net_mf_amount,
                   m.buy_lg_amount,
                   m.sell_lg_amount,
                   a5.avg_vol5
            FROM daily d
            JOIN moneyflow m ON d.ts_code = m.ts_code AND m.trade_date = d.trade_date
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
              AND d.pct_chg >= ?
              AND d.close > d.open
              AND d.amount >= ?
              AND m.net_mf_amount > 0
        """, [trade_date, trade_date, _PCT_MIN, _AMOUNT_MIN]).fetchall()

        signals = []
        for ts_code, name, pct_chg, open_p, close, amount, net_mf, buy_lg, sell_lg, avg_vol5 in rows:
            # 大单净流入比例：net_mf 单位万元，amount 单位千元 → 统一成万元再做比
            net_ratio = (net_mf * 10) / amount if amount > 0 else 0
            if net_ratio < _BIG_MONEY_RATIO:
                continue

            # 量比
            vol_ratio = 1.0  # amount 代替 vol 估算，这里保守给 1.0

            # 评分：净流入比例越高越好，涨幅配合适当加分
            score = 60.0 + min(25.0, net_ratio * 100) + min(10.0, pct_chg * 2)
            score = round(min(100.0, score), 1)

            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=score, pct_chg=pct_chg,
                vol_ratio=vol_ratio,
                triggered=[self.name],
                extra={
                    "net_mf_wan": round(net_mf, 1),
                    "net_ratio_pct": round(net_ratio * 100, 1),
                    "buy_lg": round(buy_lg, 1),
                    "sell_lg": round(sell_lg, 1),
                },
            ))
        return signals
