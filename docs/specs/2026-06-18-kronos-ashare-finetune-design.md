# Kronos A 股版本微调 — 技术方案

- **日期**：2026-06-18
- **状态**：P0 已完成（2026-06-18）；P1 待推进（需云 GPU）
- **目标读者**：本系统维护者 / 后续实现模型
- **范围**：把通用 Kronos 基座模型微调成 **A 股日线专用**模型，全市场多股票，产出可接入 `a_share_system` 的预测信号源。

---

## 0. TL;DR

- 通用 Kronos base 已能零样本预测 A 股（见 `Kronos/examples/predict_from_duckdb.py`），本方案是把它**专精化**。
- **核心简化**：官方 `finetune/` 是多股票横截面管线，但绑定 Qlib。其 `QlibDataset` 本质只吃一个 `{symbol: DataFrame}` 的 pickle —— 我们**绕开 Qlib**，写一个 DuckDB→pickle 预处理器，其余训练脚本几乎原样复用。
- 数据走 **`daily_qfq` 前复权**（守复权红线）；归一化是窗口内 z-score，qfq/hfq 等价但 qfq 输出锚定现价。
- **硬件硬约束**：微调必须 NVIDIA GPU，Mac 跑不动 → 数据导出在本机做，训练上云 GPU。
- 评估口径：预测信号的**收益**回测用 `daily_hfq`（复权红线另一面）。

---

## 1. 目标与非目标

### 目标
1. 用全市场 A 股日线（前复权）微调 Kronos 的 **tokenizer + predictor**。
2. 微调后模型在 A 股 test 区间上，预测质量（方向命中率 / IC / top-K 回测）优于 base 零样本。
3. 模型产物可被 `predict_from_duckdb.py` 直接 `--model` 切换，并包装成 `a_share_system` 的一个信号源。

### 非目标（本期不做）
- 分钟级 / 日内预测（DuckDB 目前只有日线）。
- 组合优化、风险因子中性化、交易成本精细建模（属于"信号→策略"层，另立项）。
- Web 端实时推理服务。

---

## 2. 现状与基线

| 项 | 现状 |
|----|------|
| 基座可用性 | base(102M) + Tokenizer-base 零样本已跑通，~7 秒/次（Mac CPU，pred_len=10） |
| 数据 | DuckDB `daily_qfq`：**2021-01-04 ~ 2026-06-15，1316 交易日，5467 只票（≥101 根），658 万行** |
| 官方微调管线 | `Kronos/finetune/`（Qlib，多股票，含 top-K 回测）；`Kronos/finetune_csv/`（单 CSV，单序列，不适合全市场） |
| 环境 | `mxk_env` 已装 torch/einops/safetensors/huggingface_hub/matplotlib/socksio |

**基线对照**：零样本 base 的 test 区间表现，作为微调收益的 baseline。微调若打不过零样本，则不值得投入。

---

## 3. 核心架构决策：绕开 Qlib，复用官方训练脚本

官方 `finetune/dataset.py::QlibDataset` 的真实契约（已读源码确认）：

- 它从 `train_data.pkl / val_data.pkl` 反序列化出一个 **`{symbol: DataFrame}`** 字典；
- 每个 DataFrame 需含 `datetime` 列 + 特征列 `['open','high','low','close','vol','amt']`；
- 时间特征 `minute/hour/weekday/day/month` 由 `datetime` 现场派生（日线下 minute/hour=0，无害）；
- 归一化在 `__getitem__` 内做：**仅用 lookback 段算 mean/std 的窗口内 z-score**，再 clip 到 ±5（防未来泄漏，源码 L108-117 明确注释）。

> ⚠️ 特征列名是 **`vol` / `amt`**（不是 volume/amount），导出时要对齐。

**结论**：Qlib 只是个数据来源，对训练不是必需。我们只要产出**同结构的 pickle**，即可：
- ✅ 原样复用 `train_tokenizer.py`、`train_predictor.py`（DDP / torchrun）；
- ✏️ 替换 `qlib_data_preprocess.py` → 自研 `duckdb_data_preprocess.py`；
- ✏️ 改造 `qlib_test.py`（回测里有 Qlib 调用）→ 复用 `a_share_system` 现有回测器。

这样既不引入 Qlib 依赖，又守住「数据一律走 DuckDB」的系统约定。

```
DuckDB daily_qfq ──(duckdb_data_preprocess.py)──> {symbol: df} pickle
                                                        │
                              ┌─────────────────────────┼─────────────────────────┐
                              ▼                          ▼                         ▼
                     train_tokenizer.py        train_predictor.py          评估/回测
                     (复用，30 epoch)          (复用)                  (a_share_system 回测器, hfq)
```

---

## 4. 数据方案

### 4.1 来源与口径
- **视图**：`daily_qfq`（前复权）。**红线**：形态/K 线/训练输入禁用原始 `daily`（除权跳空会被当暴涨暴跌）。
- qfq vs hfq：两者仅差全局常数倍率，经窗口内 z-score 后**对训练完全等价**；选 qfq 是因为推理输出锚定当前真实盘面价，可读、可直接喂涨跌停裁剪。
- 列映射：`open/high/low/close` 直取；`vol → vol`，`amount → amt`；`trade_date(INT) → datetime`。

### 4.2 样本范围与清洗
- **全市场 5467 只票**（历史 ≥ `lookback+predict+1 = 101` 根才够一个窗口，5536 中 69 只新股不够，自动丢弃）。
- **退市股**：DuckDB 若含已退市票，**应纳入**训练（避免幸存者偏差）；但评估/回测时按交易日对齐，退市后自然退出。
- **停牌缺口**：日线停牌会造成日期不连续。滑窗按"行"切而非按"日历日"切，停牌前后会被当连续 → 可接受（base 也这么处理）；极端长停牌的票可设阈值剔除。
- **极端值**：一字涨跌停、低价股的大跳动 → 窗口 z-score + `clip=5.0` 已能压制。
- **新股**：上市初期高波动，靠 ≥101 根门槛 + 后续 val/test 时间切分自然降权。

### 4.3 时间切分（防未来函数）
按时间切，边界向前重叠 ≥ `lookback`(90 交易日 ≈ 4.5 个月) 以填满首样本的回看窗：

| 集 | 区间 | 说明 |
|----|------|------|
| **train** | 2021-01-04 ~ 2024-12-31 | ~4 年 |
| **val** | 2024-08-01 ~ 2025-06-30 | 起点前置 ~5 月填 lookback |
| **test** | 2025-02-01 ~ 2026-06-15 | ~1 年纯样本外，含 lookback 前置 |

> 切分按 symbol 内各自的时间轴做；绝不能跨集泄漏未来行。

### 4.4 规模估算
658 万行 / 5467 票，平均每票 ~1200 根。滑窗（lookback90+predict10）可枚举约 **数百万个样本**，远超官方 demo 的 `n_train_iter=10万/epoch`，数据量充足，不缺样本。pickle 体积量级约几百 MB ~ 1-2 GB（仅保留必要列）。

---

## 5. 训练管线

### 5.1 两阶段
1. **Tokenizer 微调**（30 epoch）：让 OHLCV→token 的量化适配 A 股价格/振幅分布（±10%/20%、T+1 缺口）。
2. **Predictor 微调**（依赖上一步产出的 tokenizer）：在 A 股 token 上继续自回归训练。

`train_sequential` 思路可顺序跑；也可分开跑便于排错。

### 5.2 模型选型
- **起步用 Kronos-small(24.7M)**：官方 demo 默认就微调 small，显存/时长友好，先验证管线与收益。
- base(102M) 作为收益验证后的升级项。
- mini(4.1M) 不建议（容量太小）。

### 5.3 关键超参（沿用官方 `finetune/config.py`，按需调）
- `lookback_window=90`、`predict_window=10`、`max_context=512`、`clip=5.0`
- `tokenizer_lr=2e-4`、`predictor_lr=4e-5`、`batch_size=50/GPU`、`adam(0.9,0.95)`、`wd=0.1`
- `instrument` 概念替换为"全市场池"；benchmark 用沪深300（`SH000300`）或中证全指
- 关掉 Comet（`use_comet=False`）或换自有日志

---

## 6. 硬件与环境

| 任务 | 在哪 | 说明 |
|------|------|------|
| 数据导出 pickle | **本机 Mac** | 只读 DuckDB，`read_only=True`，纯 pandas，无需 GPU |
| Tokenizer/Predictor 微调 | **云 NVIDIA GPU** | 脚本依赖 CUDA/nccl，Mac 无 N 卡跑不动；MPS 需改 hardcode 且性能半残 |
| 推理/评估 | 本机或云 | small 模型 Mac CPU 可推理 |

- **云 GPU 估算**：单张 4090/A100，small 模型 + 数百万样本，tokenizer+predictor 合计**数小时 ~ 1 天**量级（取决于 epoch 与样本采样数）。
- 云端需重建环境：torch / einops / safetensors / huggingface_hub（+ 上传 pickle 与 base 权重）。
- 数据传输：导出的 pickle（~1GB）上传云端。

---

## 7. 评估方案

### 7.1 对照实验
同一 test 区间，**微调模型 vs base 零样本**，三层指标：
1. **点预测**：预测 close 序列 vs 实际的 MAE / RMSE（归一化后）。
2. **方向/因子**：预测 N 日收益的 **IC / RankIC、方向命中率**（这是当信号源最关心的）。
3. **组合回测**：top-K 策略（官方 hold50/drop5）年化 / 夏普 / 最大回撤 vs 基准。

### 7.2 收益口径（红线另一面）
- 模型**输入/预测**用 `daily_qfq`；
- 回测**算持仓收益**那一步用 **`daily_hfq`**（后复权，收益跨除权连续正确）。
- 涨跌停、T+1 在回测撮合层建模（用原始 `daily` 的 pre_close 判涨跌停）。

---

## 8. 集成到 a_share_system

1. **最小接入**：`predict_from_duckdb.py --model <finetuned_path>` 即可用 A 股专用权重。
2. **信号化**：把预测产物转成因子写入 `signals` 表（同现有 12 策略的 schema：`ts_code/trade_date/strategy='KRONOS'/score/...`）。候选因子：
   - 预测未来 N 日收益率（连续分）；
   - 预测"创 M 日新高"概率（多采样路径频率）；
   - 预测形态与现有规则信号的**共振过滤**。
3. **定位**：作为第 13 个信号源，模型驱动，与规则信号互补，不单独决策。

---

## 9. 风险与坑

| 风险 | 缓解 |
|------|------|
| 未来函数 | 时间切分 + 窗口内归一化（仅 lookback 段）；test 严格样本外 |
| 幸存者偏差 | 纳入退市股训练 |
| qfq/hfq 混用 | 训练/预测 qfq，收益回测 hfq，文档化、代码隔离 |
| 日线远端不可靠 | predict_window=10；远端只作形态参考，不作点位信号 |
| 过拟合单一行情 | 全市场 + 4 年 train 跨牛熊；val 早停 |
| T+1/涨跌停 | 预测层不强制，交易/回测层建模 |
| 停牌/流动性 | 长停牌剔除；低流动性票在信号层加流动性过滤 |
| 算力 | 先 small 验证收益，再决定是否上 base/加卡 |

---

## 10. 分期里程碑

| 阶段 | 产出 | 在哪 | 门槛 | 状态 |
|------|------|------|------|------|
| **P0** | baseline_eval.py（零样本评估）+ finetune_single_stock.py（单票微调验证） | Mac，免费 | 微调后命中率提升 ≥ 2pp | ✅ 完成（2026-06-18）：零样本命中率 48.25%；单票（600036）5 epoch 后命中率 +8pp，IC -0.22→+0.26 |
| **P1** | duckdb_data_preprocess.py（全市场导出 pickle）；去 Qlib 依赖的训练脚本 | 云 GPU 短时 | 管线无误、loss 收敛 | ⬜ 待推进 |
| **P2** | **全市场全量微调**（small），产出 A 股专用 tokenizer+predictor | 云 GPU | test 指标 > 零样本 baseline | ⬜ 待推进 |
| **P3** | 回测（hfq）+ 接入 `signals` 表当信号源 | Mac | IC/回测达标 | ⬜ 待推进 |

P0 不依赖 GPU、不浪费——是任何后续步骤的前置，**建议先做 P0**。

---

## 附录：需新建 / 改动的文件清单

| 文件 | 动作 | 说明 |
|------|------|------|
| `Kronos/finetune/duckdb_data_preprocess.py` | 新建 | DuckDB `daily_qfq` → `{symbol: df}` pickle，列映射 vol/amt，时间切分 |
| `Kronos/finetune/config.py` | 改 | 路径、`use_comet=False`、池/基准、pickle 路径 |
| `Kronos/finetune/train_tokenizer.py` | 复用 | 基本不改 |
| `Kronos/finetune/train_predictor.py` | 复用 | 基本不改 |
| `Kronos/finetune/qlib_test.py` | 改/替 | 去 Qlib，改用 `a_share_system` 回测器 + `daily_hfq` |
| `Kronos/examples/predict_from_duckdb.py` | 已有 | 推理脚本，`--model` 指向微调产物即可 |
| `a_share_system/strategies/…`（信号接入） | 后续 | P3，把预测写入 `signals` 表 |
