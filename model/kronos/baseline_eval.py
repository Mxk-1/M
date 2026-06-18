# -*- coding: utf-8 -*-
"""
baseline_eval.py — Kronos 零样本基线评估

在 test 区间的若干固定"预测日"上，用 predict_batch 并行推理，
对比预测收益率与实际收益率，输出方向命中率 / IC / RankIC。

这是 P0 的 go/no-go 门：
  - 方向命中率 > 52% 且 IC > 0.02  → 有信号，值得继续微调
  - 方向命中率 ~50%              → 模型对 A 股日线基本盲，微调收益存疑

用法:
    conda run -n mxk_env python model/kronos/baseline_eval.py
    conda run -n mxk_env python model/kronos/baseline_eval.py --n-stocks 200 --pred-len 5
"""

import sys
import argparse
import random
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from scipy import stats

_AVAIL = {f.name for f in font_manager.fontManager.ttflist}
for _f in ("PingFang SC", "Heiti TC", "Arial Unicode MS", "STHeiti",
           "Hiragino Sans GB", "Songti SC", "Microsoft YaHei", "SimHei"):
    if _f in _AVAIL:
        plt.rcParams["font.sans-serif"] = [_f]
        break
plt.rcParams["axes.unicode_minus"] = False

KRONOS_ROOT = Path(__file__).resolve().parent        # model/kronos/
M_ROOT      = KRONOS_ROOT.parents[1]                 # M/
sys.path.insert(0, str(KRONOS_ROOT))
from model import Kronos, KronosTokenizer, KronosPredictor  # noqa: E402

DEFAULT_DB  = M_ROOT / "a_share_system" / "market.duckdb"
DEFAULT_OUT = KRONOS_ROOT / "outputs"

TOKENIZER_PRETRAINED = "NeoQuasar/Kronos-Tokenizer-base"
MODEL_PRETRAINED     = "NeoQuasar/Kronos-base"

# 8 个均匀分布在 test 区间的预测日（每个预测日独立推理一批股票）
EVAL_DATES = [
    20250303, 20250429, 20250630,
    20250825, 20251028, 20251223,
    20260227, 20260427,
]


# ─── 数据层 ────────────────────────────────────────────────────────────────────

def get_eligible_stocks(con, pred_date: int, lookback: int) -> list[str]:
    """在 pred_date 之前有足够 lookback 根数据的股票池。"""
    rows = con.execute(
        f"""
        SELECT ts_code FROM (
            SELECT ts_code, count(*) c
            FROM daily_qfq
            WHERE trade_date < {pred_date}
            GROUP BY ts_code
        ) WHERE c >= {lookback}
        """
    ).fetchdf()
    return rows["ts_code"].tolist()


def load_history(con, ts_codes: list[str], pred_date: int, lookback: int) -> dict[str, pd.DataFrame]:
    """批量读取各股 pred_date 之前的最近 lookback 根前复权日线。"""
    codes_sql = ",".join(f"'{c}'" for c in ts_codes)
    df = con.execute(
        f"""
        SELECT ts_code, trade_date, open, high, low, close,
               vol AS volume, amount
        FROM daily_qfq
        WHERE ts_code IN ({codes_sql})
          AND trade_date < {pred_date}
        ORDER BY ts_code, trade_date
        """
    ).fetch_df()
    df["date"] = pd.to_datetime(df["trade_date"].astype(int).astype(str), format="%Y%m%d")

    result = {}
    for code, g in df.groupby("ts_code"):
        g = g.sort_values("date").tail(lookback).reset_index(drop=True)
        if len(g) == lookback:
            result[code] = g
    return result


def load_actual(con, ts_codes: list[str], pred_date: int, pred_len: int) -> pd.DataFrame:
    """读取 pred_date 当天及之后 pred_len 个交易日的实际收盘价（前复权）。"""
    codes_sql = ",".join(f"'{c}'" for c in ts_codes)
    df = con.execute(
        f"""
        SELECT ts_code, trade_date, close
        FROM daily_qfq
        WHERE ts_code IN ({codes_sql})
          AND trade_date >= {pred_date}
        ORDER BY ts_code, trade_date
        """
    ).fetch_df()
    df["date"] = pd.to_datetime(df["trade_date"].astype(int).astype(str), format="%Y%m%d")

    result = {}
    for code, g in df.groupby("ts_code"):
        g = g.sort_values("date").reset_index(drop=True)
        # index 0 = pred_date 当天收盘(作为基准价), index pred_len = 第 pred_len 个未来交易日
        if len(g) >= pred_len + 1:
            result[code] = g.iloc[:pred_len + 1]["close"].values
    return result


def get_future_timestamps(con, pred_date: int, pred_len: int) -> pd.Series:
    """从库里取 pred_date 之后真实的 pred_len 个交易日（而非工作日近似）。"""
    rows = con.execute(
        f"""
        SELECT DISTINCT trade_date
        FROM daily
        WHERE trade_date > {pred_date}
        ORDER BY trade_date
        LIMIT {pred_len}
        """
    ).fetchdf()
    return pd.Series(pd.to_datetime(rows["trade_date"].astype(int).astype(str), format="%Y%m%d"))


# ─── 批量推理 ──────────────────────────────────────────────────────────────────

def run_batch(predictor, hist_map: dict[str, pd.DataFrame],
              y_timestamp: pd.Series, pred_len: int,
              batch_size: int, sample_count: int) -> dict[str, pd.DataFrame]:
    """分批调用 predict_batch，返回 {ts_code: pred_df}。"""
    codes  = list(hist_map.keys())
    result = {}

    for start in range(0, len(codes), batch_size):
        chunk = codes[start: start + batch_size]
        df_list  = [hist_map[c][["open","high","low","close","volume","amount"]] for c in chunk]
        xt_list  = [hist_map[c]["date"].reset_index(drop=True) for c in chunk]
        yt_list  = [y_timestamp] * len(chunk)

        preds = predictor.predict_batch(
            df_list=df_list,
            x_timestamp_list=xt_list,
            y_timestamp_list=yt_list,
            pred_len=pred_len,
            T=1.0, top_p=0.9,
            sample_count=sample_count,
            verbose=False,
        )
        for code, pred_df in zip(chunk, preds):
            result[code] = pred_df

    return result


# ─── 评估计算 ──────────────────────────────────────────────────────────────────

def compute_metrics(pred_map: dict[str, pd.DataFrame],
                    actual_map: dict[str, np.ndarray],
                    pred_len: int) -> list[dict]:
    """
    对每个预测点计算预测收益率与实际收益率，返回 record 列表。
    基准价 = pred_date 当天实际收盘（actual_map 中 index 0）。
    实际 N 日收益 = actual[pred_len] / actual[0] - 1
    预测 N 日收益 = pred_close[-1] / pred_close[0] - 1（pred_close[0]≈pred_date预测开盘）
    更稳健的对齐：用预测第 pred_len 日 close vs 实际基准价
    """
    records = []
    common = set(pred_map.keys()) & set(actual_map.keys())
    for code in common:
        pred_df = pred_map[code]
        actual  = actual_map[code]   # len = pred_len + 1

        base_actual = actual[0]          # pred_date 当天实际收盘
        end_actual  = actual[pred_len]   # pred_len 个交易日后实际收盘
        actual_ret  = end_actual / base_actual - 1

        pred_close   = pred_df["close"].values   # shape (pred_len,)
        base_pred    = pred_close[0]
        end_pred     = pred_close[-1]
        pred_ret     = end_pred / base_pred - 1

        records.append({
            "ts_code":    code,
            "pred_ret":   float(pred_ret),
            "actual_ret": float(actual_ret),
            "direction_correct": int(np.sign(pred_ret) == np.sign(actual_ret)),
        })
    return records


# ─── 报告输出 ──────────────────────────────────────────────────────────────────

def print_summary(all_records: list[dict], pred_len: int, out_dir: Path):
    df = pd.DataFrame(all_records)
    if df.empty:
        print("⚠️  无有效评估样本")
        return

    n     = len(df)
    hit   = df["direction_correct"].mean()
    ic    = df["pred_ret"].corr(df["actual_ret"])
    rank_ic = df["pred_ret"].rank().corr(df["actual_ret"].rank())

    # 方向命中率的 95% 置信区间（二项检验）
    se    = np.sqrt(hit * (1 - hit) / n)
    ci_lo = hit - 1.96 * se
    ci_hi = hit + 1.96 * se

    # 单样本 t 检验：方向命中率是否显著 > 0.5
    _, p_hit = stats.ttest_1samp(df["direction_correct"], 0.5)
    # IC 是否显著 > 0
    _, p_ic  = stats.pearsonr(df["pred_ret"], df["actual_ret"])

    print("\n" + "=" * 55)
    print(f"  Kronos 零样本基线评估  (pred_len={pred_len}日)")
    print("=" * 55)
    print(f"  样本数         : {n}")
    print(f"  方向命中率     : {hit:.4f}  [{ci_lo:.4f}, {ci_hi:.4f}]  (p={p_hit:.4f})")
    print(f"  IC (Pearson)   : {ic:.4f}  (p={p_ic:.4f})")
    print(f"  RankIC         : {rank_ic:.4f}")
    print("-" * 55)

    verdict = []
    if hit > 0.52 and p_hit < 0.05:
        verdict.append("✅ 方向命中率显著 > 50%")
    else:
        verdict.append("❌ 方向命中率不显著")
    if ic > 0.02 and p_ic < 0.05:
        verdict.append("✅ IC 显著 > 0")
    else:
        verdict.append("❌ IC 不显著")

    print("  判断:")
    for v in verdict:
        print(f"    {v}")

    if all("✅" in v for v in verdict):
        print("\n  → GO：有预测信号，建议进行 P1 管线验证")
    elif any("✅" in v for v in verdict):
        print("\n  → 弱信号：部分指标通过，谨慎推进 P1")
    else:
        print("\n  → NO-GO：零样本对 A 股日线基本无效，微调收益存疑")
    print("=" * 55 + "\n")

    # ── 落盘 ──
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"baseline_eval_pred{pred_len}.csv"
    df.to_csv(csv_path, index=False)
    print(f"📄 明细已保存: {csv_path}")

    # ── 散点图：预测收益率 vs 实际收益率 ──
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    ax = axes[0]
    ax.scatter(df["pred_ret"], df["actual_ret"], alpha=0.3, s=15, color="#1f77b4")
    lim = max(abs(df["pred_ret"].max()), abs(df["actual_ret"].max())) * 1.1
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)
    ax.axhline(0, color="gray", lw=0.8); ax.axvline(0, color="gray", lw=0.8)
    z = np.polyfit(df["pred_ret"], df["actual_ret"], 1)
    xr = np.linspace(-lim, lim, 100)
    ax.plot(xr, np.polyval(z, xr), "r--", lw=1.5, label=f"IC={ic:.3f}")
    ax.set_xlabel("预测收益率"); ax.set_ylabel("实际收益率")
    ax.set_title(f"预测 vs 实际  (N={n})")
    ax.legend()

    ax2 = axes[1]
    # 按预测收益率分十分位，看各组平均实际收益（因子有效性经典图）
    df["pred_decile"] = pd.qcut(df["pred_ret"], 10, labels=False)
    grp = df.groupby("pred_decile")["actual_ret"].mean()
    bars = ax2.bar(range(1, 11), grp.values * 100, color="#2ca02c", alpha=0.8)
    ax2.axhline(0, color="gray", lw=0.8)
    ax2.set_xlabel("预测收益率分位（1=最低，10=最高）")
    ax2.set_ylabel("实际平均收益率 (%)")
    ax2.set_title("因子分层收益（单调性越强越好）")

    plt.suptitle(f"Kronos 零样本基线  pred_len={pred_len}日  样本={n}  方向命中={hit:.3f}  IC={ic:.4f}",
                 fontsize=11)
    plt.tight_layout()
    plot_path = out_dir / f"baseline_eval_pred{pred_len}.png"
    plt.savefig(plot_path, dpi=120)
    plt.close()
    print(f"📊 图已保存: {plot_path}\n")


# ─── 主流程 ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Kronos 零样本基线评估（P0）")
    ap.add_argument("--db",           type=Path, default=DEFAULT_DB)
    ap.add_argument("--out",          type=Path, default=DEFAULT_OUT)
    ap.add_argument("--n-stocks",     type=int,  default=100,  help="每个预测日随机抽几只票")
    ap.add_argument("--pred-len",     type=int,  default=10)
    ap.add_argument("--lookback",     type=int,  default=120)
    ap.add_argument("--batch-size",   type=int,  default=50,   help="predict_batch 每批最多几只")
    ap.add_argument("--sample-count", type=int,  default=3,    help="多路径采样取均值")
    ap.add_argument("--seed",         type=int,  default=42)
    ap.add_argument("--device",       default="cpu")
    ap.add_argument("--tokenizer",    default=TOKENIZER_PRETRAINED)
    ap.add_argument("--model",        default=MODEL_PRETRAINED)
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    print(f"🚀 加载模型  tokenizer={args.tokenizer}  model={args.model}  device={args.device}")
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model     = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(model, tokenizer, device=args.device,
                                max_context=args.lookback)

    con = duckdb.connect(str(args.db), read_only=True)

    all_records = []
    for pred_date in EVAL_DATES:
        print(f"\n📅 预测日: {pred_date}")

        # 1. 选票
        eligible = get_eligible_stocks(con, pred_date, args.lookback)
        if len(eligible) < 10:
            print(f"  ⚠️  够历史的票不足 10 只，跳过")
            continue
        sampled = random.sample(eligible, min(args.n_stocks, len(eligible)))
        print(f"  抽样: {len(sampled)} 只 / {len(eligible)} 只可用")

        # 2. 读历史
        hist_map = load_history(con, sampled, pred_date, args.lookback)
        valid    = list(hist_map.keys())
        print(f"  历史读取: {len(valid)} 只有效（lookback={args.lookback}）")
        if not valid:
            continue

        # 3. 未来时间戳（真实交易日）
        y_timestamp = get_future_timestamps(con, pred_date, args.pred_len)
        if len(y_timestamp) < args.pred_len:
            print(f"  ⚠️  未来交易日不足 {args.pred_len} 个（库里数据到头了），跳过")
            continue

        # 4. 批量推理
        print(f"  🔮 推理 {len(valid)} 只票（batch_size={args.batch_size}，sample_count={args.sample_count}）...")
        pred_map = run_batch(predictor, hist_map, y_timestamp,
                             args.pred_len, args.batch_size, args.sample_count)

        # 5. 读实际值
        actual_map = load_actual(con, valid, pred_date, args.pred_len)

        # 6. 计算指标
        records = compute_metrics(pred_map, actual_map, args.pred_len)
        print(f"  有效对比: {len(records)} 只")
        all_records.extend(records)

    con.close()

    # 汇总报告
    print_summary(all_records, args.pred_len, args.out)


if __name__ == "__main__":
    main()
