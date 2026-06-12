# a_share_system/engine/strategies/brooks_h2.py
"""
BROOKS_H2 —— Brooks 价格行为 H2 回调二次入场策略（规格 3）。

信号日条件（T 日收盘判定，全部满足）：
  1. always_in == LONG
  2. 当日触发 h2_signal
  3. 信号棒质量：(close-low)/(high-low) ≥ 0.5（收在区间上半）
  4. 回调深度：回调期间最低 close ≥ ema20 × 0.97（浅回调）
  5. 非铁丝网 is_barbed_wire == False
  6. 流动性/基础过滤：非 ST、上市 ≥ 60 个交易日、当日 amount ≥ 1 亿

形态全部基于 daily_qfq（前复权）；涨停判定用原始 daily 的 pre_close。
为保证全市场扫描可向量化，一次性拉取近 N 日窗口，按 ts_code groupby 计算特征。
"""
import duckdb
import numpy as np
import pandas as pd

from a_share_system.engine import price_action as pa
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal

# 形态计算所需的回看窗口（足够 EMA20 收敛 + 摆动结构）
_LOOKBACK_DAYS = 90
_MIN_LIST_DAYS = 60          # 上市 ≥ 60 个交易日
_AMOUNT_MIN = 100_000.0      # 当日 amount ≥ 1 亿（amount 单位千元 → 1e5 千元）
_SIGNAL_BAR_QUALITY = 0.5    # 信号棒质量下限


class BrooksH2Strategy(BaseStrategy):
    name = "BROOKS_H2"
    display_name = "Brooks H2"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int,
             params: dict | None = None) -> list[Signal]:
        params = params or {}
        pullback_depth = params.get("pullback_depth", pa.DEFAULT_PARAMS["pullback_depth"])

        # 候选：当日有数据、非 ST、上市 ≥ 60 交易日、amount ≥ 1 亿
        candidates = con.execute(
            """
            WITH cnt AS (
                SELECT ts_code, COUNT(*) AS ndays
                FROM daily WHERE trade_date <= ?
                GROUP BY ts_code
            )
            SELECT d.ts_code, COALESCE(sb.name, d.ts_code) AS name
            FROM daily d
            JOIN cnt ON cnt.ts_code = d.ts_code
            LEFT JOIN stock_basic sb ON sb.ts_code = d.ts_code
            WHERE d.trade_date = ?
              AND d.amount >= ?
              AND cnt.ndays >= ?
              AND COALESCE(sb.name, '') NOT LIKE '%ST%'
            """,
            [trade_date, trade_date, _AMOUNT_MIN, _MIN_LIST_DAYS],
        ).df()
        if candidates.empty:
            return []

        codes = candidates["ts_code"].tolist()
        name_map = dict(zip(candidates["ts_code"], candidates["name"]))

        # 一次性拉窗口期前复权 + 原始价（用于涨停）
        qfq = con.execute(
            f"""
            SELECT q.ts_code, q.trade_date, q.open, q.high, q.low, q.close,
                   q.pct_chg, q.vol, q.amount
            FROM daily_qfq q
            WHERE q.trade_date <= ?
              AND q.trade_date > (
                  SELECT MIN(t) FROM (
                      SELECT DISTINCT trade_date AS t FROM daily
                      WHERE trade_date <= ? ORDER BY trade_date DESC LIMIT ?
                  )
              ) - 1
              AND q.ts_code IN ({_in_clause(codes)})
            ORDER BY q.ts_code, q.trade_date
            """,
            [trade_date, trade_date, _LOOKBACK_DAYS],
        ).df()
        raw = con.execute(
            f"""
            SELECT ts_code, trade_date, open, high, low, close, pre_close
            FROM daily
            WHERE trade_date <= ?
              AND trade_date > (
                  SELECT MIN(t) FROM (
                      SELECT DISTINCT trade_date AS t FROM daily
                      WHERE trade_date <= ? ORDER BY trade_date DESC LIMIT ?
                  )
              ) - 1
              AND ts_code IN ({_in_clause(codes)})
            ORDER BY ts_code, trade_date
            """,
            [trade_date, trade_date, _LOOKBACK_DAYS],
        ).df()

        raw_by_code = {c: g for c, g in raw.groupby("ts_code", sort=False)}

        signals: list[Signal] = []
        for ts_code, g in qfq.groupby("ts_code", sort=False):
            if len(g) < _MIN_LIST_DAYS:
                continue
            feat = pa.compute_features(
                g, raw_df=raw_by_code.get(ts_code), is_st=False, params=params
            )
            last = feat.iloc[-1]
            if int(last["trade_date"]) != trade_date:
                continue

            sig = _evaluate(last, feat, ts_code, name_map.get(ts_code, ts_code),
                            trade_date, pullback_depth)
            if sig is not None:
                signals.append(sig)

        return sorted(signals, key=lambda s: s.score, reverse=True)


def _evaluate(last, feat, ts_code, name, trade_date, pullback_depth) -> Signal | None:
    # 1. always_in == LONG
    if last["always_in"] != "LONG":
        return None
    # 2. h2_signal
    if not bool(last["h2_signal"]):
        return None
    # 5. 非铁丝网
    if bool(last["is_barbed_wire"]):
        return None

    high, low, close, open_ = last["high"], last["low"], last["close"], last["open"]
    rng = high - low
    # 3. 信号棒质量
    bar_quality = (close - low) / rng if rng > 0 else 0.0
    if bar_quality < _SIGNAL_BAR_QUALITY:
        return None

    # 4. 回调深度：回调期间最低 close ≥ ema20 × depth
    ema20 = last["ema20"]
    pb_low = last["pullback_low"]
    if pd.isna(pb_low):
        # 回退：用近段 h_count 回调最低 close
        recent = feat["pullback_low"].dropna()
        pb_low = recent.iloc[-1] if len(recent) else close
    if not (pb_low >= ema20 * pullback_depth):
        return None

    # ---- 评分（规格 3）----
    consec = abs(float(last["consec_trend_bars"]))
    trend_strength = min(1.0, consec / 5.0)
    score = 60.0 + bar_quality * 20.0 + trend_strength * 20.0
    score = round(min(100.0, score), 1)

    # ---- 风控参数 ----
    atr = float(last["atr14"]) if not pd.isna(last["atr14"]) else 0.0
    stop = round(float(pb_low) - 0.5 * atr, 2)
    entry = round(float(close), 2)   # 参考价（回测以 T+1 开盘撮合）
    risk_r = entry - stop
    target = round(entry + 2.0 * risk_r, 2) if risk_r > 0 else None

    return Signal(
        ts_code=ts_code, name=name,
        trade_date=trade_date, strategy="BROOKS_H2",
        score=score, pct_chg=float(last["pct_chg"]),
        vol_ratio=1.0,
        triggered=["BROOKS_H2"],
        extra={
            "bar_quality": round(float(bar_quality), 3),
            "ema20": round(float(ema20), 3),
            "pullback_low": round(float(pb_low), 3),
            "consec_trend_bars": int(last["consec_trend_bars"]),
            "atr14": round(atr, 3),
            "stop_price": stop,
            "entry_ref": entry,
            "risk_r": round(risk_r, 3),
            "target_2r": target,
        },
    )


def _in_clause(codes: list[str]) -> str:
    return ",".join("'" + c.replace("'", "") + "'" for c in codes)
