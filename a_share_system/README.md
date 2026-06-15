# A股交易系统 v2.0

基于 2021–2026 年 Tushare 历史数据的 A 股辅助决策系统。

## 功能

- **每日信号扫描**：全市场横截面，12 个策略输出信号池
- **历史回测**：复用同一套策略代码，逐日回放任意日期范围
- **价格行为研究**：Brooks H2 等形态信号 + 交易者方程回测验证
- **Web 仪表盘**：Apple 风格暗色界面，左侧市场概况 + 右侧策略信号 + K 线弹窗

## 架构

```
data/       DuckDB 数据层（历史导入 + 每日更新 + 复权视图 + 回填脚本）
engine/     策略引擎（12 个策略 + price_action 特征库 + runner + backtest）
web/        FastAPI 后端 + Vue3 前端
```

设计方向：**三层架构**——情绪周期（全市场总开关）→ 资金面/题材选股 → 价格行为择时与风控。详见 `docs/specs/2026-06-12-brooks-phase1-design.md`。

## 快速开始

推荐用启动脚本（自动包好 conda 前缀、数据库锁检查、前端构建检查）：

```bash
./scripts/start.sh            # 启动 Web → http://localhost:8080
./scripts/start.sh daily      # 盘后一条龙：update → run → serve
./scripts/start.sh update     # 仅拉当日/缺口数据
./scripts/start.sh run        # 仅扫描信号
```

底层等价命令：

```bash
conda run -n mxk_env python -m a_share_system.main <serve|update|run|backtest|migrate|news>
# 回测示例
conda run -n mxk_env python -m a_share_system.main backtest 20260101 20260508
```

## 数据层

| 表 / 视图 | 内容 | 覆盖 |
|------|------|------|
| `daily` | 日线 OHLCV（未复权） | 1315 交易日全 |
| `daily_qfq` / `daily_hfq` | 前复权 / 后复权视图（形态用 qfq，回测收益用 hfq） | 同 daily |
| `adj_factor` | 复权因子 | 1315 交易日全 |
| `daily_basic` | PE/PB/换手/量比/市值 | 1315 交易日全 |
| `index_daily` | 指数日行情 | 1315 交易日全 |
| `moneyflow` | 大单资金流 | 1315 交易日全 |
| `top_list` | 龙虎榜（事件表，仅上榜日有记录） | 历史稀疏 |
| `limit_list` | 涨跌停明细 | 仅近期（接口限频 1次/天） |

缺口补齐脚本（自动只补缺失交易日）：

```bash
conda run -n mxk_env python -m a_share_system.data.backfill_adj_factor
conda run -n mxk_env python -m a_share_system.data.backfill_daily_basic
conda run -n mxk_env python -m a_share_system.data.backfill_moneyflow
```

## 策略清单

| 标识 | 名称 | 逻辑 |
|------|------|------|
| `LIMIT_UP` | N字涨停 | 涨幅 ≥ 9.5%，确认封单 |
| `VOLUME_SPIKE` | 突然爆量 | 量比 > 3 且涨幅 > 3% |
| `MA_BREAKOUT` | 均线突破 | MA5 上穿 MA10，或价格站上 MA60 |
| `MACD_CROSS` | MACD金叉 | DIF 上穿 DEA |
| `MACD_DIVERGENCE` | MACD底背离 | 价格新低但 DIF 不创新低 |
| `CONSECUTIVE` | 连板龙头 | 连续涨停 ≥ 2 天 |
| `BIG_MONEY` | 大单净流入 | 大单净买入/成交额 ≥ 阈值，且阳线 |
| `SECTOR_HOT` | 板块联动 | 同行业当日涨停数 ≥ 3，且本股涨 ≥ 2% |
| `TOP_LIST` | 龙虎榜买入 | 龙虎榜净买入 > 0，且当日上涨 |
| `PULLBACK` | 龙头回踩 | 回踩均线后放量阳线二次发力 |
| `BROOKS_H2` | Brooks H2 | 上升趋势回调二次入场（价格行为，基于 qfq） |
| `RESONANCE` | 多策略共振 | 同一股票触发 ≥ 2 个策略 |

## 数据范围

- 历史数据：2021-01-04 至今，约 1315 个交易日，约 658 万行日线
- 数据库：`market.duckdb`（单文件，DuckDB；单写者，勿并发写）
- 数据源：Tushare Pro API

## 环境

```bash
conda activate mxk_env
# 依赖：duckdb, tushare, fastapi, uvicorn, pandas, numpy, pytest
```
