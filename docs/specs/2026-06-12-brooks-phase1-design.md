# Brooks 价格行为 Phase 1 设计：特征库 + BROOKS_H2 + 回测验证

> 2026-06-12 · 设计：Fable / 实现：Opus 4.8
> 前置依赖：adj_factor 已回填、daily_qfq 视图可用（schema.sql 已就绪）

## 0. 背景与范围

将 Al Brooks 价格行为体系适配 A 股日线，作为三层架构的第三层（执行与风控层）：

```
第一层  情绪周期（全市场总开关）   ← Phase 1 仅产出指标，不做策略
第二层  选股（资金面+题材）        ← 已有 BIG_MONEY / SECTOR_HOT / TOP_LIST
第三层  价格行为（择时与风控）     ← 本期：特征库 + BROOKS_H2 策略
```

**Phase 1 交付物**：
1. `engine/price_action.py` —— 价格行为特征库（纯函数，无状态）
2. `engine/strategies/brooks_h2.py` —— H2 回调二次入场策略
3. 回测验证报告 —— 假设 H-1 ~ H-5 的统计结论

**明确不做**：情绪开关策略、failed breakout 策略（Phase 2）、前端标注（Phase 4）、分钟级数据。

## 1. 数据约定

- **所有形态计算一律使用 `daily_qfq` 视图**（前复权），禁止直接用 `daily` 原始价——除权跳空会产生假信号。
- `pct_chg`、`vol`、`amount` 复权不变，直接透传。
- 输入统一为单只股票按 `trade_date` 升序的 DataFrame，列：`trade_date, open, high, low, close, pct_chg, vol, amount`。

## 2. 特征库 `engine/price_action.py`

### 2.1 单棒特征（逐行计算）

| 特征 | 定义 | 备注 |
|---|---|---|
| `body_ratio` | abs(close−open) / (high−low) | high==low 时取 0 |
| `upper_tail` | (high−max(open,close)) / (high−low) | 上影占比 |
| `lower_tail` | (min(open,close)−low) / (high−low) | 下影占比 |
| `is_trend_bar` | body_ratio ≥ 0.6 | 阈值进参数表 |
| `is_doji` | body_ratio ≤ 0.25 | |
| `gap_pct` | (open − prev_close) / prev_close | 隔夜缺口 |
| `is_limit_up` | 收盘价==当日涨停价（由 pre_close 推算并按交易所规则四舍五入到分） | 主板±10%、创业板/科创板(300/301/688/689)±20%、ST±5%；**勿用 pct_chg≥9.8 近似** |
| `is_limit_board` | is_limit_up 且 open==high==low==close | 一字板，不可成交 |
| `touched_limit` | high==涨停价 且 close<涨停价 | 炸板（盘中触及未封住） |

### 2.2 滚动上下文特征

| 特征 | 定义 |
|---|---|
| `ema20` / `ema20_slope` | EMA20 及其 5 日斜率（归一化：slope/ema20） |
| `consec_trend_bars` | 同向趋势棒连续计数（带符号，+3 = 连续3根阳趋势棒） |
| `overlap_ratio` | 近 5 棒两两区间重叠度均值，重叠度 = 重叠区间/并集区间 |
| `is_barbed_wire` | 近 5 棒中 ≥3 根 is_doji 且 overlap_ratio ≥ 0.6 |

### 2.3 摆动点与 Always-In

- **摆动高/低点**：分形定义，N=2（某棒 high 高于前后各 2 棒的 high → swing high；低点对称）。确认有 2 棒滞后，特征标注在分形棒上但**只能在确认日之后使用**（回测防未来函数的关键点）。
- **Always-In 状态机**（`always_in` ∈ {LONG, SHORT, NEUTRAL}）：
  - → LONG：close > ema20 且 ema20_slope > 0，且最近一次确认摆动低点未被跌破
  - → SHORT：对称
  - → NEUTRAL：is_barbed_wire 或 close 与 ema20 缠绕（近 5 日穿越 ≥3 次）
  - 状态有粘性：翻转需条件连续满足 2 日，避免单日噪声抖动。

### 2.4 H/L 计数（H1/H2 核心逻辑）

仅在 `always_in == LONG` 时计数（L 系对称，本期只实现 H 系）：

1. 回调开始：出现某棒 high < 前棒 high，进入 pullback 状态，leg_count=0
2. **H1**：pullback 中首次出现某棒 high > 前棒 high，leg_count=1
3. 若 H1 后价格再创回调新低（未跌破摆动结构），回到下行腿
4. **H2**：第二次出现 high > 前棒 high，leg_count=2 → 标记 `h2_signal`
5. 回调终结条件（重置状态）：close 创出趋势新高，或 always_in 翻转

## 3. 策略 `BROOKS_H2`

沿用现有策略基类与 signals 表协议（strategy='BROOKS_H2'）。

**信号日条件（T 日收盘判定，全部满足）**：
1. `always_in == LONG`
2. 当日触发 `h2_signal`
3. 信号棒质量：close 位于当日区间上半（(close−low)/(high−low) ≥ 0.5）
4. 回调深度：回调期间最低 close ≥ ema20 × 0.97（浅回调，强趋势特征）
5. 非铁丝网：`is_barbed_wire == False`
6. 流动性与基础过滤：非 ST、上市 ≥ 60 个交易日、当日 amount ≥ 1 亿
7. **可执行性**：信号本身不要求，但回测撮合时 T+1 一字板（is_limit_board）按放弃处理

**score**：基础分 60 + 信号棒质量×20 + 趋势强度（consec_trend_bars 归一）×20，存 signals.score。

**风控参数（写入信号，供回测与前端展示）**：
- 止损参考价 = 回调最低点 − 0.5×ATR(14)
- 单笔风险 R = 入场价 − 止损价；目标 = 入场价 + 2R（交易者方程基准）

## 4. 回测协议（决定结论可信度，必须严格执行）

1. **撮合**：T 日出信号，T+1 **开盘价**成交；T+1 一字涨停 → 该信号作废（单独统计作废率）
2. **持有期**：固定 5 日与 10 日两组，T+1+N 开盘价卖出（T+1 制度下最早 T+2 可卖，N≥1 自然满足）
3. **样本**：20210104 ~ 最新，全市场非 ST
4. **输出指标**（按持有期分组）：信号数、作废率、胜率、平均盈亏比、期望收益、与同期等权基准的超额、最大单笔回撤
5. **假设检验**：
   - H-1：BROOKS_H2 期望收益 > 0 且超额 > 0
   - H-3：去掉铁丝网过滤后假信号率是否显著上升（消融实验）
   - H-4：与 BIG_MONEY 同日共振子集 vs 各自单独，期望对比
   - H-5：（探索）统计"突破 20 日高点追入"在 A 股的期望，验证反转强于动量的文献结论
6. **敏感性**：body_ratio 阈值 {0.5, 0.6, 0.7}、回调深度 {0.95, 0.97, 0.99} 网格，结论随参数翻转则判定 setup 不稳健
7. **未来函数自查清单**：摆动点 2 棒滞后、EMA 不用当日后数据、qfq 因子用全历史最新值（回测可接受，因子仅影响价格比例不影响 pct_chg）

## 5. 验收标准

- [ ] `price_action.py` 纯函数、有单测（构造小型合成 K 线验证 H1/H2 计数、摆动点滞后、铁丝网判定）
- [ ] `tests/test_strategies.py` 新增 BROOKS_H2 用例，沿用现有测试风格
- [ ] `python -m a_share_system.main run` 能跑出 BROOKS_H2 信号且耗时增量 < 30s
- [ ] 回测报告含第 4 节全部指标与敏感性网格
- [ ] 不修改既有策略行为（现有测试全绿）

## 6. 已知限制

- Always-In 状态机是对 Brooks "context" 的有损压缩，预期捕捉原方法 ~60% 的判断力
- limit_list 历史薄（仅 2026-04 起），涨停语义全部从 daily 推算，新股上市首日规则（无涨跌幅）按上市 ≥60 日过滤规避
- 周线上下文（更高时间框架）本期不做，列入 Phase 2
