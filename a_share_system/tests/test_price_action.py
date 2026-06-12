# a_share_system/tests/test_price_action.py
"""
Brooks 价格行为特征库单测（规格 5：合成 K 线验证 H1/H2 计数、摆动点滞后、
铁丝网判定、涨停判定、防未来函数）。
"""
import numpy as np
import pandas as pd
import pytest

from a_share_system.engine import price_action as pa


def _bar(d, o, h, l, c, pct=0.0, vol=1000.0, amount=1e8):
    return {"trade_date": d, "open": o, "high": h, "low": l,
            "close": c, "pct_chg": pct, "vol": vol, "amount": amount}


def _frame(bars):
    return pd.DataFrame(bars)


# ---------- 单棒特征 ----------
def test_body_ratio_and_tails():
    df = _frame([_bar(1, 10, 12, 8, 11)])
    out = pa.add_bar_features(df)
    # body=1, range=4 → 0.25
    assert out["body_ratio"].iloc[0] == pytest.approx(0.25)
    # upper = 12 - 11 = 1 → 0.25 ; lower = 10 - 8 = 2 → 0.5
    assert out["upper_tail"].iloc[0] == pytest.approx(0.25)
    assert out["lower_tail"].iloc[0] == pytest.approx(0.5)


def test_doji_when_high_equals_low():
    df = _frame([_bar(1, 10, 10, 10, 10)])
    out = pa.add_bar_features(df)
    assert out["body_ratio"].iloc[0] == 0.0
    assert bool(out["is_doji"].iloc[0]) is True


def test_trend_bar_threshold():
    # body 0.7 → trend bar at 0.6 threshold
    df = _frame([_bar(1, 10, 10, 0, 7)])  # body=3, range=10 -> 0.3 ... adjust
    df = _frame([_bar(1, 10, 20, 10, 17)])  # body=7 range=10 -> 0.7
    out = pa.add_bar_features(df)
    assert bool(out["is_trend_bar"].iloc[0]) is True
    assert out["bar_dir"].iloc[0] == 1


# ---------- 涨停判定 ----------
def test_limit_up_mainboard_rounding():
    # pre_close 10.00 → limit 11.00, 主板 10%
    raw = _frame([{"ts_code": "600000.SH", "trade_date": 1,
                   "open": 11.0, "high": 11.0, "low": 11.0, "close": 11.0, "pre_close": 10.0}])
    out = pa.add_limit_flags(raw)
    assert bool(out["is_limit_up"].iloc[0]) is True
    assert bool(out["is_limit_board"].iloc[0]) is True  # 一字板


def test_limit_up_chinext_20pct():
    # 创业板 20%：pre_close 10 → 12.00
    raw = _frame([{"ts_code": "300001.SZ", "trade_date": 1,
                   "open": 11.0, "high": 12.0, "low": 11.0, "close": 12.0, "pre_close": 10.0}])
    out = pa.add_limit_flags(raw)
    assert bool(out["is_limit_up"].iloc[0]) is True
    assert bool(out["is_limit_board"].iloc[0]) is False  # 非一字


def test_touched_limit_intraday():
    # 盘中摸到涨停 11.00 但收 10.50 → 炸板
    raw = _frame([{"ts_code": "600000.SH", "trade_date": 1,
                   "open": 10.2, "high": 11.0, "low": 10.1, "close": 10.5, "pre_close": 10.0}])
    out = pa.add_limit_flags(raw)
    assert bool(out["is_limit_up"].iloc[0]) is False
    assert bool(out["touched_limit"].iloc[0]) is True


def test_st_limit_5pct():
    raw = _frame([{"ts_code": "600000.SH", "trade_date": 1,
                   "open": 10.5, "high": 10.5, "low": 10.5, "close": 10.5, "pre_close": 10.0}])
    out = pa.add_limit_flags(raw, is_st=True)
    assert bool(out["is_limit_up"].iloc[0]) is True


# ---------- 摆动点 2 棒滞后（防未来函数核心） ----------
def test_swing_high_confirmed_lags_by_n():
    # 第 3 棒(idx2) high 最高，左右各 2 棒更低 → swing high 标在 idx2，确认在 idx4
    highs = [10, 11, 15, 11, 10, 9, 8]
    bars = [_bar(i + 1, h - 1, h, h - 2, h - 0.5) for i, h in enumerate(highs)]
    df = pa.add_swing_points(_frame(bars))
    assert bool(df["swing_high"].iloc[2]) is True
    # 确认列右移 2：idx4 才为 True，idx2 为 False
    assert bool(df["swing_high_confirmed"].iloc[2]) is False
    assert bool(df["swing_high_confirmed"].iloc[4]) is True
    # last_swing_high 在确认日(idx4)之后才出现该价位
    assert df["last_swing_high"].iloc[3] != 15
    assert df["last_swing_high"].iloc[4] == 15


def test_swing_low_confirmed():
    lows = [10, 9, 5, 9, 10, 11, 12]
    bars = [_bar(i + 1, l + 1, l + 2, l, l + 0.5) for i, l in enumerate(lows)]
    df = pa.add_swing_points(_frame(bars))
    assert bool(df["swing_low"].iloc[2]) is True
    assert bool(df["swing_low_confirmed"].iloc[4]) is True
    assert df["last_swing_low"].iloc[4] == 5


# ---------- 铁丝网判定 ----------
def test_barbed_wire_detection():
    # 5 根高度重叠的小实体 doji → barbed wire
    bars = []
    for i in range(6):
        # 全部在 [10, 10.4] 重叠区间，小实体
        bars.append(_bar(i + 1, 10.1, 10.4, 10.0, 10.15))
    df = pa.add_bar_features(_frame(bars))
    df = pa.add_context_features(df)
    # 末棒：近 5 棒 ≥3 doji 且 overlap ≥0.6
    assert bool(df["is_barbed_wire"].iloc[-1]) is True


def test_not_barbed_wire_when_trending():
    bars = []
    base = 10.0
    for i in range(6):
        o = base + i
        bars.append(_bar(i + 1, o, o + 2, o - 0.1, o + 1.8))  # 强阳趋势棒
    df = pa.add_bar_features(_frame(bars))
    df = pa.add_context_features(df)
    assert bool(df["is_barbed_wire"].iloc[-1]) is False


# ---------- consec_trend_bars ----------
def test_consec_trend_bars_signed():
    bars = [
        _bar(1, 10, 12, 9.9, 11.8),   # 阳趋势棒
        _bar(2, 11.8, 14, 11.7, 13.8),  # 阳趋势棒
        _bar(3, 13.8, 16, 13.7, 15.8),  # 阳趋势棒 → +3
        _bar(4, 15.8, 16, 14, 14.2),    # 阴趋势棒 → -1
    ]
    df = pa.add_bar_features(_frame(bars))
    df = pa.add_context_features(df)
    assert df["consec_trend_bars"].iloc[2] == 3
    assert df["consec_trend_bars"].iloc[3] == -1


# ---------- H1/H2 计数 ----------
def _uptrend_then_pullback_then_h1h2():
    """
    构造：一段强劲上行 → 浅回调出 H1 → 再下探 → 出 H2。
    用足够长的上行段先把 always_in 推到 LONG。
    """
    bars = []
    price = 10.0
    d = 1
    # 25 根稳步上行的阳趋势棒，确保 EMA20 上升、close>ema、always_in=LONG
    for _ in range(25):
        o = price
        c = price + 0.5
        bars.append(_bar(d, o, c + 0.05, o - 0.05, c, pct=5.0))
        price = c
        d += 1
    # 回调腿1：两根 lower-high（high 递减），价格小幅回落
    top = price
    bars.append(_bar(d, top, top + 0.02, top - 0.4, top - 0.35, pct=-3.0)); d += 1   # high < prev → pullback start
    bars.append(_bar(d, top - 0.35, top - 0.3, top - 0.7, top - 0.6, pct=-2.0)); d += 1  # 继续走低 (lower high)
    # H1：higher-high
    bars.append(_bar(d, top - 0.6, top + 0.1, top - 0.65, top - 0.2, pct=2.0)); d += 1   # high > prev → H1
    # 回调新低：再创回调新低（close 更低）
    bars.append(_bar(d, top - 0.2, top - 0.15, top - 0.9, top - 0.8, pct=-2.0)); d += 1  # lower high + new low close
    # H2：再次 higher-high
    bars.append(_bar(d, top - 0.8, top + 0.05, top - 0.85, top - 0.1, pct=2.0)); d += 1  # high > prev → H2
    return _frame(bars)


def test_h1_h2_counting():
    df = pa.compute_features(_uptrend_then_pullback_then_h1h2())
    # always_in 在上行段末尾应为 LONG
    assert (df["always_in"] == "LONG").any()
    # 应至少出现一次 H1 与一次 H2
    assert bool(df["h1_signal"].any())
    assert bool(df["h2_signal"].any())
    # H2 在 H1 之后
    h1_idx = df.index[df["h1_signal"]].tolist()
    h2_idx = df.index[df["h2_signal"]].tolist()
    assert h1_idx and h2_idx
    assert max(h2_idx) > min(h1_idx)


def test_no_h_signals_when_not_long():
    # 单边下行 → always_in 不为 LONG → 无 H2
    bars = []
    price = 30.0
    for d in range(1, 30):
        o = price
        c = price - 0.5
        bars.append(_bar(d, o + 0.05, o + 0.05, c - 0.05, c, pct=-5.0))
        price = c
    df = pa.compute_features(_frame(bars))
    assert (df["always_in"] != "LONG").all() or not df["h2_signal"].any()


# ---------- 防未来函数自查（规格 4.7） ----------
def test_no_future_function_swing_confirmed():
    """
    截断验证：用前 k 行计算的 swing_*_confirmed，应与全量计算在前 k 行上一致。
    swing_*（含未来信息）不要求一致；confirmed 列必须一致。
    """
    bars = []
    rng = np.random.default_rng(42)
    price = 20.0
    for d in range(1, 60):
        o = price
        c = price + rng.normal(0, 0.5)
        h = max(o, c) + abs(rng.normal(0, 0.3))
        l = min(o, c) - abs(rng.normal(0, 0.3))
        bars.append(_bar(d, o, h, l, c, pct=0.0))
        price = c
    full = pa.add_swing_points(_frame(bars))
    k = 40
    trunc = pa.add_swing_points(_frame(bars[:k]))
    # confirmed 列在前 k-? 行应一致（截断不引入未来）
    pd.testing.assert_series_equal(
        full["swing_high_confirmed"].iloc[:k].reset_index(drop=True),
        trunc["swing_high_confirmed"].reset_index(drop=True),
        check_names=False,
    )
    pd.testing.assert_series_equal(
        full["swing_low_confirmed"].iloc[:k].reset_index(drop=True),
        trunc["swing_low_confirmed"].reset_index(drop=True),
        check_names=False,
    )


def test_no_future_function_h2_prefix_stable():
    """
    H2 信号是逐棒因果状态机：用前 k 行重算，前 k 行的 h2_signal 不变。
    """
    df_full = _uptrend_then_pullback_then_h1h2()
    feat_full = pa.compute_features(df_full)
    k = len(df_full) - 1
    feat_trunc = pa.compute_features(df_full.iloc[:k].copy())
    # compute_features 内含 EMA(adjust=False) 与逐棒状态机，均为因果；前 k 行应一致
    np.testing.assert_array_equal(
        feat_full["h2_signal"].to_numpy()[:k],
        feat_trunc["h2_signal"].to_numpy(),
    )
