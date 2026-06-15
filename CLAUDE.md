# CLAUDE.md

A 股交易辅助系统。Python 包 `a_share_system`（DuckDB 数据层 + 策略引擎 + FastAPI/Vue3 Web）。

## 硬边界（违反会出错）

- **一律用 conda 环境**：所有 Python 命令前缀 `conda run -n mxk_env`（依赖 duckdb/tushare/fastapi/pandas 都在这个环境）。
- **复权红线**：形态 / K 线 / 价格行为分析**必须用 `daily_qfq` 视图**（前复权），回测收益用 `daily_hfq`（后复权）。**禁止用原始 `daily` 做形态分析**——除权除息跳空会被误判成暴涨暴跌。`daily` 仅用于涨跌停判定（需原始 pre_close）和资金面策略。
- **DuckDB 单写者**：`market.duckdb` 同时只能有一个写连接。`update` / `run` / 回填脚本写库时持锁，期间别开第二个写进程。`./scripts/start.sh serve` 启动前会做锁检查并友好提示。只读分析用 `read_only=True`。
- **Tushare token 硬编码在 `a_share_system/config.py`**：本仓库是 private，刻意为之，**不要**改成环境变量。

## 命令速查

```bash
./scripts/start.sh [serve|daily|update|run]      # 日常入口（已包好 conda + 锁检查）
conda run -n mxk_env python -m a_share_system.main <serve|update|run|backtest|migrate|news>
conda run -n mxk_env python -m a_share_system.data.backfill_<adj_factor|daily_basic|moneyflow>
conda run -n mxk_env python -m pytest a_share_system/tests/ -x -q
conda run -n mxk_env python scripts/backtest_brooks_h2.py [--quick]
```

## 约定 / 已知情况

- **目录**：`scripts/` 散装脚本与回测器 · `archive/` 旧版本（gitignore，不入库） · `docs/specs|reports` 设计与回测报告 · 大数据/媒体在仓库外 `~/Archives/`。
- **数据缺口**：`limit_list` 接口限频严（1次/天），历史补不动，仅近期有；`top_list` 是事件表，历史稀疏。其余表（daily / daily_basic / adj_factor / index_daily / moneyflow）均 1315 交易日全覆盖。
- **预存测试失败**：`test_ma_breakout_detects_ma5_cross_ma10` 是历史遗留失败，与近期改动无关。
- **分工偏好**：方案/设计可由当前模型出，代码实现倾向交给 Opus 4.8（见 agent 记忆）；执行终端命令需用户明确要求。

## 深入文档

| 主题 | 文档 |
|------|------|
| 系统总览 / 策略清单 / 数据表 | `a_share_system/README.md` |
| Brooks 价格行为 Phase 1 设计 | `docs/specs/2026-06-12-brooks-phase1-design.md` |
| BROOKS_H2 回测结论（H-1~H-5） | `docs/reports/2026-06-12-brooks-h2-backtest.md` |
