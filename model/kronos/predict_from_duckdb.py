# -*- coding: utf-8 -*-
"""
predict_from_duckdb.py

用 a_share_system 的 DuckDB(前复权视图 daily_qfq)驱动 Kronos 预测未来日线。

复权口径(重要):
    模型输入与预测一律用【前复权 daily_qfq】。
    - 不复权(daily)会把除权除息跳空当成暴涨暴跌,毒化 K 线 token —— 禁止。
    - qfq 与 hfq 仅差一个全局常数倍率,经 Kronos 的窗口内归一化后预测形状一致;
      选 qfq 是因为它锚定最新价,输出价 = 当前真实盘面价同量纲,直接可读。
    - 注意:将来若要回测 Kronos 信号的【盈亏】,算收益那一步再切 daily_hfq。

数据库为单写者:本脚本以 read_only=True 连接,不与 update/回填等写进程抢锁。

用法:
    conda run -n mxk_env python model/kronos/predict_from_duckdb.py --code 600580
    conda run -n mxk_env python model/kronos/predict_from_duckdb.py --code 300207 --pred-len 20 --device cpu

依赖(除 mxk_env 已有的 duckdb/pandas/matplotlib 外,还需):
    pip install torch einops safetensors huggingface_hub
"""

import os
import sys
import argparse
from pathlib import Path

import duckdb
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# 选一个系统里可用的中文字体,避免图中中文变方框
_AVAIL = {f.name for f in font_manager.fontManager.ttflist}
for _f in ("PingFang SC", "Heiti TC", "Arial Unicode MS", "STHeiti", "Hiragino Sans GB",
           "Songti SC", "Microsoft YaHei", "SimHei"):
    if _f in _AVAIL:
        plt.rcParams["font.sans-serif"] = [_f]
        break
plt.rcParams["axes.unicode_minus"] = False

# 让 `from model import ...` 找到 Kronos 包(脚本在 Kronos/examples/ 下)
KRONOS_ROOT = Path(__file__).resolve().parent        # model/kronos/
M_ROOT      = KRONOS_ROOT.parents[1]                 # M/
sys.path.insert(0, str(KRONOS_ROOT))
from model import Kronos, KronosTokenizer, KronosPredictor  # noqa: E402

DEFAULT_DB  = M_ROOT / "a_share_system" / "market.duckdb"
DEFAULT_OUT = KRONOS_ROOT / "outputs"

TOKENIZER_PRETRAINED = "NeoQuasar/Kronos-Tokenizer-base"
MODEL_PRETRAINED = "NeoQuasar/Kronos-base"


def normalize_ts_code(code: str) -> str:
    """把 '600580' / 'sh600580' / '600580.SH' 统一成 tushare 的 ts_code 格式。"""
    code = code.strip().upper()
    if "." in code:
        return code
    # 去掉可能的 SH/SZ/BJ 前缀,留 6 位数字
    digits = "".join(c for c in code if c.isdigit())
    if len(digits) != 6:
        raise ValueError(f"无法识别股票代码: {code}")
    head = digits[0]
    if head in "69":        # 沪市主板 / 科创板(688)/ B股
        suffix = "SH"
    elif head in "0123":    # 深市主板 / 创业板(300)
        suffix = "SZ"
    else:                   # 4/8 北交所
        suffix = "BJ"
    return f"{digits}.{suffix}"


def infer_limit_rate(ts_code: str) -> float:
    """按代码推断涨跌停幅度(主板 10% / 创业板·科创板 20% / 北交所 30%)。

    注意:无法从代码判断 ST(±5%),如标的为 ST 请用 --limit 0.05 覆盖。
    """
    six = ts_code.split(".")[0]
    if six.startswith(("300", "688")):
        return 0.20
    if six.startswith(("4", "8")):
        return 0.30
    return 0.10


def load_qfq(db_path: Path, ts_code: str, lookback: int) -> pd.DataFrame:
    """从 daily_qfq 读取最近 lookback 根前复权日线。"""
    print(f"📥 读取前复权数据 daily_qfq: {ts_code}  (db={db_path})")
    if not db_path.exists():
        sys.exit(f"❌ 找不到数据库: {db_path}")
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(
            """
            SELECT trade_date, open, high, low, close, vol AS volume, amount
            FROM daily_qfq
            WHERE ts_code = ?
            ORDER BY trade_date
            """,
            [ts_code],
        ).fetch_df()
    finally:
        con.close()

    if df.empty:
        sys.exit(f"❌ {ts_code} 在 daily_qfq 中无数据(代码是否正确 / 库是否已更新?)")

    df["date"] = pd.to_datetime(df["trade_date"].astype(int).astype(str), format="%Y%m%d")
    df = df.drop(columns=["trade_date"]).sort_values("date").reset_index(drop=True)

    if len(df) < lookback:
        print(f"⚠️  历史仅 {len(df)} 根 < lookback={lookback},将使用全部可用数据。")
    df = df.tail(lookback).reset_index(drop=True)
    print(f"✅ 已载入 {len(df)} 根  范围 {df['date'].iloc[0].date()} ~ {df['date'].iloc[-1].date()}")
    return df


def build_future_timestamps(last_date: pd.Timestamp, pred_len: int) -> pd.Series:
    """未来交易日时间戳。用工作日近似(不含 A 股节假日),仅供模型时间嵌入用。"""
    future = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=pred_len)
    return pd.Series(future)


def apply_price_limit(pred_df: pd.DataFrame, last_close: float, rate: float) -> pd.DataFrame:
    """逐日按上一日收盘 ±rate 裁剪 OHLC,模拟涨跌停约束(rate<=0 关闭)。"""
    if rate <= 0:
        return pred_df
    print(f"🔒 应用 ±{rate*100:.0f}% 涨跌停裁剪")
    pred_df = pred_df.reset_index(drop=True)
    cols = ["open", "high", "low", "close"]
    pred_df[cols] = pred_df[cols].astype("float64")
    prev = float(last_close)
    for i in range(len(pred_df)):
        up, down = prev * (1 + rate), prev * (1 - rate)
        for c in cols:
            v = pred_df.at[i, c]
            if pd.notna(v):
                pred_df.at[i, c] = float(max(min(v, up), down))
        prev = float(pred_df.at[i, "close"])
    return pred_df


def plot_result(hist: pd.DataFrame, pred: pd.DataFrame, ts_code: str, out_dir: Path,
                hist_tail: int = 120) -> Path:
    h = hist.tail(hist_tail)
    plt.figure(figsize=(12, 6))
    plt.plot(h["date"], h["close"], label="历史(前复权)", color="#1f77b4")
    # 连接历史最后一点和预测第一点
    bridge = pd.concat([hist.tail(1), pred]).reset_index(drop=True)
    plt.plot(bridge["date"], bridge["close"], label="Kronos 预测", color="#d62728", linestyle="--")
    plt.axvline(hist["date"].iloc[-1], color="gray", linestyle=":", alpha=0.6)
    plt.title(f"Kronos 前复权预测 — {ts_code}")
    plt.xlabel("日期")
    plt.ylabel("收盘价(前复权)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"pred_{ts_code.replace('.', '_')}_chart.png"
    plt.savefig(path, dpi=120)
    plt.close()
    print(f"📊 图已保存: {path}")
    return path


def main():
    ap = argparse.ArgumentParser(description="用 DuckDB 前复权数据跑 Kronos 日线预测")
    ap.add_argument("--code", required=True, help="股票代码,如 600580 / 600580.SH / 300207")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"market.duckdb 路径(默认 {DEFAULT_DB})")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="输出目录")
    ap.add_argument("--lookback", type=int, default=400, help="输入历史长度(<=512)")
    ap.add_argument("--pred-len", type=int, default=10, help="预测未来交易日数(日线远端不可靠,建议 ≤20)")
    ap.add_argument("--device", default="cpu", help="cpu / cuda:0 / mps")
    ap.add_argument("--max-context", type=int, default=512)
    ap.add_argument("--T", type=float, default=1.0, help="采样温度")
    ap.add_argument("--top-p", type=float, default=0.9)
    ap.add_argument("--sample-count", type=int, default=1, help=">1 时对多条采样路径取均值,更平滑")
    ap.add_argument("--limit", type=float, default=None,
                    help="涨跌停幅度,如 0.1;默认按代码自动判;0 关闭;ST 请填 0.05")
    ap.add_argument("--tokenizer", default=TOKENIZER_PRETRAINED)
    ap.add_argument("--model", default=MODEL_PRETRAINED)
    args = ap.parse_args()

    ts_code = normalize_ts_code(args.code)
    rate = args.limit if args.limit is not None else infer_limit_rate(ts_code)

    df = load_qfq(args.db, ts_code, args.lookback)

    print(f"🚀 加载 Kronos  tokenizer={args.tokenizer}  model={args.model}  device={args.device}")
    tokenizer = KronosTokenizer.from_pretrained(args.tokenizer)
    model = Kronos.from_pretrained(args.model)
    predictor = KronosPredictor(model, tokenizer, device=args.device, max_context=args.max_context)

    x_df = df[["open", "high", "low", "close", "volume", "amount"]]
    x_timestamp = df["date"]
    y_timestamp = build_future_timestamps(df["date"].iloc[-1], args.pred_len)

    print(f"🔮 预测未来 {args.pred_len} 个交易日 ...")
    pred_df = predictor.predict(
        df=x_df,
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=args.pred_len,
        T=args.T,
        top_p=args.top_p,
        sample_count=args.sample_count,
    )

    pred_df = pred_df.reset_index(drop=True)
    pred_df["date"] = y_timestamp.values
    pred_df = apply_price_limit(pred_df, df["close"].iloc[-1], rate)

    # 概览
    last_close = df["close"].iloc[-1]
    end_close = pred_df["close"].iloc[-1]
    chg = (end_close / last_close - 1) * 100
    print(f"\n📈 现价(前复权) {last_close:.2f} → 第 {args.pred_len} 日预测 {end_close:.2f}  "
          f"({chg:+.2f}%)")
    print(pred_df[["date", "open", "high", "low", "close"]].to_string(index=False))

    # 落盘
    args.out.mkdir(parents=True, exist_ok=True)
    cols = ["date", "open", "high", "low", "close", "volume", "amount"]
    out_csv = args.out / f"pred_{ts_code.replace('.', '_')}_data.csv"
    pd.concat([df[cols], pred_df[cols]]).reset_index(drop=True).to_csv(out_csv, index=False)
    print(f"\n✅ 历史+预测已保存: {out_csv}")
    plot_result(df, pred_df, ts_code, args.out)


if __name__ == "__main__":
    main()
