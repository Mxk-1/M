# A股交易系统 v2.0

基于 2021–2026 年 Tushare 历史数据的 A 股辅助决策系统。

## 功能

- **每日信号扫描**：全市场横截面，输出策略信号池
- **历史回测**：复用同一套策略代码，逐日回放任意日期范围
- **Web 仪表盘**：Apple 风格暗色界面，左侧市场概况 + 右侧策略信号

## 架构

```
data/       DuckDB 数据层（历史导入 + 每日更新）
engine/     策略引擎（7 个策略 + runner + backtest）
web/        FastAPI 后端 + 静态前端
```

## 快速开始

```bash
# 首次：导入历史 CSV 数据
python -m a_share_system.main migrate

# 每日更新 + 扫描信号
python -m a_share_system.main update
python -m a_share_system.main run

# 启动 Web（访问 http://localhost:8080）
python -m a_share_system.main serve

# 历史回测（指定日期范围）
python -m a_share_system.main backtest 20260101 20260508
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
| `RESONANCE` | 多策略共振 | 同一股票触发 ≥ 2 个策略 |

## 数据范围

- 历史数据：2021-01-04 至今，约 1292 个交易日，608 万行日线
- 数据库：`market.duckdb`（单文件，DuckDB）
- 数据源：Tushare Pro API

## 环境

```bash
conda activate mxk_env
# 依赖：duckdb, tushare, fastapi, uvicorn, pandas, pytest
```
