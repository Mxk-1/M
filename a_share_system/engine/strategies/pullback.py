# a_share_system/engine/strategies/pullback.py
"""
龙头回踩策略（强势整理）
核心逻辑：
  1. 前 5-15 日内曾有涨停（强势基因）
  2. 随后价格回落但跌幅不超过涨停后高点的 15%（强势整理，非崩盘）
  3. 近 3 日成交量萎缩（缩量洗盘）
  4. 今日放量阳线启动（二次发力信号）

对应模型先生说的：主力建仓→控盘洗盘→拉升，在洗盘末尾、启动初期介入
"""
import duckdb
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


_LIMIT_THRESHOLD = 9.5      # 认定涨停的涨幅下限
_MAX_PULLBACK    = 0.15     # 最多回调 15%
_VOL_SHRINK      = 0.7      # 近 3 日成交量 ≤ 涨停日量的 70%（缩量）
_VOL_EXPAND      = 1.3      # 今日放量 ≥ 近 3 日均量的 1.3 倍
_PCT_TODAY       = 1.5      # 今日涨幅 ≥ 1.5%


class PullbackStrategy(BaseStrategy):
    name = "PULLBACK"
    display_name = "龙头回踩"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        # 取近 20 日有数据的所有股票
        candidates = con.execute("""
            SELECT DISTINCT ts_code FROM daily
            WHERE trade_date <= ?
            GROUP BY ts_code HAVING COUNT(*) >= 20
        """, [trade_date]).fetchall()

        # 批量拉近 20 日数据
        hist_rows = con.execute("""
            SELECT ts_code, trade_date, open, close, high, low, pct_chg, vol
            FROM daily
            WHERE trade_date <= ? AND ts_code IN (
                SELECT ts_code FROM daily
                WHERE trade_date <= ?
                GROUP BY ts_code HAVING COUNT(*) >= 20
            )
            ORDER BY ts_code, trade_date DESC
        """, [trade_date, trade_date]).fetchall()

        from collections import defaultdict
        stock_hist: dict[str, list] = defaultdict(list)
        for row in hist_rows:
            ts_code = row[0]
            if len(stock_hist[ts_code]) < 20:
                stock_hist[ts_code].append(row[1:])  # (date, open, close, high, low, pct_chg, vol)

        # 批量查名称
        name_map = {r[0]: r[1] for r in con.execute(
            "SELECT ts_code, COALESCE(name, ts_code) FROM stock_basic"
        ).fetchall()}

        signals = []
        for ts_code, hist in stock_hist.items():
            # hist[0] 是今日（最新），hist[-1] 是最早
            if len(hist) < 10:
                continue

            today = hist[0]
            today_pct  = today[5]   # pct_chg
            today_close = today[2]
            today_open  = today[1]
            today_vol   = today[6]

            # 今日必须是阳线，涨幅达标
            if today_close <= today_open or today_pct < _PCT_TODAY:
                continue

            # 在过去 5~15 日内找涨停日（不含今日）
            limit_idx = None
            limit_high = 0.0
            limit_vol  = 0.0
            for i in range(1, min(16, len(hist))):
                if hist[i][5] >= _LIMIT_THRESHOLD:
                    limit_idx  = i
                    limit_high = hist[i][3]   # 涨停日的 high
                    limit_vol  = hist[i][6]   # 涨停日的 vol
                    break

            if limit_idx is None:
                continue

            # 涨停后最高价（含涨停当天到昨日的最高价）
            peak = max(h[3] for h in hist[1:limit_idx + 1])   # high

            # 当前价格回调幅度不超过 15%
            if today_close < peak * (1 - _MAX_PULLBACK):
                continue

            # 缩量：涨停后到昨日的平均量 ≤ 涨停日量 * 0.7
            if limit_idx <= 1:
                continue
            recent_vols = [hist[i][6] for i in range(1, limit_idx)]
            avg_recent_vol = sum(recent_vols) / len(recent_vols) if recent_vols else limit_vol
            if avg_recent_vol > limit_vol * _VOL_SHRINK:
                continue

            # 今日放量 ≥ 近 3 日均量 * 1.3
            near3_vols = [hist[i][6] for i in range(1, min(4, len(hist)))]
            avg_near3  = sum(near3_vols) / len(near3_vols) if near3_vols else today_vol
            vol_ratio  = today_vol / avg_near3 if avg_near3 > 0 else 1.0
            if vol_ratio < _VOL_EXPAND:
                continue

            # 涨停日距今天数
            days_since = limit_idx

            # 评分：越近涨停越好，量比越大越好，回调越浅越好
            pullback_pct = (peak - today_close) / peak * 100
            score = 70.0 + min(10.0, (5 - days_since) * 2) + min(10.0, (vol_ratio - 1) * 5) \
                    - min(5.0, pullback_pct * 0.5)
            score = round(max(50.0, min(100.0, score)), 1)

            name = name_map.get(ts_code, ts_code)
            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=score, pct_chg=today_pct,
                vol_ratio=round(vol_ratio, 2),
                triggered=[self.name],
                extra={
                    "days_since_limit": days_since,
                    "peak": round(peak, 2),
                    "pullback_pct": round(pullback_pct, 1),
                },
            ))
        return signals
