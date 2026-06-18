# -*- coding: utf-8 -*-
"""
finetune_single_stock.py

单票快速微调验证脚本（Mac CPU 可跑）：
  1. 从 DuckDB daily_qfq 导出单只票前复权日线 CSV
  2. 微调 Kronos Tokenizer（5 epoch）
  3. 微调 Kronos Predictor（5 epoch）
  4. 在 test 区间评估：零样本 base vs 微调后，对比方向命中率 / IC
  5. 输出对比图

目的：P0 go/no-go 的补充验证——
  如果微调后方向命中率 > 零样本 base ≥ 2pp，说明微调有效果，
  全市场全量微调才值得花 GPU 算力。

用法:
    # 快速（5 epoch，约 7 分钟 Mac CPU）
    conda run -n mxk_env python model/kronos/finetune_single_stock.py --code 600036

    # 指定股票和 epoch 数
    conda run -n mxk_env python model/kronos/finetune_single_stock.py --code 601318 --tok-epochs 10 --pred-epochs 5
"""

import os
import sys
import argparse
import logging
import random
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import torch
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

KRONOS_ROOT   = Path(__file__).resolve().parent        # model/kronos/
FINETUNE_DIR  = KRONOS_ROOT / "finetune"
M_ROOT        = KRONOS_ROOT.parents[1]                 # M/
DEFAULT_DB    = M_ROOT / "a_share_system" / "market.duckdb"
DEFAULT_OUT   = KRONOS_ROOT / "outputs"
DEFAULT_CFG   = FINETUNE_DIR / "configs" / "config_ashare_single_stock.yaml"

sys.path.insert(0, str(KRONOS_ROOT))
sys.path.insert(0, str(FINETUNE_DIR))

from model import Kronos, KronosTokenizer, KronosPredictor  # noqa: E402
from finetune_tokenizer import train_tokenizer               # noqa: E402
from finetune_base_model import train_model                  # noqa: E402
from config_loader import CustomFinetuneConfig               # noqa: E402


# ─── 工具 ─────────────────────────────────────────────────────────────────────

def normalize_code(code: str) -> str:
    code = code.strip().upper()
    if "." in code:
        return code
    digits = "".join(c for c in code if c.isdigit())
    if len(digits) != 6:
        raise ValueError(f"无法识别股票代码: {code}")
    return f"{digits}.{'SH' if digits[0] in '69' else ('BJ' if digits[0] in '48' else 'SZ')}"


def make_logger(name: str, log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(str(log_path), encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(ch)
    return logger


# ─── Step 1：导出 CSV ──────────────────────────────────────────────────────────

def export_csv(db_path: Path, ts_code: str, csv_path: Path) -> pd.DataFrame:
    """从 daily_qfq 导出前复权日线为 finetune_csv 所需格式。"""
    print(f"📥 导出 {ts_code} 前复权日线 → {csv_path}")
    con = duckdb.connect(str(db_path), read_only=True)
    df = con.execute(
        """
        SELECT trade_date, open, high, low, close,
               vol AS volume, amount
        FROM daily_qfq
        WHERE ts_code = ?
        ORDER BY trade_date
        """,
        [ts_code],
    ).fetch_df()
    con.close()

    if df.empty:
        sys.exit(f"❌ {ts_code} 在 daily_qfq 无数据")

    df["timestamps"] = pd.to_datetime(
        df["trade_date"].astype(int).astype(str), format="%Y%m%d"
    )
    df = df[["timestamps", "open", "high", "low", "close", "volume", "amount"]]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(str(csv_path), index=False)
    print(f"✅ 导出 {len(df)} 根  {df['timestamps'].iloc[0].date()} ~ {df['timestamps'].iloc[-1].date()}")
    return df


# ─── Step 2：修改 config 并训练 ──────────────────────────────────────────────

def patch_config(cfg_path: Path, csv_path: Path, out_dir: Path,
                 tok_epochs: int, pred_epochs: int) -> CustomFinetuneConfig:
    """动态替换 config 中的路径和 epoch 数，返回 config 对象。"""
    import yaml
    with open(str(cfg_path), "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    raw["data"]["data_path"] = str(csv_path)
    raw["model_paths"]["base_path"] = str(out_dir)
    raw["training"]["tokenizer_epochs"] = tok_epochs
    raw["training"]["basemodel_epochs"] = pred_epochs

    patched_path = out_dir / "config_patched.yaml"
    patched_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(patched_path), "w", encoding="utf-8") as f:
        yaml.dump(raw, f, allow_unicode=True)

    return CustomFinetuneConfig(str(patched_path))


def run_finetune(config: CustomFinetuneConfig, logger: logging.Logger):
    device = torch.device("cpu")   # Mac 强制 CPU
    print(f"Using device: {device}")

    os.makedirs(config.tokenizer_save_path, exist_ok=True)
    os.makedirs(config.basemodel_save_path, exist_ok=True)

    # ── Tokenizer ──
    print("\n🔧 微调 Tokenizer ...")
    tokenizer = KronosTokenizer.from_pretrained(config.pretrained_tokenizer_path)
    tokenizer = tokenizer.to(device)
    train_tokenizer(tokenizer, device, config, config.tokenizer_save_path, logger)

    # ── Predictor（接微调后的 tokenizer）──
    print("\n🔧 微调 Predictor ...")
    finetuned_tok_path = os.path.join(config.tokenizer_save_path, "best_model")
    tokenizer_ft = KronosTokenizer.from_pretrained(finetuned_tok_path)
    tokenizer_ft = tokenizer_ft.to(device)

    model = Kronos.from_pretrained(config.pretrained_predictor_path)
    model = model.to(device)
    train_model(model, tokenizer_ft, device, config, config.basemodel_save_path, logger)


# ─── Step 3：评估对比 ────────────────────────────────────────────────────────

def evaluate(db_path: Path, ts_code: str, df_full: pd.DataFrame,
             base_predictor: KronosPredictor, ft_predictor: KronosPredictor,
             pred_len: int, lookback: int, test_ratio: float,
             out_dir: Path) -> dict:
    """
    在 test 区间滑窗评估 base vs 微调后的方向命中率 / IC。
    test 区间 = df_full 末尾 test_ratio 部分，再往前留 lookback 根做回看。
    """
    total = len(df_full)
    test_start_idx = int(total * (1 - test_ratio)) - lookback
    test_df = df_full.iloc[test_start_idx:].reset_index(drop=True)
    print(f"\n📊 评估区间: {test_df['timestamps'].iloc[lookback].date()} ~ {test_df['timestamps'].iloc[-1].date()}")

    records = []
    # 每隔 5 个交易日取一个预测点，避免样本过度重叠
    for i in range(lookback, len(test_df) - pred_len, 5):
        x_df = test_df.iloc[i - lookback: i][
            ["open", "high", "low", "close", "volume", "amount"]
        ]
        x_ts = test_df.iloc[i - lookback: i]["timestamps"].reset_index(drop=True)
        y_ts = pd.Series(test_df.iloc[i: i + pred_len]["timestamps"].values)

        base_close  = test_df.iloc[i - 1]["close"]       # 预测日前一根收盘（基准价）
        actual_close = test_df.iloc[i + pred_len - 1]["close"]
        actual_ret  = actual_close / base_close - 1

        for label, predictor in [("base", base_predictor), ("finetuned", ft_predictor)]:
            try:
                pred_df = predictor.predict(
                    df=x_df, x_timestamp=x_ts, y_timestamp=y_ts,
                    pred_len=pred_len, T=1.0, top_p=0.9, sample_count=3, verbose=False,
                )
                pred_ret = pred_df["close"].iloc[-1] / pred_df["close"].iloc[0] - 1
            except Exception:
                continue
            records.append({
                "label":      label,
                "pred_ret":   float(pred_ret),
                "actual_ret": float(actual_ret),
                "dir_ok":     int(np.sign(pred_ret) == np.sign(actual_ret)),
            })

    df_rec = pd.DataFrame(records)
    if df_rec.empty:
        print("⚠️  无有效评估样本")
        return {}

    results = {}
    print("\n" + "=" * 55)
    print(f"  单票微调评估  {ts_code}  pred_len={pred_len}日")
    print("=" * 55)
    for label in ["base", "finetuned"]:
        sub = df_rec[df_rec["label"] == label]
        n   = len(sub)
        hit = sub["dir_ok"].mean()
        ic  = sub["pred_ret"].corr(sub["actual_ret"])
        se  = np.sqrt(hit * (1 - hit) / n)
        _, p = stats.ttest_1samp(sub["dir_ok"], 0.5)
        print(f"  [{label:>10}]  N={n}  命中率={hit:.4f} ±{se:.4f}  IC={ic:.4f}  p={p:.4f}")
        results[label] = {"n": n, "hit": hit, "ic": ic, "p": p}

    base_hit = results.get("base", {}).get("hit", 0)
    ft_hit   = results.get("finetuned", {}).get("hit", 0)
    delta    = ft_hit - base_hit
    print("-" * 55)
    print(f"  命中率提升: {delta:+.4f} ({delta*100:+.2f}pp)")
    if delta >= 0.02:
        print("  → ✅ 微调有效，方向命中率提升 ≥ 2pp，建议推进全市场微调")
    elif delta >= 0:
        print("  → ⚠️  微调有轻微提升，但未到 2pp 门槛，可尝试增加 epoch")
    else:
        print("  → ❌ 微调后反而下降，单票数据量可能不足，建议多股票联合微调")
    print("=" * 55)

    # ── 散点图对比 ──
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    colors = {"base": "#1f77b4", "finetuned": "#d62728"}
    for ax, label in zip(axes, ["base", "finetuned"]):
        sub = df_rec[df_rec["label"] == label]
        ax.scatter(sub["pred_ret"], sub["actual_ret"], alpha=0.5, s=20, color=colors[label])
        lim = max(sub["pred_ret"].abs().max(), sub["actual_ret"].abs().max()) * 1.1
        ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)
        ax.axhline(0, color="gray", lw=0.8); ax.axvline(0, color="gray", lw=0.8)
        ic_val = results.get(label, {}).get("ic", 0)
        hit_val = results.get(label, {}).get("hit", 0)
        ax.set_title(f"{label}  命中率={hit_val:.3f}  IC={ic_val:.3f}")
        ax.set_xlabel("预测收益率"); ax.set_ylabel("实际收益率")

    plt.suptitle(f"零样本 base vs 微调后 — {ts_code}  pred_len={pred_len}日", fontsize=11)
    plt.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_path = out_dir / f"finetune_eval_{ts_code.replace('.','_')}.png"
    plt.savefig(str(plot_path), dpi=120)
    plt.close()
    print(f"\n📊 对比图已保存: {plot_path}")

    df_rec.to_csv(out_dir / f"finetune_eval_{ts_code.replace('.','_')}.csv", index=False)
    return results


# ─── 主流程 ───────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="单票快速微调验证")
    ap.add_argument("--code",        default="600036",    help="股票代码，如 600036 / 600036.SH")
    ap.add_argument("--db",          type=Path, default=DEFAULT_DB)
    ap.add_argument("--out",         type=Path, default=DEFAULT_OUT)
    ap.add_argument("--config",      type=Path, default=DEFAULT_CFG)
    ap.add_argument("--tok-epochs",  type=int,  default=5,  help="tokenizer 微调 epoch 数")
    ap.add_argument("--pred-epochs", type=int,  default=5,  help="predictor 微调 epoch 数")
    ap.add_argument("--pred-len",    type=int,  default=10)
    ap.add_argument("--lookback",    type=int,  default=120)
    ap.add_argument("--seed",        type=int,  default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    ts_code  = normalize_code(args.code)
    slug     = ts_code.replace(".", "_")
    work_dir = args.out / "finetune" / slug

    logger = make_logger(f"finetune_{slug}", work_dir / "logs" / "finetune.log")

    # 1. 导出 CSV
    csv_path = work_dir / f"{slug}_qfq.csv"
    df_full  = export_csv(args.db, ts_code, csv_path)

    # 2. 加载 base（评估用，不训练）
    print("\n🚀 加载 base 模型（零样本对照）...")
    base_tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    base_model     = Kronos.from_pretrained("NeoQuasar/Kronos-base")
    base_predictor = KronosPredictor(base_model, base_tokenizer, device="cpu",
                                     max_context=args.lookback)

    # 3. 微调
    config = patch_config(args.config, csv_path, work_dir,
                          args.tok_epochs, args.pred_epochs)
    run_finetune(config, logger)

    # 4. 加载微调后的模型
    ft_tok_path  = os.path.join(config.tokenizer_save_path, "best_model")
    ft_pred_path = os.path.join(config.basemodel_save_path, "best_model")
    print(f"\n📦 加载微调后模型: tokenizer={ft_tok_path}")
    ft_tokenizer = KronosTokenizer.from_pretrained(ft_tok_path)
    ft_model     = Kronos.from_pretrained(ft_pred_path)
    ft_predictor = KronosPredictor(ft_model, ft_tokenizer, device="cpu",
                                   max_context=args.lookback)

    # 5. 评估对比
    evaluate(
        db_path=args.db,
        ts_code=ts_code,
        df_full=df_full,
        base_predictor=base_predictor,
        ft_predictor=ft_predictor,
        pred_len=args.pred_len,
        lookback=args.lookback,
        test_ratio=0.10,
        out_dir=args.out,
    )


if __name__ == "__main__":
    main()
