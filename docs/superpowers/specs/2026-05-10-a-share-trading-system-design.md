# A股交易系统 v2.0 — 设计文档

**日期**: 2026-05-10  
**状态**: 已确认，待实现  
**作者**: Irving

---

## 背景与目标

基于现有 2021-2026 年 Tushare 历史数据，重新构建一套服务于个人投资者的 A 股辅助决策系统。

**核心目标**：
- 每日盘后自动扫描全市场，输出策略信号池
- 支持 2021 年至今的历史回测，验证策略胜率
- Apple 风格 Web 仪表盘，左侧市场概况 + 右侧信号池

**现有资产**：
- `tushare/2021-2026/` — 6年完整日线数据，共约 1292 个交易日、608 万行
- `tushare/` — 指数、资金流、涨跌停、龙虎榜等辅助数据
- Tushare Pro Token（2000 积分）+ tushareMcp MCP Server
- tushare-data skill（自然语言数据查询）

---

## 系统架构

### 三层分离

```
data/       数据层    DuckDB + 每日更新脚本
engine/     策略层    策略计算，输出信号写入 DuckDB
web/        展示层    FastAPI + 纯静态 HTML，只读信号
```

### 数据流

```
CSV历史数据 ──migrate──► DuckDB
Tushare API ──updater──► DuckDB
                            │
                     engine/runner.py（每日执行）
                            │ 计算信号
                            ▼
                       signals 表（DuckDB）
                            │
                      web/app.py（只读查询）
                            │
                       浏览器（Apple风格界面）
```

---

## 目录结构

```
a_share_system/
├── data/
│   ├── db.py              # DuckDB 连接管理（单例）
│   ├── schema.sql         # 建表语句
│   ├── migrate.py         # 历史 CSV → DuckDB 一次性导入
│   └── updater.py         # 每日增量更新（Tushare API）
│
├── engine/
│   ├── base.py            # 策略基类
│   ├── signal.py          # Signal 数据结构
│   ├── runner.py          # 每日执行所有策略
│   ├── backtest.py        # 历史回测入口
│   └── strategies/
│       ├── limit_up.py        # N字涨停
│       ├── volume_spike.py    # 突然爆量
│       ├── ma_breakout.py     # 均线突破
│       ├── macd_cross.py      # MACD金叉
│       ├── macd_divergence.py # MACD底背离
│       ├── consecutive.py     # 连板龙头
│       └── resonance.py       # 多策略共振（聚合器）
│
├── web/
│   ├── app.py             # FastAPI 应用
│   ├── api/
│   │   ├── market.py      # 指数 + 情绪接口
│   │   └── signals.py     # 信号池接口
│   └── static/
│       └── index.html     # Apple 风格前端（单文件，内联 CSS/JS）
│
├── config.py              # Token、路径、策略参数
└── main.py                # 入口：update → run → serve
```

---

## 数据层设计

### 存储方案

使用 **DuckDB**（本地单文件数据库）替代 CSV 直读。

选择理由：
- 全市场横截面查询（如"找出所有量比 > 3 的股票"）比 pandas 快 5-10 倍
- 单文件，无服务端，零运维
- 原生支持直接查 CSV（迁移期间可混用）

### 表结构

```sql
-- 全市场日线（核心表，600万行历史）
CREATE TABLE daily (
    ts_code     VARCHAR NOT NULL,
    trade_date  INTEGER NOT NULL,   -- YYYYMMDD 格式
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE,
    pre_close   DOUBLE,
    pct_chg     DOUBLE,
    vol         DOUBLE,             -- 成交量（手）
    amount      DOUBLE,             -- 成交额（千元）
    PRIMARY KEY (ts_code, trade_date)
);

-- 大盘指数日线
CREATE TABLE index_daily (
    ts_code     VARCHAR NOT NULL,
    trade_date  INTEGER NOT NULL,
    close       DOUBLE,
    pct_chg     DOUBLE,
    vol         DOUBLE,
    amount      DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
);

-- 资金流向（大单净流入）
CREATE TABLE moneyflow (
    ts_code         VARCHAR NOT NULL,
    trade_date      INTEGER NOT NULL,
    net_mf_amount   DOUBLE,         -- 净流入额（万元）
    buy_lg_amount   DOUBLE,         -- 大单买入
    sell_lg_amount  DOUBLE,         -- 大单卖出
    PRIMARY KEY (ts_code, trade_date)
);

-- 涨跌停榜
CREATE TABLE limit_list (
    ts_code     VARCHAR NOT NULL,
    trade_date  INTEGER NOT NULL,
    limit       VARCHAR,            -- 'U' 涨停 / 'D' 跌停
    fd_amount   DOUBLE,             -- 封单金额
    open_times  INTEGER,            -- 开板次数
    PRIMARY KEY (ts_code, trade_date)
);

-- 龙虎榜
CREATE TABLE top_list (
    ts_code     VARCHAR NOT NULL,
    trade_date  INTEGER NOT NULL,
    net_amount  DOUBLE,             -- 净买入额
    reason      VARCHAR,
    PRIMARY KEY (ts_code, trade_date)
);

-- 股票基础信息
CREATE TABLE stock_basic (
    ts_code     VARCHAR PRIMARY KEY,
    name        VARCHAR,
    industry    VARCHAR,
    list_date   INTEGER
);

-- 策略信号输出（每日计算结果）
CREATE TABLE signals (
    ts_code       VARCHAR NOT NULL,
    trade_date    INTEGER NOT NULL,
    strategy      VARCHAR NOT NULL, -- 'LIMIT_UP' / 'VOLUME_SPIKE' 等
    score         DOUBLE,
    triggered     VARCHAR,          -- JSON 列表，共振时有多个策略名
    pct_chg       DOUBLE,
    vol_ratio     DOUBLE,           -- 量比
    boards        INTEGER,          -- 连板数
    PRIMARY KEY (ts_code, trade_date, strategy)
);
```

**设计决策**：
- `trade_date` 用 INTEGER（20260508），与现有 CSV 格式一致，无需转换
- `moneyflow` 只保留净流入和大单，精简存储
- `signals` 是策略引擎唯一输出，Web 层只读这张表

---

## 策略引擎设计

### Signal 数据结构

```python
@dataclass
class Signal:
    ts_code:    str
    name:       str
    trade_date: int
    strategy:   str         # 策略标识符
    score:      float       # 综合评分 0-100
    pct_chg:    float
    vol_ratio:  float       # 今日量 / 5日均量
    boards:     int         # 连板数，默认 0
    triggered:  list[str]   # 触发的策略列表
    extra:      dict        # 策略专属字段
```

### 策略基类

```python
class BaseStrategy:
    name: str           # 唯一标识，如 'LIMIT_UP'
    display_name: str   # 展示名，如 'N字涨停'

    def scan(self, con: duckdb.DuckDBPyConnection,
             trade_date: int) -> list[Signal]:
        raise NotImplementedError
```

### 策略清单

| 策略标识 | 展示名 | 核心逻辑 |
|---------|--------|---------|
| `LIMIT_UP` | N字涨停 | 涨幅 ≥ 9.5%，查 limit_list 确认封单 |
| `VOLUME_SPIKE` | 突然爆量 | 量比 > 3 且涨幅 > 3% |
| `MA_BREAKOUT` | 均线突破 | MA5上穿MA10，或股价站上MA60 |
| `MACD_CROSS` | MACD金叉 | DIF上穿DEA，零轴上下分类 |
| `MACD_DIVERGENCE` | MACD底背离 | 近30日价格新低但DIF不创新低 |
| `CONSECUTIVE` | 连板龙头 | 连续涨停 ≥ 2 天 |
| `RESONANCE` | 多策略共振 | 同一股票触发 ≥ 2 个策略（聚合器） |

### 每日执行流程

```python
def run_daily(con, trade_date: int):
    strategies = [LimitUpStrategy(), VolumeSpikeStrategy(), ...]
    all_signals = []
    for s in strategies:
        all_signals.extend(s.scan(con, trade_date))

    # 共振检测
    resonance = ResonanceStrategy().detect(all_signals)
    all_signals.extend(resonance)

    save_signals(con, all_signals)
```

### 回测

```python
def run_backtest(con, start_date: int, end_date: int):
    """复用同一套策略，遍历历史交易日逐日扫描"""
    for date in get_trading_days(con, start_date, end_date):
        run_daily(con, date)
```

回测与实盘**完全复用同一套策略代码**，仅日期范围不同。
新增历史年份数据（如 2019/2020）只需导入 DuckDB，无需改动策略代码。

---

## Web 层设计

### API（FastAPI，4个接口）

| 接口 | 说明 |
|------|------|
| `GET /api/dates` | 已有数据的交易日列表 |
| `GET /api/market/{date}` | 指数行情 + 市场情绪数字 |
| `GET /api/sectors/{date}` | 板块热力数据 |
| `GET /api/signals/{date}?strategy=ALL` | 信号池，支持按策略筛选 |

### 前端

- 单文件 `index.html`，CSS/JS 全部内联，无需构建工具
- Apple 黑色风格：`#000` / `#1c1c1e` / `#2c2c2e`，SF Pro 字体
- 布局：左侧固定栏（指数 + 情绪 + 板块热力）+ 右侧主区（策略 Tab + 信号表格）
- Tab 切换在前端过滤已加载数据，不重新请求

### 启动方式

```bash
python main.py               # 一键：更新 → 计算 → 启动服务
python -m data.updater       # 只更新今日数据
python -m engine.runner      # 只跑策略
uvicorn web.app:app --port 8080  # 只启动 Web
```

---

## 数据范围与扩展性

**当前覆盖**：2021-01-04 至 2026-05-08，共 1292 个交易日

扩展更早数据的步骤：
1. 用 Tushare API 拉取目标年份数据，放入 `tushare/{year}/` 目录
2. 运行 `migrate.py` 增量导入 DuckDB（主键去重，不重复）
3. 修改 `backtest.py` 的 `start_date` 参数即可

---

## 技术选型

| 层 | 技术 | 理由 |
|----|------|------|
| 数据库 | DuckDB | 分析查询快，本地单文件，无服务端 |
| 数据更新 | Tushare Pro API | 有 token，2000 积分，稳定 |
| 后端 | FastAPI | 轻量，自动生成 API 文档 |
| 前端 | 原生 JS + Fetch | 无构建工具，单文件维护简单 |
| Python 环境 | conda mxk_env | 已有 pandas、duckdb、tushare |
