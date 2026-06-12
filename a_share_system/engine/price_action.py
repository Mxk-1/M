# a_share_system/engine/price_action.py
"""
Brooks 价格行为特征库（Phase 1）

纯函数、无状态。输入统一为单只股票按 trade_date 升序的 DataFrame，
列至少包含：trade_date, open, high, low, close, pct_chg, vol, amount。
形态计算一律基于前复权价（daily_qfq），调用方负责传入 qfq 价格。

涨停判定（is_limit_up / is_limit_board / touched_limit）需要原始（未复权）
的 pre_close 与 close 才能按交易所规则四舍五入到分。is_limit_up 是 close
与 limit_price 的等值关系，复权对二者同比例缩放、布尔结果不变；但 limit_price
的“四舍五入到分”只在原始价空间成立，故这三列由 add_limit_flags() 在原始价
DataFrame 上计算，再 merge 进 qfq 特征帧。

防未来函数（规格 4.7）：
- 摆动点采用分形 N=2，确认有 2 棒滞后，标注在分形棒上，但只有
  swing_*_confirmed 列（右移 2 行）可在回测/实盘中使用。
- EMA、滚动统计只用当日及之前数据（pandas 默认行为）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------- 参数（阈值集中，便于敏感性网格扫描） ----------
DEFAULT_PARAMS: dict[str, float] = {
    "body_ratio_trend": 0.6,    # is_trend_bar 阈值
    "body_ratio_doji": 0.25,    # is_doji 阈值
    "ema_span": 20,             # EMA20
    "ema_slope_window": 5,      # EMA 斜率回看窗口
    "swing_n": 2,               # 分形摆动点左右各 N 棒
    "overlap_window": 5,        # overlap_ratio / barbed_wire 窗口
    "barbed_doji_min": 3,       # 铁丝网：窗口内 doji 棒数下限
    "barbed_overlap_min": 0.6,  # 铁丝网：overlap_ratio 下限
    "pullback_depth": 0.97,     # H2 回调深度：回调最低 close ≥ ema20 × 此值
}


# ---------- 涨停价规则 ----------
def limit_pct(ts_code: str) -> float:
    """该股票涨跌停百分比（小数）。ST 由调用方另行处理（±5%）。"""
    # 创业板 300/301、科创板 688/689 → 20%
    if ts_code[:3] in ("300", "301", "688", "689"):
        return 0.20
    # 北交所 → 30%
    if ts_code.endswith(".BJ") or ts_code.startswith("920"):
        return 0.30
    return 0.10


def limit_up_price(pre_close: float, pct: float) -> float:
    """按交易所规则四舍五入到分。"""
    return round(pre_close * (1 + pct) + 1e-9, 2)


# ---------- 单棒特征 ----------
def add_bar_features(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    """规格 2.1：逐行单棒特征。要求 df 已按 trade_date 升序。"""
    p = {**DEFAULT_PARAMS, **(params or {})}
    out = df.copy()

    rng = (out["high"] - out["low"]).replace(0, np.nan)
    body = (out["close"] - out["open"]).abs()
    out["body_ratio"] = (body / rng).fillna(0.0)

    upper = out["high"] - out[["open", "close"]].max(axis=1)
    lower = out[["open", "close"]].min(axis=1) - out["low"]
    out["upper_tail"] = (upper / rng).fillna(0.0)
    out["lower_tail"] = (lower / rng).fillna(0.0)

    out["is_trend_bar"] = out["body_ratio"] >= p["body_ratio_trend"]
    out["is_doji"] = out["body_ratio"] <= p["body_ratio_doji"]

    prev_close = out["close"].shift(1)
    out["gap_pct"] = (out["open"] - prev_close) / prev_close

    # 趋势棒方向（+1 阳 / -1 阴 / 0 非趋势棒）
    direction = np.where(out["close"] > out["open"], 1, np.where(out["close"] < out["open"], -1, 0))
    out["bar_dir"] = np.where(out["is_trend_bar"], direction, 0).astype(int)

    return out


def add_limit_flags(raw_df: pd.DataFrame, is_st: bool = False) -> pd.DataFrame:
    """
    规格 2.1 涨停三列，基于原始（未复权）价格。
    raw_df 需含 ts_code, open, high, low, close, pre_close。
    返回仅含 [trade_date, is_limit_up, is_limit_board, touched_limit] 便于 merge。
    """
    out = raw_df.copy()
    ts_code = out["ts_code"].iloc[0] if len(out) else ""
    pct = 0.05 if is_st else limit_pct(ts_code)

    lp = (out["pre_close"] * (1 + pct) + 1e-9).round(2)
    eps = 1e-4
    is_limit_up = (out["close"] - lp).abs() <= eps
    out["is_limit_up"] = is_limit_up.fillna(False)
    out["is_limit_board"] = (
        out["is_limit_up"]
        & (out["open"] == out["high"])
        & (out["high"] == out["low"])
        & (out["low"] == out["close"])
    )
    out["touched_limit"] = ((out["high"] - lp).abs() <= eps) & (out["close"] < lp - eps)
    out["touched_limit"] = out["touched_limit"].fillna(False)
    cols = ["trade_date", "is_limit_up", "is_limit_board", "touched_limit"]
    return out[cols]


# ---------- 滚动上下文特征 ----------
def add_context_features(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    """规格 2.2：EMA20、斜率、连续趋势棒、重叠度、铁丝网。"""
    p = {**DEFAULT_PARAMS, **(params or {})}
    out = df.copy()

    out["ema20"] = out["close"].ewm(span=int(p["ema_span"]), adjust=False).mean()
    sw = int(p["ema_slope_window"])
    ema_prev = out["ema20"].shift(sw)
    out["ema20_slope"] = ((out["ema20"] - ema_prev) / sw / out["ema20"]).fillna(0.0)

    # 连续同向趋势棒计数（带符号）
    out["consec_trend_bars"] = _consec_trend_bars(out["bar_dir"].to_numpy())

    # 近 N 棒两两区间重叠度均值
    out["overlap_ratio"] = _overlap_ratio(
        out["high"].to_numpy(), out["low"].to_numpy(), int(p["overlap_window"])
    )

    win = int(p["overlap_window"])
    doji_cnt = out["is_doji"].rolling(win, min_periods=win).sum()
    out["is_barbed_wire"] = (doji_cnt >= p["barbed_doji_min"]) & (
        out["overlap_ratio"] >= p["barbed_overlap_min"]
    )
    out["is_barbed_wire"] = out["is_barbed_wire"].fillna(False)

    return out


def _consec_trend_bars(bar_dir: np.ndarray) -> np.ndarray:
    """同向趋势棒连续计数，带符号。非趋势棒(0)中断计数。"""
    n = len(bar_dir)
    res = np.zeros(n, dtype=int)
    run = 0
    prev = 0
    for i in range(n):
        d = bar_dir[i]
        if d == 0:
            run = 0
        elif d == prev:
            run += d
        else:
            run = d
        res[i] = run
        prev = d
    return res


def _overlap_ratio(high: np.ndarray, low: np.ndarray, win: int) -> np.ndarray:
    """近 win 棒两两区间重叠度均值。重叠度 = 重叠区间 / 并集区间。"""
    n = len(high)
    res = np.full(n, np.nan)
    for i in range(win - 1, n):
        hs = high[i - win + 1 : i + 1]
        ls = low[i - win + 1 : i + 1]
        pairs = 0
        acc = 0.0
        for a in range(win):
            for b in range(a + 1, win):
                lo_max = max(ls[a], ls[b])
                hi_min = min(hs[a], hs[b])
                inter = max(0.0, hi_min - lo_max)
                union = max(hs[a], hs[b]) - min(ls[a], ls[b])
                acc += (inter / union) if union > 0 else 0.0
                pairs += 1
        res[i] = acc / pairs if pairs else 0.0
    return res


# ---------- 摆动点（分形 N=2，2 棒滞后） ----------
def add_swing_points(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    """
    规格 2.3：分形摆动高/低点。
    swing_high / swing_low      —— 标注在分形棒上（含未来信息，仅供画图/调试）
    swing_high_confirmed / ...  —— 右移 N 行，确认日及之后才可用（防未来函数）
    """
    p = {**DEFAULT_PARAMS, **(params or {})}
    n = int(p["swing_n"])
    out = df.copy()
    high = out["high"].to_numpy()
    low = out["low"].to_numpy()
    m = len(out)

    sh = np.zeros(m, dtype=bool)
    sl = np.zeros(m, dtype=bool)
    for i in range(n, m - n):
        window_h = high[i - n : i + n + 1]
        window_l = low[i - n : i + n + 1]
        if high[i] == window_h.max() and (window_h == high[i]).sum() == 1:
            sh[i] = True
        if low[i] == window_l.min() and (window_l == low[i]).sum() == 1:
            sl[i] = True

    out["swing_high"] = sh
    out["swing_low"] = sl
    # 确认列：分形棒在 i，确认日在 i+n
    out["swing_high_confirmed"] = pd.Series(sh, index=out.index).shift(n).fillna(False).astype(bool)
    out["swing_low_confirmed"] = pd.Series(sl, index=out.index).shift(n).fillna(False).astype(bool)
    # 最近一次已确认摆动低点的价位（用于 always_in 判断）
    swing_low_price = np.where(sl, low, np.nan)
    out["last_swing_low"] = (
        pd.Series(swing_low_price, index=out.index).shift(n).ffill()
    )
    swing_high_price = np.where(sh, high, np.nan)
    out["last_swing_high"] = (
        pd.Series(swing_high_price, index=out.index).shift(n).ffill()
    )
    return out


# ---------- Always-In 状态机 ----------
def add_always_in(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    """
    规格 2.3：always_in ∈ {LONG, SHORT, NEUTRAL}，带 2 日粘性。
    依赖 ema20 / ema20_slope / is_barbed_wire / last_swing_low/high / close。
    """
    out = df.copy()
    close = out["close"].to_numpy()
    ema = out["ema20"].to_numpy()
    slope = out["ema20_slope"].to_numpy()
    barbed = out["is_barbed_wire"].to_numpy()
    last_sl = out["last_swing_low"].to_numpy()
    last_sh = out["last_swing_high"].to_numpy()

    # close 与 ema20 缠绕：近 5 日穿越 ≥3 次
    above = close > ema
    cross = np.zeros(len(out), dtype=bool)
    chg = np.r_[False, above[1:] != above[:-1]]
    cross_cnt = pd.Series(chg.astype(int)).rolling(5, min_periods=1).sum().to_numpy()
    tangled = cross_cnt >= 3

    n = len(out)
    state = np.array(["NEUTRAL"] * n, dtype=object)
    cur = "NEUTRAL"
    long_streak = 0
    short_streak = 0
    for i in range(n):
        # 候选方向
        long_ok = (
            close[i] > ema[i]
            and slope[i] > 0
            and (np.isnan(last_sl[i]) or close[i] > last_sl[i])
        )
        short_ok = (
            close[i] < ema[i]
            and slope[i] < 0
            and (np.isnan(last_sh[i]) or close[i] < last_sh[i])
        )
        neutral_ok = bool(barbed[i]) or bool(tangled[i])

        if neutral_ok:
            cur = "NEUTRAL"
            long_streak = short_streak = 0
        elif long_ok:
            long_streak += 1
            short_streak = 0
            if long_streak >= 2 or cur == "LONG":
                cur = "LONG"
        elif short_ok:
            short_streak += 1
            long_streak = 0
            if short_streak >= 2 or cur == "SHORT":
                cur = "SHORT"
        else:
            long_streak = short_streak = 0
            # 条件不满足时保持粘性（不翻转）
        state[i] = cur

    out["always_in"] = state
    return out


# ---------- H/L 计数（H 系：always_in == LONG 时） ----------
def add_h_count(df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
    """
    规格 2.4：仅在 always_in == LONG 时计数。
    标记 h1_signal / h2_signal、leg_count、pullback_low（回调期间最低 close）。

    状态机（逐棒，单股，O(n)）：
      - 进入 LONG 且尚无回调 → 跟踪趋势高点
      - 出现 high < 前棒 high → 进入 pullback，leg_count=0，记录 pullback_low
      - pullback 中 high > 前棒 high 首次 → H1（leg_count=1）
      - H1 后再创回调新低（close 更低且未跌破结构）→ 回到下行腿
      - 第二次 high > 前棒 high → H2（leg_count=2）
      - close 创趋势新高 或 always_in 非 LONG → 重置
    """
    out = df.copy()
    high = out["high"].to_numpy()
    close = out["close"].to_numpy()
    ai = out["always_in"].to_numpy()
    n = len(out)

    h1 = np.zeros(n, dtype=bool)
    h2 = np.zeros(n, dtype=bool)
    leg = np.zeros(n, dtype=int)
    pb_low = np.full(n, np.nan)

    in_pullback = False
    leg_count = 0
    trend_high = -np.inf      # 当前 LONG 段的趋势高点
    pullback_low_close = np.inf
    awaiting_new_low = False  # H1 之后等待新低再确认 H2 的下一腿

    for i in range(n):
        if ai[i] != "LONG":
            in_pullback = False
            leg_count = 0
            trend_high = -np.inf
            pullback_low_close = np.inf
            awaiting_new_low = False
            leg[i] = 0
            continue

        if trend_high == -np.inf:
            trend_high = high[i]

        prev_high = high[i - 1] if i > 0 else high[i]

        if not in_pullback:
            # 趋势中：close 创新高则刷新趋势高点
            if high[i] > trend_high:
                trend_high = high[i]
            # 回调开始
            if high[i] < prev_high:
                in_pullback = True
                leg_count = 0
                pullback_low_close = close[i]
                awaiting_new_low = False
        else:
            # 回调中
            pullback_low_close = min(pullback_low_close, close[i])
            made_higher_high = high[i] > prev_high

            if made_higher_high:
                if leg_count == 0:
                    leg_count = 1
                    h1[i] = True
                    awaiting_new_low = True   # H1 已出，需新低后才数 H2
                elif leg_count == 1 and not awaiting_new_low:
                    leg_count = 2
                    h2[i] = True
            else:
                # 创回调新低 → 进入下一条下行腿，允许下次 higher-high 计为 H2
                if leg_count == 1 and close[i] <= pullback_low_close:
                    awaiting_new_low = False

            # 回调终结：close 创趋势新高
            if close[i] > trend_high:
                in_pullback = False
                leg_count = 0
                trend_high = high[i]
                awaiting_new_low = False

        leg[i] = leg_count
        pb_low[i] = pullback_low_close if in_pullback else np.nan

    out["h1_signal"] = h1
    out["h2_signal"] = h2
    out["leg_count"] = leg
    out["pullback_low"] = pb_low
    return out


# ---------- ATR ----------
def add_atr(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    out = df.copy()
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr14"] = tr.rolling(window, min_periods=1).mean()
    return out


# ---------- 组合管线 ----------
def compute_features(
    qfq_df: pd.DataFrame,
    raw_df: pd.DataFrame | None = None,
    is_st: bool = False,
    params: dict | None = None,
) -> pd.DataFrame:
    """
    全特征管线。qfq_df 为前复权单股升序帧；raw_df 为同股原始价帧（含 pre_close），
    用于涨停判定。raw_df 缺省时涨停三列填 False。
    """
    df = qfq_df.sort_values("trade_date").reset_index(drop=True)
    df = add_bar_features(df, params)
    df = add_context_features(df, params)
    df = add_swing_points(df, params)
    df = add_always_in(df, params)
    df = add_h_count(df, params)
    df = add_atr(df)

    if raw_df is not None and len(raw_df):
        flags = add_limit_flags(raw_df.sort_values("trade_date").reset_index(drop=True), is_st=is_st)
        df = df.merge(flags, on="trade_date", how="left")
        for c in ("is_limit_up", "is_limit_board", "touched_limit"):
            df[c] = df[c].fillna(False).astype(bool)
    else:
        df["is_limit_up"] = False
        df["is_limit_board"] = False
        df["touched_limit"] = False

    return df
