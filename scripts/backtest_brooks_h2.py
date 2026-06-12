#!/usr/bin/env python
# scripts/backtest_brooks_h2.py
"""
BROOKS_H2 回测验证（规格第 4 节）。

逐条执行回测协议：
  - 撮合：T 日出信号，T+1 开盘价成交；T+1 一字涨停(is_limit_board) → 作废
  - 持有期：固定 5 / 10 日，T+1+N 开盘价卖出
  - 样本：20210104 ~ 最新，全市场非 ST、上市≥60交易日、amount≥1亿
  - 指标：信号数、作废率、胜率、平均盈亏比、期望、超额(等权基准)、最大单笔回撤
  - 假设检验 H-1 / H-3 / H-4 / H-5
  - 敏感性网格：body_ratio {0.5,0.6,0.7} × pullback_depth {0.95,0.97,0.99}
  - 防未来函数：见单测 test_no_future_function_*

性能：每只股票全历史一次性向量化计算特征（pandas），无逐日逐股窗口重切。
读库一律 read_only=True；进程退出释放锁。
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb  # noqa: E402

from a_share_system.config import DB_PATH  # noqa: E402
from a_share_system.engine import price_action as pa  # noqa: E402

START_DATE = 20210104
MIN_LIST_DAYS = 60
AMOUNT_MIN = 100_000.0   # 千元 → 1 亿
SIGNAL_BAR_QUALITY = 0.5
HOLD_PERIODS = (5, 10)


# ---------------- 数据加载 ----------------
def load_universe(con) -> pd.DataFrame:
    """非 ST 全市场基础信息。"""
    return con.execute(
        "SELECT ts_code, COALESCE(name, ts_code) AS name FROM stock_basic "
        "WHERE COALESCE(name,'') NOT LIKE '%ST%'"
    ).df()


def trading_days(con) -> list[int]:
    rows = con.execute(
        f"SELECT DISTINCT trade_date FROM daily WHERE trade_date >= {START_DATE} ORDER BY trade_date"
    ).fetchall()
    return [r[0] for r in rows]


def load_all(con, codes: set[str]):
    """一次性拉全市场 qfq + raw + benchmark（按 ts_code 分组）。"""
    qfq = con.execute(
        f"SELECT ts_code, trade_date, open, high, low, close, pct_chg, vol, amount "
        f"FROM daily_qfq WHERE trade_date >= {START_DATE} ORDER BY ts_code, trade_date"
    ).df()
    raw = con.execute(
        f"SELECT ts_code, trade_date, open, high, low, close, pre_close "
        f"FROM daily WHERE trade_date >= {START_DATE} ORDER BY ts_code, trade_date"
    ).df()
    raw_open = con.execute(
        f"SELECT ts_code, trade_date, open FROM daily WHERE trade_date >= {START_DATE} "
        f"ORDER BY ts_code, trade_date"
    ).df()
    return qfq, raw, raw_open


# ---------------- 信号生成 ----------------
def extract_signals(qfq_g, raw_g, params: dict) -> pd.DataFrame:
    """对单股全历史计算特征，返回通过过滤的 H2 信号日（含风控字段）。"""
    pullback_depth = params.get("pullback_depth", pa.DEFAULT_PARAMS["pullback_depth"])
    feat = pa.compute_features(qfq_g, raw_df=raw_g, is_st=False, params=params)
    n = len(feat)
    if n < MIN_LIST_DAYS:
        return pd.DataFrame()

    rng = (feat["high"] - feat["low"]).replace(0, np.nan)
    bar_quality = ((feat["close"] - feat["low"]) / rng).fillna(0.0)
    # 上市 ≥60 交易日：前 60 行的信号作废（按出现位置序号）
    pos = np.arange(n)

    mask = (
        (feat["always_in"] == "LONG")
        & feat["h2_signal"].astype(bool)
        & (~feat["is_barbed_wire"].astype(bool))
        & (bar_quality >= SIGNAL_BAR_QUALITY)
        & (feat["amount"] >= AMOUNT_MIN)
        & (pos >= MIN_LIST_DAYS)
    )
    # 回调深度：回调期间最低 close ≥ ema20 × depth
    pb_low = feat["pullback_low"].ffill()
    mask &= (pb_low >= feat["ema20"] * pullback_depth)

    if not mask.any():
        return pd.DataFrame()

    sub = feat[mask].copy()
    sub["bar_quality"] = bar_quality[mask].values
    sub["pb_low"] = pb_low[mask].values
    return sub[["ts_code", "trade_date", "close", "consec_trend_bars",
                "bar_quality", "pb_low", "ema20", "atr14"]]


# ---------------- 撮合与持有 ----------------
def simulate(signals: pd.DataFrame, open_by_code: dict, board_by_code: dict,
             bench: dict) -> dict:
    """
    对每条信号撮合：T+1 开盘买入（T+1 一字板作废），T+1+N 开盘卖出。
    返回 per-period 指标 dict 与逐笔明细。
    open_by_code[ts_code] = (dates_array, opens_array)；board_by_code 同结构含 is_limit_board。
    bench = {trade_date: 等权全市场 N 日后基准收益}（按持有期）—— 实际用逐日基准列表。
    """
    results = {N: [] for N in HOLD_PERIODS}
    voided = 0
    total = 0

    for row in signals.itertuples(index=False):
        ts = row.ts_code
        dates, opens = open_by_code[ts]
        boards = board_by_code[ts]
        idx = np.searchsorted(dates, row.trade_date)
        if idx >= len(dates) or dates[idx] != row.trade_date:
            continue
        # T+1
        e_idx = idx + 1
        if e_idx >= len(dates):
            continue
        total += 1
        # 一字板作废
        if boards[e_idx]:
            voided += 1
            continue
        entry = opens[e_idx]
        if not (entry > 0):
            continue
        for N in HOLD_PERIODS:
            x_idx = e_idx + N
            if x_idx >= len(dates):
                continue
            exit_p = opens[x_idx]
            if not (exit_p > 0):
                continue
            ret = exit_p / entry - 1.0
            # 基准：同区间等权全市场（用 benchmark 序列对齐 entry→exit 交易日）
            b_entry = dates[e_idx]
            b_exit = dates[x_idx]
            bench_ret = bench.get((b_entry, b_exit))
            results[N].append((ret, bench_ret))

    return {"results": results, "voided": voided, "total": total}


def benchmark_returns(qfq: pd.DataFrame, open_by_code, all_dates) -> dict:
    """
    等权全市场基准：以每个交易日为 entry、其后 N 交易日为 exit，
    取全市场用开盘价计算的平均收益。key=(entry_date, exit_date)。
    """
    # 用 raw open（与撮合一致）按日期 pivot 计算每股开盘价
    # 这里直接用 open_by_code 重建逐日全市场开盘收益的平均
    date_to_pos = {d: i for i, d in enumerate(all_dates)}
    # 收集 (entry_date, exit_date) → list of stock returns
    acc = defaultdict(lambda: [0.0, 0])
    for ts, (dates, opens) in open_by_code.items():
        pos = np.searchsorted(all_dates, dates)
        for N in HOLD_PERIODS:
            for j in range(len(dates) - 1):
                e_idx = j + 1
                x_idx = e_idx + N
                if x_idx >= len(dates):
                    break
                e_o, x_o = opens[e_idx], opens[x_idx]
                if e_o > 0 and x_o > 0:
                    key = (dates[e_idx], dates[x_idx])
                    a = acc[key]
                    a[0] += x_o / e_o - 1.0
                    a[1] += 1
    return {k: (v[0] / v[1]) for k, v in acc.items() if v[1] > 0}


# ---------------- 指标 ----------------
def metrics(pairs: list[tuple]) -> dict:
    """pairs = [(ret, bench_ret), ...]。"""
    if not pairs:
        return {}
    rets = np.array([p[0] for p in pairs], dtype=float)
    bench = np.array([p[1] if p[1] is not None else np.nan for p in pairs], dtype=float)
    wins = rets[rets > 0]
    losses = rets[rets <= 0]
    win_rate = len(wins) / len(rets)
    avg_win = wins.mean() if len(wins) else 0.0
    avg_loss = losses.mean() if len(losses) else 0.0
    payoff = (avg_win / abs(avg_loss)) if avg_loss != 0 else float("inf")
    expectancy = rets.mean()
    excess = np.nanmean(rets - bench) if not np.all(np.isnan(bench)) else float("nan")
    max_dd = rets.min()
    # t 检验：期望是否显著 > 0
    t_stat = expectancy / (rets.std(ddof=1) / math.sqrt(len(rets))) if len(rets) > 1 and rets.std(ddof=1) > 0 else 0.0
    return {
        "n": len(rets),
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff": payoff,
        "expectancy": expectancy,
        "excess": excess,
        "max_single_dd": max_dd,
        "t_stat": t_stat,
    }


def fmt_metrics(m: dict) -> str:
    if not m:
        return "  (无样本)"
    return (
        f"  n={m['n']}  胜率={m['win_rate']*100:.1f}%  盈亏比={m['payoff']:.2f}  "
        f"期望={m['expectancy']*100:+.2f}%  超额={m['excess']*100:+.2f}%  "
        f"最大单笔回撤={m['max_single_dd']*100:.1f}%  t={m['t_stat']:.2f}"
    )


# ---------------- 主流程 ----------------
def build_indices(qfq, raw, raw_open):
    """构建 per-code 的开盘价 / 一字板索引，以及 qfq/raw 分组。"""
    open_by_code = {}
    board_by_code = {}

    qfq_groups = {c: g.reset_index(drop=True) for c, g in qfq.groupby("ts_code", sort=False)}
    raw_groups = {c: g.reset_index(drop=True) for c, g in raw.groupby("ts_code", sort=False)}

    for ts, g in raw_open.groupby("ts_code", sort=False):
        g = g.sort_values("trade_date")
        open_by_code[ts] = (g["trade_date"].to_numpy(), g["open"].to_numpy(dtype=float))

    # 一字板：需 pre_close → 用 raw 计算
    for ts, g in raw_groups.items():
        flags = pa.add_limit_flags(g, is_st=False)
        board_by_code[ts] = flags["is_limit_board"].to_numpy(dtype=bool)

    return qfq_groups, raw_groups, open_by_code, board_by_code


def run_signals(qfq_groups, raw_groups, params) -> pd.DataFrame:
    out = []
    for ts, g in qfq_groups.items():
        rg = raw_groups.get(ts)
        sig = extract_signals(g, rg, params)
        if len(sig):
            out.append(sig)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--quick", action="store_true", help="仅用部分股票快速自测")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    try:
        uni = load_universe(con)
        codes = set(uni["ts_code"])
        name_map = dict(zip(uni["ts_code"], uni["name"]))
        all_dates = np.array(trading_days(con))
        print(f"样本期 {START_DATE} ~ {all_dates[-1]}，{len(all_dates)} 交易日，非 ST {len(codes)} 只")

        print("加载全市场行情…")
        qfq, raw, raw_open = load_all(con, codes)
        # 仅保留非 ST
        qfq = qfq[qfq["ts_code"].isin(codes)]
        raw = raw[raw["ts_code"].isin(codes)]
        raw_open = raw_open[raw_open["ts_code"].isin(codes)]
        if args.quick:
            keep = sorted(codes)[:300]
            qfq = qfq[qfq["ts_code"].isin(keep)]
            raw = raw[raw["ts_code"].isin(keep)]
            raw_open = raw_open[raw_open["ts_code"].isin(keep)]

        print("构建索引…")
        qfq_groups, raw_groups, open_by_code, board_by_code = build_indices(qfq, raw, raw_open)

        print("计算等权基准…")
        bench = benchmark_returns(qfq, open_by_code, all_dates)

        # ---- 基准策略信号（默认参数）----
        print("生成 BROOKS_H2 信号（默认参数）…")
        base_params = {}
        signals = run_signals(qfq_groups, raw_groups, base_params)
        print(f"  原始 H2 信号 {len(signals)} 条")

        sim = simulate(signals, open_by_code, board_by_code, bench)
        void_rate = sim["voided"] / sim["total"] if sim["total"] else 0.0

        print("\n" + "=" * 70)
        print(f"BROOKS_H2 主结果：进入撮合 {sim['total']} 条，作废(T+1一字板) {sim['voided']} 条，"
              f"作废率 {void_rate*100:.1f}%")
        base_metrics = {}
        for N in HOLD_PERIODS:
            m = metrics(sim["results"][N])
            base_metrics[N] = m
            print(f"\n[持有 {N} 日]")
            print(fmt_metrics(m))

        # ---- H-1 ----
        print("\n" + "=" * 70)
        print("H-1：期望收益 > 0 且 超额 > 0")
        for N in HOLD_PERIODS:
            m = base_metrics[N]
            ok = m and m["expectancy"] > 0 and m["excess"] > 0
            print(f"  {N}日: 期望 {m['expectancy']*100:+.2f}% (t={m['t_stat']:.2f}), "
                  f"超额 {m['excess']*100:+.2f}% → {'成立' if ok else '不成立'}")

        # ---- H-3：消融铁丝网过滤 ----
        print("\n" + "=" * 70)
        print("H-3：去掉铁丝网过滤后假信号率是否上升（消融）")
        abl_signals = run_signals_ablation(qfq_groups, raw_groups, base_params, drop_barbed=True)
        abl_sim = simulate(abl_signals, open_by_code, board_by_code, bench)
        for N in HOLD_PERIODS:
            m_full = base_metrics[N]
            m_abl = metrics(abl_sim["results"][N])
            if m_full and m_abl:
                d_win = (m_abl["win_rate"] - m_full["win_rate"]) * 100
                print(f"  {N}日: 含过滤 胜率 {m_full['win_rate']*100:.1f}% / 期望 {m_full['expectancy']*100:+.2f}%  "
                      f"|  去过滤 胜率 {m_abl['win_rate']*100:.1f}% / 期望 {m_abl['expectancy']*100:+.2f}%  "
                      f"(去过滤胜率 {d_win:+.1f}pp)")

        # ---- H-4：与 BIG_MONEY 共振 ----
        print("\n" + "=" * 70)
        print("H-4：与 BIG_MONEY 同日共振子集 vs 单独")
        # 直接按 BigMoneyStrategy 逻辑在全历史 SQL 内重算（live signals 表只有近几日，
        # 不足以覆盖 5 年样本），口径与 big_money.py 一致：
        #   net_mf*10/amount >= 0.08, pct_chg >= 1.0, close > open, amount >= 5000(万→千元5e4)
        bm = con.execute(
            f"""
            SELECT d.ts_code, d.trade_date
            FROM daily d
            JOIN moneyflow m ON d.ts_code = m.ts_code AND m.trade_date = d.trade_date
            WHERE d.trade_date >= {START_DATE}
              AND d.pct_chg >= 1.0
              AND d.close > d.open
              AND d.amount >= 50000
              AND m.net_mf_amount > 0
              AND (m.net_mf_amount * 10) / d.amount >= 0.08
            """
        ).df()
        if bm.empty:
            print("  moneyflow 无历史，跳过定量，仅给方法说明。")
        else:
            print(f"  全历史 BIG_MONEY 信号 {len(bm)} 条")
            bm_set = set(zip(bm["ts_code"], bm["trade_date"]))
            res_set = pd.Series([(t, d) in bm_set for t, d in
                                 zip(signals["ts_code"], signals["trade_date"])])
            sig_res = signals[res_set.values]
            sig_alone = signals[~res_set.values]
            for label, sg in [("共振子集", sig_res), ("非共振", sig_alone)]:
                ss = simulate(sg, open_by_code, board_by_code, bench)
                for N in HOLD_PERIODS:
                    m = metrics(ss["results"][N])
                    print(f"  [{label} {N}日] {fmt_metrics(m)}")

        # ---- H-5：突破 20 日高点追入 ----
        print("\n" + "=" * 70)
        print("H-5（探索）：突破 20 日新高追入的期望（验证 A 股反转>动量）")
        h5 = breakout_20d(qfq_groups, open_by_code, board_by_code, bench)
        for N in HOLD_PERIODS:
            m = metrics(h5[N])
            print(f"  [突破20高 {N}日] {fmt_metrics(m)}")

        # ---- 敏感性网格 ----
        print("\n" + "=" * 70)
        print("敏感性网格：body_ratio_trend {0.5,0.6,0.7} × pullback_depth {0.95,0.97,0.99}")
        grid = {}
        for br in (0.5, 0.6, 0.7):
            for pd_ in (0.95, 0.97, 0.99):
                p = {"body_ratio_trend": br, "pullback_depth": pd_}
                sg = run_signals(qfq_groups, raw_groups, p)
                ss = simulate(sg, open_by_code, board_by_code, bench)
                m5 = metrics(ss["results"][5])
                m10 = metrics(ss["results"][10])
                grid[(br, pd_)] = (len(sg), m5, m10)
                e5 = m5.get("expectancy", float("nan")) * 100 if m5 else float("nan")
                e10 = m10.get("expectancy", float("nan")) * 100 if m10 else float("nan")
                print(f"  body={br} depth={pd_}: 信号 {len(sg):5d}  "
                      f"期望5d {e5:+.2f}%  期望10d {e10:+.2f}%")

        # 稳健性判定：所有格点 5 日期望同号
        signs = [g[1].get("expectancy", 0) > 0 for g in grid.values() if g[1]]
        robust = all(signs) or not any(signs)
        print(f"\n敏感性结论：5 日期望符号 {'一致（稳健）' if robust else '翻转（不稳健）'}")

    finally:
        con.close()


def run_signals_ablation(qfq_groups, raw_groups, params, drop_barbed=False) -> pd.DataFrame:
    """消融版：去掉铁丝网过滤。"""
    out = []
    for ts, g in qfq_groups.items():
        rg = raw_groups.get(ts)
        feat = pa.compute_features(g, raw_df=rg, is_st=False, params=params)
        n = len(feat)
        if n < MIN_LIST_DAYS:
            continue
        rng = (feat["high"] - feat["low"]).replace(0, np.nan)
        bar_quality = ((feat["close"] - feat["low"]) / rng).fillna(0.0)
        pos = np.arange(n)
        pullback_depth = params.get("pullback_depth", pa.DEFAULT_PARAMS["pullback_depth"])
        pb_low = feat["pullback_low"].ffill()
        mask = (
            (feat["always_in"] == "LONG")
            & feat["h2_signal"].astype(bool)
            & (bar_quality >= SIGNAL_BAR_QUALITY)
            & (feat["amount"] >= AMOUNT_MIN)
            & (pos >= MIN_LIST_DAYS)
            & (pb_low >= feat["ema20"] * pullback_depth)
        )
        if not drop_barbed:
            mask &= ~feat["is_barbed_wire"].astype(bool)
        if mask.any():
            sub = feat[mask].copy()
            out.append(sub[["ts_code", "trade_date", "close"]])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def breakout_20d(qfq_groups, open_by_code, board_by_code, bench) -> dict:
    """H-5：close 突破前 20 日最高 high（不含当日）即追入，T+1 开盘成交。"""
    results = {N: [] for N in HOLD_PERIODS}
    for ts, g in qfq_groups.items():
        g = g.sort_values("trade_date").reset_index(drop=True)
        if len(g) < 80:
            continue
        high = g["high"].to_numpy()
        close = g["close"].to_numpy()
        amount = g["amount"].to_numpy()
        prior_max = pd.Series(high).rolling(20).max().shift(1).to_numpy()
        sig_mask = (close > prior_max) & (amount >= AMOUNT_MIN)
        dates = g["trade_date"].to_numpy()
        o_dates, opens = open_by_code[ts]
        boards = board_by_code[ts]
        for i in np.where(sig_mask)[0]:
            if i < 60:
                continue
            t_date = dates[i]
            idx = np.searchsorted(o_dates, t_date)
            if idx >= len(o_dates) or o_dates[idx] != t_date:
                continue
            e_idx = idx + 1
            if e_idx >= len(o_dates) or boards[e_idx]:
                continue
            entry = opens[e_idx]
            if not (entry > 0):
                continue
            for N in HOLD_PERIODS:
                x_idx = e_idx + N
                if x_idx >= len(o_dates):
                    continue
                exit_p = opens[x_idx]
                if not (exit_p > 0):
                    continue
                ret = exit_p / entry - 1.0
                bench_ret = bench.get((o_dates[e_idx], o_dates[x_idx]))
                results[N].append((ret, bench_ret))
    return results


if __name__ == "__main__":
    main()
