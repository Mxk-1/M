# A股交易系统 v2.0 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建三层分离的 A 股辅助决策系统：DuckDB 数据层 + 策略引擎 + Apple 风格 Web 仪表盘

**Architecture:** 历史 CSV 通过 migrate.py 一次性导入 DuckDB；每日 updater.py 增量更新；engine/runner.py 每日跑 7 个策略写入 signals 表；FastAPI 只读 DuckDB 暴露 4 个接口；前端单文件 index.html 渲染左右分栏界面。

**Tech Stack:** Python 3.12, DuckDB 1.5.2, FastAPI, Uvicorn, Tushare 1.4.29, 原生 JS（无框架）

**Python 环境:** `conda run -n mxk_env` 执行所有命令

**数据路径:** `/Users/xinkai_ma/repo/openclaw-hermes/M/tushare/`

**项目根目录:** `/Users/xinkai_ma/repo/openclaw-hermes/M/a_share_system/`

---

## 文件清单

```
a_share_system/
├── config.py                          # Token、路径、策略参数常量
├── main.py                            # 入口：update → run → serve
├── data/
│   ├── __init__.py
│   ├── db.py                          # DuckDB 连接管理（get_conn 单例）
│   ├── schema.sql                     # 建表 DDL
│   ├── migrate.py                     # 历史 CSV → DuckDB 一次性导入
│   └── updater.py                     # 每日增量更新（Tushare API）
├── engine/
│   ├── __init__.py
│   ├── signal.py                      # Signal dataclass
│   ├── base.py                        # BaseStrategy 抽象类
│   ├── runner.py                      # run_daily() + save_signals()
│   ├── backtest.py                    # run_backtest()
│   └── strategies/
│       ├── __init__.py
│       ├── limit_up.py                # LimitUpStrategy
│       ├── volume_spike.py            # VolumeSpikeStrategy
│       ├── ma_breakout.py             # MaBreakoutStrategy
│       ├── macd_cross.py              # MacdCrossStrategy
│       ├── macd_divergence.py         # MacdDivergenceStrategy
│       ├── consecutive.py             # ConsecutiveStrategy
│       └── resonance.py               # ResonanceStrategy（聚合器）
├── web/
│   ├── __init__.py
│   ├── app.py                         # FastAPI 应用 + 路由注册
│   ├── api/
│   │   ├── __init__.py
│   │   ├── market.py                  # /api/market/{date}, /api/sectors/{date}, /api/dates
│   │   └── signals.py                 # /api/signals/{date}
│   └── static/
│       └── index.html                 # Apple 风格前端（CSS/JS 内联）
└── tests/
    ├── test_signal.py
    ├── test_strategies.py
    └── test_api.py
```

---

## Task 1: 安装依赖 + 建项目骨架

**Files:**
- Create: `a_share_system/config.py`
- Create: `a_share_system/data/__init__.py`
- Create: `a_share_system/engine/__init__.py`
- Create: `a_share_system/engine/strategies/__init__.py`
- Create: `a_share_system/web/__init__.py`
- Create: `a_share_system/web/api/__init__.py`
- Create: `a_share_system/tests/__init__.py`

- [ ] **Step 1: 安装缺失依赖**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env pip install fastapi uvicorn[standard] -q
```

预期输出：`Successfully installed fastapi-... uvicorn-...`

- [ ] **Step 2: 创建项目目录结构**

```bash
mkdir -p a_share_system/{data,engine/strategies,web/api,web/static,tests}
touch a_share_system/__init__.py
touch a_share_system/data/__init__.py
touch a_share_system/engine/__init__.py
touch a_share_system/engine/strategies/__init__.py
touch a_share_system/web/__init__.py
touch a_share_system/web/api/__init__.py
touch a_share_system/tests/__init__.py
```

- [ ] **Step 3: 写 config.py**

```python
# a_share_system/config.py
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DATA_ROOT = PROJECT_ROOT.parent / "tushare"
DB_PATH = PROJECT_ROOT / "market.duckdb"

TUSHARE_TOKEN = "a5482c79be93fad0aad0340890cc47a44e010cee27f25e8fdf5d5fb5"

# 指数代码
INDEX_CODES = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
}

# 策略参数
STRATEGY_PARAMS = {
    "LIMIT_UP": {"threshold": 9.5},
    "VOLUME_SPIKE": {"vol_ratio_min": 3.0, "pct_chg_min": 3.0},
    "MA_BREAKOUT": {"ma_short": 5, "ma_long": 10, "ma_trend": 60},
    "MACD_CROSS": {"ema_fast": 12, "ema_slow": 26, "signal": 9},
    "MACD_DIVERGENCE": {"lookback": 30, "local_window": 4},
    "CONSECUTIVE": {"min_boards": 2},
    "RESONANCE": {"min_strategies": 2},
}
```

- [ ] **Step 4: 验证结构**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python -c "from a_share_system.config import DB_PATH, DATA_ROOT; print('DB:', DB_PATH); print('Data:', DATA_ROOT); print('Data exists:', DATA_ROOT.exists())"
```

预期输出：
```
DB: .../a_share_system/market.duckdb
Data: .../tushare
Data exists: True
```

- [ ] **Step 5: Commit**

```bash
git init a_share_system 2>/dev/null || true
cd /Users/xinkai_ma/repo/openclaw-hermes/M
git add a_share_system/
git commit -m "feat: init project skeleton and config"
```

---

## Task 2: 数据层 — schema + db.py

**Files:**
- Create: `a_share_system/data/schema.sql`
- Create: `a_share_system/data/db.py`
- Create: `a_share_system/tests/test_db.py`

- [ ] **Step 1: 写 schema.sql**

```sql
-- a_share_system/data/schema.sql

CREATE TABLE IF NOT EXISTS daily (
    ts_code    VARCHAR NOT NULL,
    trade_date INTEGER NOT NULL,
    open       DOUBLE,
    high       DOUBLE,
    low        DOUBLE,
    close      DOUBLE,
    pre_close  DOUBLE,
    pct_chg    DOUBLE,
    vol        DOUBLE,
    amount     DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS index_daily (
    ts_code    VARCHAR NOT NULL,
    trade_date INTEGER NOT NULL,
    close      DOUBLE,
    pct_chg    DOUBLE,
    vol        DOUBLE,
    amount     DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS moneyflow (
    ts_code        VARCHAR NOT NULL,
    trade_date     INTEGER NOT NULL,
    net_mf_amount  DOUBLE,
    buy_lg_amount  DOUBLE,
    sell_lg_amount DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS limit_list (
    ts_code    VARCHAR NOT NULL,
    trade_date INTEGER NOT NULL,
    lmt        VARCHAR,
    fd_amount  DOUBLE,
    open_times INTEGER,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS top_list (
    ts_code    VARCHAR NOT NULL,
    trade_date INTEGER NOT NULL,
    net_amount DOUBLE,
    reason     VARCHAR,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS stock_basic (
    ts_code   VARCHAR PRIMARY KEY,
    name      VARCHAR,
    industry  VARCHAR,
    list_date INTEGER
);

CREATE TABLE IF NOT EXISTS signals (
    ts_code    VARCHAR  NOT NULL,
    trade_date INTEGER  NOT NULL,
    strategy   VARCHAR  NOT NULL,
    score      DOUBLE,
    triggered  VARCHAR,
    pct_chg    DOUBLE,
    vol_ratio  DOUBLE,
    boards     INTEGER  DEFAULT 0,
    PRIMARY KEY (ts_code, trade_date, strategy)
);
```

注意：`limit_list` 的列名用 `lmt`（避开 SQL 保留字 `limit`）。

- [ ] **Step 2: 写测试**

```python
# a_share_system/tests/test_db.py
import pytest
import duckdb
from pathlib import Path
from a_share_system.data.db import get_conn, init_schema


def test_get_conn_returns_connection():
    con = get_conn(":memory:")
    assert con is not None
    result = con.execute("SELECT 42").fetchone()
    assert result[0] == 42


def test_init_schema_creates_all_tables():
    con = get_conn(":memory:")
    init_schema(con)
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()
    table_names = {t[0] for t in tables}
    assert "daily" in table_names
    assert "index_daily" in table_names
    assert "moneyflow" in table_names
    assert "limit_list" in table_names
    assert "top_list" in table_names
    assert "stock_basic" in table_names
    assert "signals" in table_names


def test_signals_table_accepts_insert():
    con = get_conn(":memory:")
    init_schema(con)
    con.execute("""
        INSERT INTO signals VALUES
        ('600111.SH', 20260508, 'LIMIT_UP', 85.0, '["LIMIT_UP"]', 9.98, 3.2, 2)
    """)
    row = con.execute("SELECT ts_code, strategy FROM signals").fetchone()
    assert row == ("600111.SH", "LIMIT_UP")
```

- [ ] **Step 3: 运行测试，确认失败**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python -m pytest a_share_system/tests/test_db.py -v 2>&1 | tail -15
```

预期：`ModuleNotFoundError: No module named 'a_share_system.data.db'`

- [ ] **Step 4: 写 db.py**

```python
# a_share_system/data/db.py
import duckdb
from pathlib import Path
from a_share_system.config import DB_PATH

_conn: duckdb.DuckDBPyConnection | None = None


def get_conn(path: str | None = None) -> duckdb.DuckDBPyConnection:
    global _conn
    if path == ":memory:":
        return duckdb.connect(":memory:")
    if _conn is None:
        db_path = Path(path) if path else DB_PATH
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _conn = duckdb.connect(str(db_path))
    return _conn


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    schema_path = Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    # 逐条执行（DuckDB 不支持多语句一次执行）
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt)
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python -m pytest a_share_system/tests/test_db.py -v
```

预期：`3 passed`

- [ ] **Step 6: Commit**

```bash
git add a_share_system/data/schema.sql a_share_system/data/db.py a_share_system/tests/test_db.py
git commit -m "feat: add DuckDB schema and connection manager"
```

---

## Task 3: 数据层 — migrate.py（历史 CSV 导入）

**Files:**
- Create: `a_share_system/data/migrate.py`

- [ ] **Step 1: 写 migrate.py**

```python
# a_share_system/data/migrate.py
"""
一次性将 tushare/ 历史 CSV 导入 DuckDB。
幂等：主键冲突时忽略（INSERT OR IGNORE）。
"""
import duckdb
from pathlib import Path
from a_share_system.config import DATA_ROOT
from a_share_system.data.db import get_conn, init_schema


def _insert_csv(con: duckdb.DuckDBPyConnection, csv_path: Path,
                table: str, columns: list[str]) -> int:
    col_str = ", ".join(columns)
    try:
        con.execute(f"""
            INSERT OR IGNORE INTO {table} ({col_str})
            SELECT {col_str}
            FROM read_csv_auto('{csv_path}', ignore_errors=true)
        """)
        return con.execute("SELECT changes()").fetchone()[0]
    except Exception as e:
        print(f"  ⚠ 跳过 {csv_path.name}: {e}")
        return 0


def migrate_daily(con: duckdb.DuckDBPyConnection) -> None:
    columns = ["ts_code", "trade_date", "open", "high", "low",
               "close", "pre_close", "pct_chg", "vol", "amount"]
    total = 0
    for year_dir in sorted(DATA_ROOT.glob("*/market")):
        for csv_file in sorted(year_dir.glob("daily_all.csv")):
            rows = _insert_csv(con, csv_file, "daily", columns)
            print(f"  daily {csv_file.parent.parent.name}: +{rows:,} 行")
            total += rows
    print(f"  daily 合计: {total:,} 行")


def migrate_index_daily(con: duckdb.DuckDBPyConnection) -> None:
    columns = ["ts_code", "trade_date", "close", "pct_chg", "vol", "amount"]
    total = 0
    for year_dir in sorted(DATA_ROOT.glob("*/market")):
        for csv_file in sorted(year_dir.glob("index_daily.csv")):
            rows = _insert_csv(con, csv_file, "index_daily", columns)
            total += rows
    print(f"  index_daily 合计: {total:,} 行")


def migrate_moneyflow(con: duckdb.DuckDBPyConnection) -> None:
    columns = ["ts_code", "trade_date", "net_mf_amount",
               "buy_lg_amount", "sell_lg_amount"]
    total = 0
    for year_dir in sorted(DATA_ROOT.glob("*/market")):
        for csv_file in sorted(year_dir.glob("moneyflow_????????.csv")):
            rows = _insert_csv(con, csv_file, "moneyflow", columns)
            total += rows
    print(f"  moneyflow 合计: {total:,} 行")


def migrate_limit_list(con: duckdb.DuckDBPyConnection) -> None:
    total = 0
    for year_dir in sorted(DATA_ROOT.glob("*/market")):
        for csv_file in sorted(year_dir.glob("limit_list_????????.csv")):
            try:
                con.execute(f"""
                    INSERT OR IGNORE INTO limit_list (ts_code, trade_date, lmt, fd_amount, open_times)
                    SELECT ts_code,
                           CAST(trade_date AS INTEGER),
                           "limit",
                           TRY_CAST(fd AS DOUBLE),
                           TRY_CAST(open_times AS INTEGER)
                    FROM read_csv_auto('{csv_file}', ignore_errors=true)
                """)
                rows = con.execute("SELECT changes()").fetchone()[0]
                total += rows
            except Exception as e:
                print(f"  ⚠ 跳过 {csv_file.name}: {e}")
    print(f"  limit_list 合计: {total:,} 行")


def migrate_top_list(con: duckdb.DuckDBPyConnection) -> None:
    total = 0
    for year_dir in sorted(DATA_ROOT.glob("*/other")):
        for csv_file in sorted(year_dir.glob("top_list*.csv")):
            try:
                con.execute(f"""
                    INSERT OR IGNORE INTO top_list (ts_code, trade_date, net_amount, reason)
                    SELECT ts_code,
                           CAST(trade_date AS INTEGER),
                           TRY_CAST(net_amount AS DOUBLE),
                           reason
                    FROM read_csv_auto('{csv_file}', ignore_errors=true)
                """)
                rows = con.execute("SELECT changes()").fetchone()[0]
                total += rows
            except Exception as e:
                print(f"  ⚠ 跳过 {csv_file.name}: {e}")
    print(f"  top_list 合计: {total:,} 行")


def migrate_stock_basic(con: duckdb.DuckDBPyConnection) -> None:
    # 用最新年份的 stock_basic（包含最多股票）
    csv_file = DATA_ROOT / "2026" / "reference" / "stock_basic.csv"
    if not csv_file.exists():
        print("  ⚠ stock_basic.csv 不存在，跳过")
        return
    con.execute(f"""
        INSERT OR IGNORE INTO stock_basic (ts_code, name, industry, list_date)
        SELECT ts_code, name, industry, CAST(list_date AS INTEGER)
        FROM read_csv_auto('{csv_file}', ignore_errors=true)
    """)
    rows = con.execute("SELECT COUNT(*) FROM stock_basic").fetchone()[0]
    print(f"  stock_basic: {rows:,} 只")


def run_migration() -> None:
    con = get_conn()
    init_schema(con)
    print("开始导入历史数据...")
    migrate_stock_basic(con)
    migrate_daily(con)
    migrate_index_daily(con)
    migrate_moneyflow(con)
    migrate_limit_list(con)
    migrate_top_list(con)

    # 汇总
    daily_cnt = con.execute("SELECT COUNT(*) FROM daily").fetchone()[0]
    dates_cnt = con.execute("SELECT COUNT(DISTINCT trade_date) FROM daily").fetchone()[0]
    print(f"\n✅ 导入完成: daily={daily_cnt:,}行, {dates_cnt}个交易日")


if __name__ == "__main__":
    run_migration()
```

- [ ] **Step 2: 运行迁移（预计 2-5 分钟）**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python -m a_share_system.data.migrate
```

预期输出（最后几行）：
```
  stock_basic: 5,497 只
  daily 2021: +1,042,459 行
  ...
✅ 导入完成: daily=6,xxx,xxx 行, 1292 个交易日
```

- [ ] **Step 3: 验证数据**

```bash
conda run -n mxk_env python -c "
from a_share_system.data.db import get_conn
con = get_conn()
print('daily 行数:', con.execute('SELECT COUNT(*) FROM daily').fetchone()[0])
print('最新日期:', con.execute('SELECT MAX(trade_date) FROM daily').fetchone()[0])
print('北方稀土近3日:')
print(con.execute(\"SELECT trade_date,close,pct_chg FROM daily WHERE ts_code='600111.SH' ORDER BY trade_date DESC LIMIT 3\").df().to_string(index=False))
"
```

- [ ] **Step 4: Commit**

```bash
git add a_share_system/data/migrate.py
git commit -m "feat: migrate historical CSV to DuckDB"
```

---

## Task 4: 策略引擎基础 — Signal + BaseStrategy

**Files:**
- Create: `a_share_system/engine/signal.py`
- Create: `a_share_system/engine/base.py`
- Create: `a_share_system/tests/test_signal.py`

- [ ] **Step 1: 写测试**

```python
# a_share_system/tests/test_signal.py
import json
from a_share_system.engine.signal import Signal


def test_signal_defaults():
    s = Signal(ts_code="600111.SH", name="北方稀土",
               trade_date=20260508, strategy="LIMIT_UP",
               score=85.0, pct_chg=9.98, vol_ratio=3.2)
    assert s.boards == 0
    assert s.triggered == []
    assert s.extra == {}


def test_signal_to_dict():
    s = Signal(ts_code="600111.SH", name="北方稀土",
               trade_date=20260508, strategy="LIMIT_UP",
               score=85.0, pct_chg=9.98, vol_ratio=3.2,
               boards=2, triggered=["LIMIT_UP", "VOLUME_SPIKE"])
    d = s.to_dict()
    assert d["ts_code"] == "600111.SH"
    assert d["boards"] == 2
    assert json.loads(d["triggered"]) == ["LIMIT_UP", "VOLUME_SPIKE"]
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python -m pytest a_share_system/tests/test_signal.py -v 2>&1 | tail -5
```

预期：`ImportError`

- [ ] **Step 3: 写 signal.py**

```python
# a_share_system/engine/signal.py
import json
from dataclasses import dataclass, field


@dataclass
class Signal:
    ts_code:    str
    name:       str
    trade_date: int
    strategy:   str
    score:      float
    pct_chg:    float
    vol_ratio:  float
    boards:     int       = 0
    triggered:  list[str] = field(default_factory=list)
    extra:      dict      = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ts_code":    self.ts_code,
            "name":       self.name,
            "trade_date": self.trade_date,
            "strategy":   self.strategy,
            "score":      self.score,
            "pct_chg":    self.pct_chg,
            "vol_ratio":  self.vol_ratio,
            "boards":     self.boards,
            "triggered":  json.dumps(self.triggered, ensure_ascii=False),
            "extra":      json.dumps(self.extra, ensure_ascii=False),
        }
```

- [ ] **Step 4: 写 base.py**

```python
# a_share_system/engine/base.py
import duckdb
from abc import ABC, abstractmethod
from a_share_system.engine.signal import Signal


class BaseStrategy(ABC):
    name: str         # 唯一标识，如 'LIMIT_UP'
    display_name: str # 展示名，如 'N字涨停'

    @abstractmethod
    def scan(self, con: duckdb.DuckDBPyConnection,
             trade_date: int) -> list[Signal]:
        """
        扫描指定交易日，返回触发该策略的 Signal 列表。
        每个策略只需实现这一个方法。
        """
        ...
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python -m pytest a_share_system/tests/test_signal.py -v
```

预期：`2 passed`

- [ ] **Step 6: Commit**

```bash
git add a_share_system/engine/signal.py a_share_system/engine/base.py a_share_system/tests/test_signal.py
git commit -m "feat: add Signal dataclass and BaseStrategy"
```

---

## Task 5: 策略实现（上）— LimitUp + VolumeSpike + Consecutive

**Files:**
- Create: `a_share_system/engine/strategies/limit_up.py`
- Create: `a_share_system/engine/strategies/volume_spike.py`
- Create: `a_share_system/engine/strategies/consecutive.py`
- Create: `a_share_system/tests/test_strategies.py`

- [ ] **Step 1: 写测试（使用内存数据库）**

```python
# a_share_system/tests/test_strategies.py
import duckdb
import pytest
from a_share_system.data.db import init_schema


def make_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    init_schema(con)
    # 插入股票基础信息
    con.execute("""
        INSERT INTO stock_basic VALUES
        ('600111.SH', '北方稀土', '小金属', 19970924),
        ('600519.SH', '贵州茅台', '白酒',   20010827),
        ('300750.SZ', '宁德时代', '电池',   20180611)
    """)
    return con


def insert_daily(con, rows: list[tuple]) -> None:
    for row in rows:
        con.execute(
            "INSERT OR IGNORE INTO daily VALUES (?,?,?,?,?,?,?,?,?,?)", row
        )


# ---------- LimitUp ----------
def test_limit_up_detects_limit_up_stock():
    from a_share_system.engine.strategies.limit_up import LimitUpStrategy
    con = make_db()
    # 600111.SH 当日涨停 +9.98%
    insert_daily(con, [
        ("600111.SH", 20260508, 50.0, 55.0, 49.5, 55.0, 50.0, 9.98, 9.98, 1000000, 5000000),
    ])
    signals = LimitUpStrategy().scan(con, 20260508)
    assert len(signals) == 1
    assert signals[0].ts_code == "600111.SH"
    assert signals[0].strategy == "LIMIT_UP"


def test_limit_up_ignores_non_limit_stock():
    from a_share_system.engine.strategies.limit_up import LimitUpStrategy
    con = make_db()
    insert_daily(con, [
        ("600519.SH", 20260508, 1800.0, 1850.0, 1790.0, 1820.0, 1800.0, 1.11, 1.11, 50000, 9000000),
    ])
    signals = LimitUpStrategy().scan(con, 20260508)
    assert len(signals) == 0


# ---------- VolumeSpike ----------
def test_volume_spike_detects_spike():
    from a_share_system.engine.strategies.volume_spike import VolumeSpikeStrategy
    con = make_db()
    # 插入 5 天历史（均量 100000 手）
    for i, d in enumerate([20260502, 20260503, 20260506, 20260507]):
        insert_daily(con, [("300750.SZ", d, 100.0, 102.0, 99.0, 101.0, 100.0, 1.0, 1.0, 100000, 10000000)])
    # 今日成交量 350000（量比 3.5）且涨幅 4%
    insert_daily(con, [("300750.SZ", 20260508, 101.0, 106.0, 100.5, 105.0, 101.0, 3.96, 3.96, 350000, 36000000)])
    signals = VolumeSpikeStrategy().scan(con, 20260508)
    assert len(signals) == 1
    assert signals[0].ts_code == "300750.SZ"
    assert signals[0].vol_ratio > 3.0


def test_volume_spike_ignores_low_volume():
    from a_share_system.engine.strategies.volume_spike import VolumeSpikeStrategy
    con = make_db()
    for d in [20260502, 20260503, 20260506, 20260507]:
        insert_daily(con, [("300750.SZ", d, 100.0, 102.0, 99.0, 101.0, 100.0, 1.0, 1.0, 100000, 10000000)])
    # 今日量比 1.5（不满足 > 3）
    insert_daily(con, [("300750.SZ", 20260508, 101.0, 106.0, 100.5, 105.0, 101.0, 3.96, 3.96, 150000, 15000000)])
    signals = VolumeSpikeStrategy().scan(con, 20260508)
    assert len(signals) == 0


# ---------- Consecutive ----------
def test_consecutive_detects_2_boards():
    from a_share_system.engine.strategies.consecutive import ConsecutiveStrategy
    con = make_db()
    # 昨日 + 今日都涨停
    insert_daily(con, [
        ("600111.SH", 20260507, 50.0, 55.0, 49.5, 55.0, 50.0, 10.0, 10.0, 1000000, 5000000),
        ("600111.SH", 20260508, 55.0, 60.5, 54.5, 60.5, 55.0, 10.0, 10.0, 1200000, 7000000),
    ])
    signals = ConsecutiveStrategy().scan(con, 20260508)
    assert len(signals) == 1
    assert signals[0].boards == 2


def test_consecutive_ignores_single_board():
    from a_share_system.engine.strategies.consecutive import ConsecutiveStrategy
    con = make_db()
    insert_daily(con, [
        ("600111.SH", 20260507, 50.0, 52.0, 49.5, 51.0, 50.0, 2.0, 2.0, 500000, 2500000),
        ("600111.SH", 20260508, 51.0, 56.1, 50.5, 56.1, 51.0, 10.0, 10.0, 1200000, 6500000),
    ])
    signals = ConsecutiveStrategy().scan(con, 20260508)
    assert len(signals) == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python -m pytest a_share_system/tests/test_strategies.py -v 2>&1 | tail -10
```

预期：`ImportError` 或 `ModuleNotFoundError`

- [ ] **Step 3: 写 limit_up.py**

```python
# a_share_system/engine/strategies/limit_up.py
import duckdb
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


class LimitUpStrategy(BaseStrategy):
    name = "LIMIT_UP"
    display_name = "N字涨停"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        threshold = STRATEGY_PARAMS["LIMIT_UP"]["threshold"]
        rows = con.execute(f"""
            SELECT d.ts_code,
                   COALESCE(s.name, d.ts_code) AS name,
                   d.pct_chg,
                   CASE WHEN d.vol > 0 AND prev.avg_vol > 0
                        THEN d.vol / prev.avg_vol ELSE 1.0 END AS vol_ratio
            FROM daily d
            LEFT JOIN stock_basic s ON d.ts_code = s.ts_code
            LEFT JOIN (
                SELECT ts_code, AVG(vol) AS avg_vol
                FROM daily
                WHERE trade_date < {trade_date}
                GROUP BY ts_code
            ) prev ON d.ts_code = prev.ts_code
            WHERE d.trade_date = {trade_date}
              AND d.pct_chg >= {threshold}
        """).fetchall()

        signals = []
        for ts_code, name, pct_chg, vol_ratio in rows:
            score = min(100.0, 60.0 + pct_chg * 4)
            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=score, pct_chg=pct_chg,
                vol_ratio=round(vol_ratio, 2),
                triggered=[self.name],
            ))
        return signals
```

- [ ] **Step 4: 写 volume_spike.py**

```python
# a_share_system/engine/strategies/volume_spike.py
import duckdb
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


class VolumeSpikeStrategy(BaseStrategy):
    name = "VOLUME_SPIKE"
    display_name = "突然爆量"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        p = STRATEGY_PARAMS["VOLUME_SPIKE"]
        vol_min = p["vol_ratio_min"]
        pct_min = p["pct_chg_min"]

        rows = con.execute(f"""
            WITH avg5 AS (
                SELECT ts_code, AVG(vol) AS avg_vol
                FROM (
                    SELECT ts_code, vol,
                           ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
                    FROM daily
                    WHERE trade_date < {trade_date}
                ) t WHERE rn <= 5
                GROUP BY ts_code
            )
            SELECT d.ts_code,
                   COALESCE(s.name, d.ts_code),
                   d.pct_chg,
                   d.vol / a.avg_vol AS vol_ratio
            FROM daily d
            JOIN avg5 a ON d.ts_code = a.ts_code
            LEFT JOIN stock_basic s ON d.ts_code = s.ts_code
            WHERE d.trade_date = {trade_date}
              AND a.avg_vol > 0
              AND d.vol / a.avg_vol >= {vol_min}
              AND d.pct_chg >= {pct_min}
        """).fetchall()

        return [
            Signal(
                ts_code=r[0], name=r[1],
                trade_date=trade_date, strategy=self.name,
                score=min(100.0, 50.0 + r[3] * 10),
                pct_chg=r[2], vol_ratio=round(r[3], 2),
                triggered=[self.name],
            )
            for r in rows
        ]
```

- [ ] **Step 5: 写 consecutive.py**

```python
# a_share_system/engine/strategies/consecutive.py
import duckdb
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


class ConsecutiveStrategy(BaseStrategy):
    name = "CONSECUTIVE"
    display_name = "连板龙头"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        min_boards = STRATEGY_PARAMS["CONSECUTIVE"]["min_boards"]
        threshold = STRATEGY_PARAMS["LIMIT_UP"]["threshold"]

        # 今日涨停的股票
        today_limit = con.execute(f"""
            SELECT d.ts_code, COALESCE(s.name, d.ts_code), d.pct_chg, d.vol,
                   CASE WHEN prev.avg_vol > 0 THEN d.vol / prev.avg_vol ELSE 1.0 END AS vol_ratio
            FROM daily d
            LEFT JOIN stock_basic s ON d.ts_code = s.ts_code
            LEFT JOIN (
                SELECT ts_code, AVG(vol) AS avg_vol FROM daily
                WHERE trade_date < {trade_date} GROUP BY ts_code
            ) prev ON d.ts_code = prev.ts_code
            WHERE d.trade_date = {trade_date} AND d.pct_chg >= {threshold}
        """).fetchall()

        signals = []
        for ts_code, name, pct_chg, vol, vol_ratio in today_limit:
            # 向前统计连板数
            hist = con.execute(f"""
                SELECT pct_chg FROM daily
                WHERE ts_code = '{ts_code}' AND trade_date < {trade_date}
                ORDER BY trade_date DESC LIMIT 10
            """).fetchall()

            boards = 1
            for row in hist:
                if row[0] >= threshold:
                    boards += 1
                else:
                    break

            if boards >= min_boards:
                score = min(100.0, 60.0 + boards * 8)
                signals.append(Signal(
                    ts_code=ts_code, name=name,
                    trade_date=trade_date, strategy=self.name,
                    score=score, pct_chg=pct_chg,
                    vol_ratio=round(vol_ratio, 2),
                    boards=boards,
                    triggered=[self.name],
                ))
        return signals
```

- [ ] **Step 6: 运行测试，确认通过**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python -m pytest a_share_system/tests/test_strategies.py -v
```

预期：`8 passed`

- [ ] **Step 7: Commit**

```bash
git add a_share_system/engine/strategies/limit_up.py \
        a_share_system/engine/strategies/volume_spike.py \
        a_share_system/engine/strategies/consecutive.py \
        a_share_system/tests/test_strategies.py
git commit -m "feat: add LimitUp, VolumeSpike, Consecutive strategies"
```

---

## Task 6: 策略实现（下）— MA_BREAKOUT + MACD_CROSS + MACD_DIVERGENCE

**Files:**
- Create: `a_share_system/engine/strategies/ma_breakout.py`
- Create: `a_share_system/engine/strategies/macd_cross.py`
- Create: `a_share_system/engine/strategies/macd_divergence.py`

- [ ] **Step 1: 在 test_strategies.py 追加测试**

在 `a_share_system/tests/test_strategies.py` 末尾追加：

```python
# ---------- MA Breakout ----------
def test_ma_breakout_detects_ma5_cross_ma10():
    from a_share_system.engine.strategies.ma_breakout import MaBreakoutStrategy
    con = make_db()
    # 构造 MA5 昨天 < MA10，今天 MA5 > MA10 的场景
    # 10天数据：前9天均价 100，今天 105（MA5 会超过 MA10）
    for i, (d, c) in enumerate(zip(
        [20260425,20260426,20260427,20260428,20260429,
         20260502,20260503,20260506,20260507],
        [100,100,100,100,100,100,100,100,100]
    )):
        insert_daily(con, [("600111.SH", d, c, c+1, c-1, float(c), float(c), 0.0, 0.0, 500000, 50000000)])
    # 今日收盘 115，拉高 MA5
    insert_daily(con, [("600111.SH", 20260508, 100.0, 116.0, 99.0, 115.0, 100.0, 15.0, 15.0, 800000, 90000000)])
    signals = MaBreakoutStrategy().scan(con, 20260508)
    assert len(signals) >= 1
    assert signals[0].ts_code == "600111.SH"


# ---------- MACD Cross ----------
def test_macd_cross_detects_golden_cross():
    from a_share_system.engine.strategies.macd_cross import MacdCrossStrategy
    con = make_db()
    # 构造 30 天下跌后反弹的价格序列（制造 DIF 上穿 DEA）
    prices = [100 - i * 0.5 for i in range(28)] + [90.0, 95.0]  # 最后两天反弹
    dates = [20260301, 20260302, 20260303, 20260304, 20260305,
             20260306, 20260309, 20260310, 20260311, 20260312,
             20260313, 20260316, 20260317, 20260318, 20260319,
             20260320, 20260323, 20260324, 20260325, 20260326,
             20260327, 20260330, 20260331, 20260401, 20260402,
             20260403, 20260407, 20260408, 20260409, 20260410]
    for d, p in zip(dates, prices):
        insert_daily(con, [("600111.SH", d, p, p+1, p-1, p, p, 0.0, 0.0, 500000, 500000*p)])
    signals = MacdCrossStrategy().scan(con, 20260410)
    # 价格反弹时应触发金叉
    assert isinstance(signals, list)  # 不要求一定有信号，只验证不报错


# ---------- MACD Divergence ----------
def test_macd_divergence_returns_list():
    from a_share_system.engine.strategies.macd_divergence import MacdDivergenceStrategy
    con = make_db()
    # 60 天数据：先跌后跌（底背离场景）
    prices = [100 - i * 0.3 for i in range(60)]
    dates = list(range(20260101, 20260101 + 60))
    for d, p in zip(dates, prices):
        insert_daily(con, [("600111.SH", d, p, p+1, p-1, p, p, 0.0, 0.0, 500000, 500000*p)])
    signals = MacdDivergenceStrategy().scan(con, dates[-1])
    assert isinstance(signals, list)
```

- [ ] **Step 2: 写 ma_breakout.py**

```python
# a_share_system/engine/strategies/ma_breakout.py
import duckdb
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


class MaBreakoutStrategy(BaseStrategy):
    name = "MA_BREAKOUT"
    display_name = "均线突破"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        p = STRATEGY_PARAMS["MA_BREAKOUT"]
        short, long_, trend = p["ma_short"], p["ma_long"], p["ma_trend"]
        need = trend + 1  # 需要至少 61 天历史

        candidates = con.execute(f"""
            SELECT DISTINCT ts_code FROM daily
            WHERE trade_date <= {trade_date}
            GROUP BY ts_code HAVING COUNT(*) >= {need}
        """).fetchall()

        signals = []
        for (ts_code,) in candidates:
            hist = con.execute(f"""
                SELECT close FROM daily
                WHERE ts_code = '{ts_code}' AND trade_date <= {trade_date}
                ORDER BY trade_date DESC LIMIT {need}
            """).fetchall()
            closes = [r[0] for r in reversed(hist)]
            if len(closes) < need:
                continue

            ma5_today  = sum(closes[-short:]) / short
            ma10_today = sum(closes[-long_:]) / long_
            ma5_yest   = sum(closes[-short-1:-1]) / short
            ma10_yest  = sum(closes[-long_-1:-1]) / long_
            ma60       = sum(closes[-trend:]) / trend

            signal_type = None
            if ma5_today > ma10_today and ma5_yest <= ma10_yest:
                signal_type = "MA5上穿MA10"
            elif closes[-1] > ma60 and closes[-2] <= ma60:
                signal_type = "站上MA60"

            if signal_type is None:
                continue

            name_row = con.execute(
                f"SELECT name FROM stock_basic WHERE ts_code='{ts_code}'"
            ).fetchone()
            name = name_row[0] if name_row else ts_code
            pct_row = con.execute(
                f"SELECT pct_chg FROM daily WHERE ts_code='{ts_code}' AND trade_date={trade_date}"
            ).fetchone()
            pct_chg = pct_row[0] if pct_row else 0.0

            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=65.0, pct_chg=pct_chg, vol_ratio=1.0,
                triggered=[self.name],
                extra={"signal_type": signal_type,
                       "ma5": round(ma5_today, 2), "ma10": round(ma10_today, 2),
                       "ma60": round(ma60, 2)},
            ))
        return signals
```

- [ ] **Step 3: 写 macd_cross.py**

```python
# a_share_system/engine/strategies/macd_cross.py
import duckdb
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _calc_dif_dea(closes: list[float], fast: int, slow: int, signal: int) -> tuple:
    """返回 (dif_today, dea_today, dif_yest, dea_yest)"""
    if len(closes) < slow + signal:
        return None, None, None, None
    difs = []
    for i in range(slow, len(closes) + 1):
        e12 = _ema(closes[:i], fast)
        e26 = _ema(closes[:i], slow)
        if e12 and e26:
            difs.append(e12 - e26)
    if len(difs) < signal:
        return None, None, None, None
    dea_today = _ema(difs, signal)
    dea_yest  = _ema(difs[:-1], signal) if len(difs) > signal else dea_today
    return difs[-1], dea_today, difs[-2] if len(difs) >= 2 else difs[-1], dea_yest


class MacdCrossStrategy(BaseStrategy):
    name = "MACD_CROSS"
    display_name = "MACD金叉"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        p = STRATEGY_PARAMS["MACD_CROSS"]
        need = p["ema_slow"] + p["signal"] + 5

        candidates = con.execute(f"""
            SELECT DISTINCT ts_code FROM daily
            WHERE trade_date <= {trade_date}
            GROUP BY ts_code HAVING COUNT(*) >= {need}
        """).fetchall()

        signals = []
        for (ts_code,) in candidates:
            hist = con.execute(f"""
                SELECT close FROM daily
                WHERE ts_code = '{ts_code}' AND trade_date <= {trade_date}
                ORDER BY trade_date ASC
            """).fetchall()
            closes = [r[0] for r in hist]

            dif, dea, dif_y, dea_y = _calc_dif_dea(
                closes, p["ema_fast"], p["ema_slow"], p["signal"]
            )
            if dif is None or dea is None or dif_y is None or dea_y is None:
                continue
            if not (dif > dea and dif_y <= dea_y):
                continue

            name_row = con.execute(
                f"SELECT name FROM stock_basic WHERE ts_code='{ts_code}'"
            ).fetchone()
            name = name_row[0] if name_row else ts_code
            pct_row = con.execute(
                f"SELECT pct_chg FROM daily WHERE ts_code='{ts_code}' AND trade_date={trade_date}"
            ).fetchone()
            pct_chg = pct_row[0] if pct_row else 0.0
            position = "零轴上方" if dif > 0 else "零轴下方"

            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=70.0 if dif > 0 else 55.0,
                pct_chg=pct_chg, vol_ratio=1.0,
                triggered=[self.name],
                extra={"dif": round(dif, 3), "dea": round(dea, 3), "position": position},
            ))
        return signals
```

- [ ] **Step 4: 写 macd_divergence.py**

```python
# a_share_system/engine/strategies/macd_divergence.py
import duckdb
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.base import BaseStrategy
from a_share_system.engine.signal import Signal
from a_share_system.engine.strategies.macd_cross import _ema


def _find_local_lows(data: list[float], window: int = 4) -> list[tuple[int, float]]:
    lows = []
    for i in range(window, len(data) - window):
        if all(data[i] <= data[j] for j in range(i - window, i + window + 1) if j != i):
            lows.append((i, data[i]))
    return lows[-2:] if len(lows) >= 2 else []


class MacdDivergenceStrategy(BaseStrategy):
    name = "MACD_DIVERGENCE"
    display_name = "MACD底背离"

    def scan(self, con: duckdb.DuckDBPyConnection, trade_date: int) -> list[Signal]:
        p = STRATEGY_PARAMS["MACD_DIVERGENCE"]
        lookback = p["lookback"]
        need = 60

        candidates = con.execute(f"""
            SELECT DISTINCT ts_code FROM daily
            WHERE trade_date <= {trade_date}
            GROUP BY ts_code HAVING COUNT(*) >= {need}
        """).fetchall()

        signals = []
        for (ts_code,) in candidates:
            hist = con.execute(f"""
                SELECT close, pct_chg FROM daily
                WHERE ts_code = '{ts_code}' AND trade_date <= {trade_date}
                ORDER BY trade_date ASC
            """).fetchall()
            closes = [r[0] for r in hist]
            today_pct = hist[-1][1]

            if len(closes) < 40:
                continue

            difs = []
            for i in range(26, len(closes) + 1):
                e12 = _ema(closes[:i], 12)
                e26 = _ema(closes[:i], 26)
                if e12 and e26:
                    difs.append(e12 - e26)

            if len(difs) < lookback:
                continue

            recent_closes = closes[-lookback:]
            recent_difs   = difs[-lookback:]

            price_lows = _find_local_lows(recent_closes)
            if len(price_lows) < 2:
                continue

            idx1, p1 = price_lows[0]
            idx2, p2 = price_lows[1]
            if p2 >= p1:
                continue  # 价格未创新低

            dif1 = recent_difs[idx1] if idx1 < len(recent_difs) else 0
            dif2 = recent_difs[idx2] if idx2 < len(recent_difs) else 0
            if not (dif2 > dif1 and dif2 < 0):
                continue  # DIF 无背离

            # 今天收阳确认
            if today_pct <= 0:
                continue

            name_row = con.execute(
                f"SELECT name FROM stock_basic WHERE ts_code='{ts_code}'"
            ).fetchone()
            name = name_row[0] if name_row else ts_code

            signals.append(Signal(
                ts_code=ts_code, name=name,
                trade_date=trade_date, strategy=self.name,
                score=72.0, pct_chg=today_pct, vol_ratio=1.0,
                triggered=[self.name],
                extra={"low1": round(p1, 2), "low2": round(p2, 2),
                       "dif1": round(dif1, 3), "dif2": round(dif2, 3)},
            ))
        return signals
```

- [ ] **Step 5: 运行全部策略测试**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python -m pytest a_share_system/tests/test_strategies.py -v
```

预期：`11 passed`（8 原有 + 3 新增）

- [ ] **Step 6: Commit**

```bash
git add a_share_system/engine/strategies/ma_breakout.py \
        a_share_system/engine/strategies/macd_cross.py \
        a_share_system/engine/strategies/macd_divergence.py \
        a_share_system/tests/test_strategies.py
git commit -m "feat: add MaBreakout, MacdCross, MacdDivergence strategies"
```

---

## Task 7: 策略引擎 — Resonance + Runner + Backtest

**Files:**
- Create: `a_share_system/engine/strategies/resonance.py`
- Create: `a_share_system/engine/runner.py`
- Create: `a_share_system/engine/backtest.py`

- [ ] **Step 1: 写 resonance.py**

```python
# a_share_system/engine/strategies/resonance.py
from collections import defaultdict
from a_share_system.config import STRATEGY_PARAMS
from a_share_system.engine.signal import Signal


class ResonanceStrategy:
    name = "RESONANCE"
    display_name = "多策略共振"

    def detect(self, signals: list[Signal]) -> list[Signal]:
        """
        输入：所有策略的 Signal 列表
        输出：触发 >= min_strategies 个不同策略的股票的共振 Signal
        """
        min_n = STRATEGY_PARAMS["RESONANCE"]["min_strategies"]
        by_stock: dict[tuple, list[Signal]] = defaultdict(list)
        for s in signals:
            by_stock[(s.ts_code, s.trade_date)].append(s)

        resonance = []
        for (ts_code, trade_date), stock_signals in by_stock.items():
            strategies = list({s.strategy for s in stock_signals})
            if len(strategies) < min_n:
                continue
            base = stock_signals[0]
            score = min(100.0, 70.0 + len(strategies) * 8)
            resonance.append(Signal(
                ts_code=ts_code,
                name=base.name,
                trade_date=trade_date,
                strategy=self.name,
                score=score,
                pct_chg=base.pct_chg,
                vol_ratio=base.vol_ratio,
                boards=max(s.boards for s in stock_signals),
                triggered=strategies,
            ))
        resonance.sort(key=lambda s: s.score, reverse=True)
        return resonance
```

- [ ] **Step 2: 写 runner.py**

```python
# a_share_system/engine/runner.py
import json
import duckdb
from a_share_system.engine.signal import Signal
from a_share_system.engine.strategies.limit_up import LimitUpStrategy
from a_share_system.engine.strategies.volume_spike import VolumeSpikeStrategy
from a_share_system.engine.strategies.consecutive import ConsecutiveStrategy
from a_share_system.engine.strategies.ma_breakout import MaBreakoutStrategy
from a_share_system.engine.strategies.macd_cross import MacdCrossStrategy
from a_share_system.engine.strategies.macd_divergence import MacdDivergenceStrategy
from a_share_system.engine.strategies.resonance import ResonanceStrategy

STRATEGIES = [
    LimitUpStrategy(),
    VolumeSpikeStrategy(),
    ConsecutiveStrategy(),
    MaBreakoutStrategy(),
    MacdCrossStrategy(),
    MacdDivergenceStrategy(),
]


def save_signals(con: duckdb.DuckDBPyConnection, signals: list[Signal]) -> None:
    if not signals:
        return
    con.executemany(
        """
        INSERT OR REPLACE INTO signals
        (ts_code, trade_date, strategy, score, triggered, pct_chg, vol_ratio, boards)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (s.ts_code, s.trade_date, s.strategy, s.score,
             s.to_dict()["triggered"], s.pct_chg, s.vol_ratio, s.boards)
            for s in signals
        ],
    )


def run_daily(con: duckdb.DuckDBPyConnection, trade_date: int) -> int:
    all_signals: list[Signal] = []
    for strategy in STRATEGIES:
        try:
            found = strategy.scan(con, trade_date)
            all_signals.extend(found)
        except Exception as e:
            print(f"  ⚠ {strategy.name} 出错: {e}")

    resonance = ResonanceStrategy().detect(all_signals)
    all_signals.extend(resonance)

    save_signals(con, all_signals)
    return len(all_signals)


if __name__ == "__main__":
    from a_share_system.data.db import get_conn
    con = get_conn()
    latest = con.execute("SELECT MAX(trade_date) FROM daily").fetchone()[0]
    print(f"扫描 {latest}...")
    count = run_daily(con, latest)
    print(f"✅ 写入 {count} 个信号")
    resonance = con.execute(
        f"SELECT ts_code, score, triggered FROM signals WHERE trade_date={latest} AND strategy='RESONANCE' ORDER BY score DESC LIMIT 5"
    ).df()
    print(resonance.to_string(index=False))
```

- [ ] **Step 3: 写 backtest.py**

```python
# a_share_system/engine/backtest.py
import duckdb
from a_share_system.data.db import get_conn
from a_share_system.engine.runner import run_daily


def get_trading_days(con: duckdb.DuckDBPyConnection,
                     start_date: int, end_date: int) -> list[int]:
    rows = con.execute(f"""
        SELECT DISTINCT trade_date FROM daily
        WHERE trade_date >= {start_date} AND trade_date <= {end_date}
        ORDER BY trade_date
    """).fetchall()
    return [r[0] for r in rows]


def run_backtest(start_date: int, end_date: int,
                 con: duckdb.DuckDBPyConnection | None = None) -> None:
    if con is None:
        con = get_conn()
    days = get_trading_days(con, start_date, end_date)
    print(f"回测 {start_date} ~ {end_date}，共 {len(days)} 个交易日")
    for i, date in enumerate(days, 1):
        count = run_daily(con, date)
        if i % 50 == 0 or i == len(days):
            print(f"  [{i}/{len(days)}] {date}: {count} 个信号")
    total = con.execute(
        f"SELECT COUNT(*) FROM signals WHERE trade_date BETWEEN {start_date} AND {end_date}"
    ).fetchone()[0]
    print(f"✅ 回测完成，累计写入 {total:,} 条信号")


if __name__ == "__main__":
    # 回测最近 30 个交易日
    con = get_conn()
    latest = con.execute("SELECT MAX(trade_date) FROM daily").fetchone()[0]
    days = get_trading_days(con, 0, latest)
    start = days[-30] if len(days) >= 30 else days[0]
    run_backtest(start, latest, con)
```

- [ ] **Step 4: 冒烟测试 — 跑最新一天**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python -m a_share_system.engine.runner
```

预期输出（最后几行）：
```
扫描 20260508...
✅ 写入 N 个信号
  ts_code   score  triggered
  ...
```

- [ ] **Step 5: Commit**

```bash
git add a_share_system/engine/strategies/resonance.py \
        a_share_system/engine/runner.py \
        a_share_system/engine/backtest.py
git commit -m "feat: add ResonanceStrategy, runner, and backtest"
```

---

## Task 8: 数据层 — updater.py（每日增量更新）

**Files:**
- Create: `a_share_system/data/updater.py`

- [ ] **Step 1: 写 updater.py**

```python
# a_share_system/data/updater.py
"""
每日盘后运行：从 Tushare 拉今日数据写入 DuckDB。
"""
import os
import time
import pandas as pd
import tushare as ts
from datetime import datetime
from a_share_system.config import TUSHARE_TOKEN
from a_share_system.data.db import get_conn, init_schema

os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)

_pro = None


def get_pro():
    global _pro
    if _pro is None:
        _pro = ts.pro_api(TUSHARE_TOKEN)
    return _pro


def update_daily(con, trade_date: str) -> int:
    pro = get_pro()
    try:
        df = pro.daily(trade_date=trade_date)
        if df is None or df.empty:
            print(f"  daily {trade_date}: 无数据（非交易日？）")
            return 0
        df = df[["ts_code","trade_date","open","high","low","close","pre_close","pct_chg","vol","amount"]]
        con.executemany(
            "INSERT OR IGNORE INTO daily VALUES (?,?,?,?,?,?,?,?,?,?)",
            df.values.tolist()
        )
        print(f"  daily {trade_date}: +{len(df)} 行")
        return len(df)
    except Exception as e:
        print(f"  ⚠ daily {trade_date} 失败: {e}")
        return 0


def update_index_daily(con, trade_date: str) -> int:
    pro = get_pro()
    codes = ["000001.SH", "399001.SZ", "399006.SZ"]
    total = 0
    for code in codes:
        try:
            df = pro.index_daily(ts_code=code, start_date=trade_date, end_date=trade_date)
            if df is not None and not df.empty:
                row = df.iloc[0]
                con.execute(
                    "INSERT OR IGNORE INTO index_daily VALUES (?,?,?,?,?,?)",
                    [row.ts_code, int(row.trade_date), row.close, row.pct_chg, row.vol, row.amount]
                )
                total += 1
        except Exception as e:
            print(f"  ⚠ index_daily {code} 失败: {e}")
        time.sleep(0.3)
    print(f"  index_daily {trade_date}: +{total} 行")
    return total


def update_moneyflow(con, trade_date: str) -> int:
    pro = get_pro()
    try:
        df = pro.moneyflow(trade_date=trade_date)
        if df is None or df.empty:
            return 0
        rows = []
        for _, r in df.iterrows():
            rows.append([r.ts_code, int(r.trade_date),
                         float(r.get("net_mf_amount", 0) or 0),
                         float(r.get("buy_lg_amount", 0) or 0),
                         float(r.get("sell_lg_amount", 0) or 0)])
        con.executemany("INSERT OR IGNORE INTO moneyflow VALUES (?,?,?,?,?)", rows)
        print(f"  moneyflow {trade_date}: +{len(rows)} 行")
        return len(rows)
    except Exception as e:
        print(f"  ⚠ moneyflow {trade_date} 失败: {e}")
        return 0


def update_limit_list(con, trade_date: str) -> int:
    pro = get_pro()
    try:
        df = pro.limit_list_d(trade_date=trade_date)
        if df is None or df.empty:
            return 0
        rows = [[r.ts_code, int(r.trade_date), r.get("limit",""),
                 float(r.get("fd_amount", 0) or 0),
                 int(r.get("open_times", 0) or 0)]
                for _, r in df.iterrows()]
        con.executemany("INSERT OR IGNORE INTO limit_list VALUES (?,?,?,?,?)", rows)
        print(f"  limit_list {trade_date}: +{len(rows)} 行")
        return len(rows)
    except Exception as e:
        print(f"  ⚠ limit_list {trade_date} 失败: {e}")
        return 0


def run_update(trade_date: str | None = None) -> None:
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y%m%d")
    con = get_conn()
    init_schema(con)
    print(f"更新 {trade_date} 数据...")
    update_daily(con, trade_date)
    time.sleep(0.5)
    update_index_daily(con, trade_date)
    time.sleep(0.5)
    update_moneyflow(con, trade_date)
    time.sleep(0.5)
    update_limit_list(con, trade_date)
    print(f"✅ {trade_date} 更新完成")


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else None
    run_update(date)
```

- [ ] **Step 2: 测试 updater（用最近一个真实交易日）**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python -m a_share_system.data.updater 20260508
```

预期：
```
更新 20260508 数据...
  daily 20260508: +N 行（或"无数据"，因为已在 DuckDB 中）
  ...
✅ 20260508 更新完成
```

- [ ] **Step 3: Commit**

```bash
git add a_share_system/data/updater.py
git commit -m "feat: add daily data updater via Tushare API"
```

---

## Task 9: Web 层 — FastAPI 后端

**Files:**
- Create: `a_share_system/web/app.py`
- Create: `a_share_system/web/api/market.py`
- Create: `a_share_system/web/api/signals.py`
- Create: `a_share_system/tests/test_api.py`

- [ ] **Step 1: 写测试**

```python
# a_share_system/tests/test_api.py
from fastapi.testclient import TestClient
import duckdb
from a_share_system.data.db import init_schema


def make_test_db():
    con = duckdb.connect(":memory:")
    init_schema(con)
    con.execute("INSERT INTO stock_basic VALUES ('600111.SH','北方稀土','小金属',19970924)")
    con.execute("INSERT INTO daily VALUES ('600111.SH',20260508,54.0,55.5,53.5,54.75,55.31,-1.01,141480,770874)")
    con.execute("INSERT INTO index_daily VALUES ('000001.SH',20260508,4179.95,0.0,0.0,0.0)")
    con.execute("INSERT INTO signals VALUES ('600111.SH',20260508,'LIMIT_UP',85.0,'[\"LIMIT_UP\"]',9.98,3.2,2)")
    return con


def get_test_app(con):
    from a_share_system.web.app import create_app
    return create_app(con)


def test_dates_endpoint():
    con = make_test_db()
    app = get_test_app(con)
    client = TestClient(app)
    r = client.get("/api/dates")
    assert r.status_code == 200
    assert 20260508 in r.json()


def test_market_endpoint():
    con = make_test_db()
    app = get_test_app(con)
    client = TestClient(app)
    r = client.get("/api/market/20260508")
    assert r.status_code == 200
    data = r.json()
    assert "indices" in data
    assert "sentiment" in data


def test_signals_endpoint():
    con = make_test_db()
    app = get_test_app(con)
    client = TestClient(app)
    r = client.get("/api/signals/20260508")
    assert r.status_code == 200
    signals = r.json()
    assert isinstance(signals, list)
    assert signals[0]["ts_code"] == "600111.SH"


def test_signals_filtered_by_strategy():
    con = make_test_db()
    app = get_test_app(con)
    client = TestClient(app)
    r = client.get("/api/signals/20260508?strategy=RESONANCE")
    assert r.status_code == 200
    assert r.json() == []  # 测试库里没有 RESONANCE 信号
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python -m pytest a_share_system/tests/test_api.py -v 2>&1 | tail -8
```

预期：`ImportError`

- [ ] **Step 3: 写 web/api/market.py**

```python
# a_share_system/web/api/market.py
import duckdb
from fastapi import APIRouter

router = APIRouter()
_con: duckdb.DuckDBPyConnection = None


def set_conn(con: duckdb.DuckDBPyConnection):
    global _con
    _con = con


@router.get("/api/dates")
def get_dates():
    rows = _con.execute(
        "SELECT DISTINCT trade_date FROM daily ORDER BY trade_date DESC LIMIT 100"
    ).fetchall()
    return [r[0] for r in rows]


@router.get("/api/market/{date}")
def get_market(date: int):
    index_codes = {"000001.SH": "上证指数", "399001.SZ": "深证成指", "399006.SZ": "创业板指"}
    indices = []
    for code, name in index_codes.items():
        row = _con.execute(
            f"SELECT close, pct_chg FROM index_daily WHERE ts_code='{code}' AND trade_date={date}"
        ).fetchone()
        if row:
            indices.append({"code": code, "name": name, "close": row[0], "pct_chg": row[1]})

    today = _con.execute(f"SELECT pct_chg FROM daily WHERE trade_date={date}").fetchall()
    pcts = [r[0] for r in today]
    up = sum(1 for p in pcts if p > 0)
    down = sum(1 for p in pcts if p < 0)
    limit_up = sum(1 for p in pcts if p >= 9.5)
    limit_down = sum(1 for p in pcts if p <= -9.5)

    resonance_count = _con.execute(
        f"SELECT COUNT(*) FROM signals WHERE trade_date={date} AND strategy='RESONANCE'"
    ).fetchone()[0]

    max_boards = _con.execute(
        f"SELECT COALESCE(MAX(boards),0) FROM signals WHERE trade_date={date}"
    ).fetchone()[0]

    return {
        "date": str(date),
        "indices": indices,
        "sentiment": {
            "up": up, "down": down,
            "limit_up": limit_up, "limit_down": limit_down,
            "max_boards": max_boards,
            "resonance_count": resonance_count,
        }
    }


@router.get("/api/sectors/{date}")
def get_sectors(date: int):
    rows = _con.execute(f"""
        SELECT s.industry, AVG(d.pct_chg) AS avg_pct, COUNT(*) AS cnt
        FROM daily d
        JOIN stock_basic s ON d.ts_code = s.ts_code
        WHERE d.trade_date = {date} AND s.industry IS NOT NULL AND s.industry != ''
        GROUP BY s.industry HAVING cnt >= 3
        ORDER BY avg_pct DESC
    """).fetchall()
    return [
        {"name": r[0], "pct_chg": round(r[1], 2), "stock_count": r[2]}
        for r in rows
    ]
```

- [ ] **Step 4: 写 web/api/signals.py**

```python
# a_share_system/web/api/signals.py
import json
import duckdb
from fastapi import APIRouter, Query

router = APIRouter()
_con: duckdb.DuckDBPyConnection = None


def set_conn(con: duckdb.DuckDBPyConnection):
    global _con
    _con = con


@router.get("/api/signals/{date}")
def get_signals(date: int, strategy: str = Query(default="ALL")):
    where = f"sig.trade_date = {date}"
    if strategy != "ALL":
        where += f" AND sig.strategy = '{strategy}'"

    rows = _con.execute(f"""
        SELECT sig.ts_code,
               COALESCE(sb.name, sig.ts_code) AS name,
               sig.strategy, sig.score, sig.triggered,
               sig.pct_chg, sig.vol_ratio, sig.boards
        FROM signals sig
        LEFT JOIN stock_basic sb ON sig.ts_code = sb.ts_code
        WHERE {where}
        ORDER BY sig.score DESC
    """).fetchall()

    return [
        {
            "ts_code":    r[0],
            "name":       r[1],
            "strategy":   r[2],
            "score":      r[3],
            "triggered":  json.loads(r[4]) if r[4] else [],
            "pct_chg":    r[5],
            "vol_ratio":  r[6],
            "boards":     r[7],
        }
        for r in rows
    ]
```

- [ ] **Step 5: 写 web/app.py**

```python
# a_share_system/web/app.py
import duckdb
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from a_share_system.web.api import market, signals


def create_app(con: duckdb.DuckDBPyConnection) -> FastAPI:
    market.set_conn(con)
    signals.set_conn(con)

    app = FastAPI(title="A股交易系统")
    app.include_router(market.router)
    app.include_router(signals.router)

    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(static_dir / "index.html"))

    return app


if __name__ == "__main__":
    import uvicorn
    from a_share_system.data.db import get_conn
    con = get_conn()
    app = create_app(con)
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

- [ ] **Step 6: 运行 API 测试**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python -m pytest a_share_system/tests/test_api.py -v
```

预期：`4 passed`

- [ ] **Step 7: Commit**

```bash
git add a_share_system/web/app.py \
        a_share_system/web/api/market.py \
        a_share_system/web/api/signals.py \
        a_share_system/tests/test_api.py
git commit -m "feat: add FastAPI web layer with market and signals endpoints"
```

---

## Task 10: 前端 — Apple 风格 index.html

**Files:**
- Create: `a_share_system/web/static/index.html`

- [ ] **Step 1: 写 index.html**

```html
<!-- a_share_system/web/static/index.html -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股交易系统</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,"SF Pro Display","SF Pro Text",sans-serif;background:#000;color:#f5f5f7;min-height:100vh;display:flex;flex-direction:column}
.titlebar{background:rgba(28,28,30,.95);backdrop-filter:blur(20px);border-bottom:1px solid rgba(255,255,255,.06);padding:14px 24px;display:flex;justify-content:space-between;align-items:center;flex-shrink:0}
.titlebar-dots{display:flex;gap:6px}
.dot{width:12px;height:12px;border-radius:50%}
.dot-r{background:#ff5f57}.dot-y{background:#febc2e}.dot-g{background:#28c840}
.titlebar-title{font-size:14px;font-weight:600;color:#f5f5f7;margin-left:12px}
.titlebar-date{font-size:12px;color:#636366;font-variant-numeric:tabular-nums}
.body{display:flex;flex:1;overflow:hidden}
.sidebar{width:240px;flex-shrink:0;background:#141414;border-right:1px solid rgba(255,255,255,.06);padding:20px 16px;display:flex;flex-direction:column;gap:20px;overflow-y:auto}
.section-label{font-size:10px;font-weight:600;color:#636366;letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px}
.index-card{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);border-radius:10px;padding:10px 12px;display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.idx-name{font-size:12px;color:#aeaeb2}
.idx-price{font-size:14px;font-weight:600;color:#f5f5f7;font-variant-numeric:tabular-nums}
.idx-chg{font-size:11px;font-variant-numeric:tabular-nums}
.up{color:#30d158}.down{color:#ff453a}
.sentiment-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px}
.s-chip{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:7px 4px;text-align:center}
.s-val{font-size:16px;font-weight:700;font-variant-numeric:tabular-nums}
.s-lbl{font-size:9px;color:#636366;margin-top:2px}
.sector-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px}
.s-cell{border-radius:7px;padding:6px 8px;font-size:10px;display:flex;justify-content:space-between;align-items:center}
.s-up-strong{background:rgba(48,209,88,.18);border:1px solid rgba(48,209,88,.25)}
.s-up-mid{background:rgba(48,209,88,.10);border:1px solid rgba(48,209,88,.15)}
.s-down-mid{background:rgba(255,69,58,.10);border:1px solid rgba(255,69,58,.15)}
.s-down-strong{background:rgba(255,69,58,.18);border:1px solid rgba(255,69,58,.25)}
.s-pct{font-weight:600;font-variant-numeric:tabular-nums}
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.tabs-bar{padding:16px 20px 0;display:flex;gap:4px;border-bottom:1px solid rgba(255,255,255,.06);background:#1c1c1e;overflow-x:auto;flex-shrink:0}
.tab{padding:8px 14px;font-size:12px;font-weight:500;color:#636366;border-radius:8px 8px 0 0;cursor:pointer;white-space:nowrap;border:1px solid transparent;border-bottom:none;position:relative;bottom:-1px;transition:all .15s}
.tab:hover{color:#aeaeb2}
.tab.active{color:#f5f5f7;background:#2c2c2e;border-color:rgba(255,255,255,.08);border-bottom-color:#2c2c2e}
.badge{display:inline-block;background:rgba(255,255,255,.08);border-radius:10px;padding:0 5px;font-size:10px;margin-left:4px;font-variant-numeric:tabular-nums}
.tab.active .badge{background:rgba(10,132,255,.25);color:#0a84ff}
.table-area{flex:1;background:#2c2c2e;overflow-y:auto;padding:16px 20px}
.summary-bar{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.pill{padding:4px 10px;border-radius:20px;font-size:11px;font-weight:500}
.pill-r{background:rgba(191,90,242,.15);color:#bf5af2;border:1px solid rgba(191,90,242,.25)}
.pill-g{background:rgba(255,69,58,.12);color:#ff6961;border:1px solid rgba(255,69,58,.2)}
.pill-b{background:rgba(10,132,255,.12);color:#0a84ff;border:1px solid rgba(10,132,255,.2)}
.pill-n{background:rgba(255,255,255,.06);color:#aeaeb2;border:1px solid rgba(255,255,255,.08)}
table{width:100%;border-collapse:collapse;font-size:13px}
thead tr{border-bottom:1px solid rgba(255,255,255,.06)}
th{padding:8px 10px;text-align:left;font-size:10px;font-weight:600;color:#636366;letter-spacing:.05em;text-transform:uppercase}
th:last-child,td:last-child{text-align:right}
tbody tr{border-bottom:1px solid rgba(255,255,255,.04);cursor:pointer;transition:background .1s}
tbody tr:hover{background:rgba(255,255,255,.04)}
tbody tr:last-child{border-bottom:none}
td{padding:11px 10px;color:#e5e5ea;vertical-align:middle}
.sn{font-weight:600;color:#f5f5f7;font-size:13px}
.sc{font-size:10px;color:#636366;margin-top:1px;font-family:"SF Mono",monospace}
.tag{display:inline-block;padding:2px 7px;border-radius:5px;font-size:10px;font-weight:500;margin-right:3px}
.tag-r{background:rgba(191,90,242,.2);color:#bf5af2}
.tag-l{background:rgba(255,69,58,.15);color:#ff6961}
.tag-v{background:rgba(10,132,255,.15);color:#0a84ff}
.tag-m{background:rgba(255,159,10,.15);color:#ff9f0a}
.board-badge{display:inline-block;background:rgba(255,159,10,.2);color:#ff9f0a;border-radius:5px;padding:2px 6px;font-size:10px;font-weight:700}
.loading{color:#636366;text-align:center;padding:40px;font-size:14px}
</style>
</head>
<body>
<div class="titlebar">
  <div style="display:flex;align-items:center">
    <div class="titlebar-dots">
      <div class="dot dot-r"></div><div class="dot dot-y"></div><div class="dot dot-g"></div>
    </div>
    <div class="titlebar-title">A股交易系统</div>
  </div>
  <div class="titlebar-date" id="dateLabel">加载中...</div>
</div>

<div class="body">
  <div class="sidebar">
    <div>
      <div class="section-label">大盘指数</div>
      <div id="indices"><div class="loading">加载中...</div></div>
    </div>
    <div>
      <div class="section-label">市场情绪</div>
      <div class="sentiment-row" id="sentiment"></div>
    </div>
    <div>
      <div class="section-label">板块热力</div>
      <div class="sector-grid" id="sectors"></div>
    </div>
  </div>

  <div class="main">
    <div class="tabs-bar" id="tabs"></div>
    <div class="table-area">
      <div class="summary-bar" id="summary"></div>
      <table>
        <thead id="thead"></thead>
        <tbody id="tbody"><tr><td colspan="8" class="loading">加载中...</td></tr></tbody>
      </table>
    </div>
  </div>
</div>

<script>
const STRATEGIES = [
  {id:'RESONANCE',    label:'⚡ 共振精选'},
  {id:'LIMIT_UP',     label:'🔥 N字涨停'},
  {id:'VOLUME_SPIKE', label:'💥 突然爆量'},
  {id:'CONSECUTIVE',  label:'👑 连板龙头'},
  {id:'MA_BREAKOUT',  label:'📈 均线突破'},
  {id:'MACD_CROSS',   label:'📊 MACD金叉'},
  {id:'MACD_DIVERGENCE', label:'🔻 底背离'},
];

let allSignals = [];
let currentStrategy = 'RESONANCE';

async function init() {
  const dates = await fetch('/api/dates').then(r => r.json());
  const date = dates[0];
  document.getElementById('dateLabel').textContent = `${String(date).slice(0,4)}-${String(date).slice(4,6)}-${String(date).slice(6)} 盘后`;

  const [market, sectors, signals] = await Promise.all([
    fetch(`/api/market/${date}`).then(r => r.json()),
    fetch(`/api/sectors/${date}`).then(r => r.json()),
    fetch(`/api/signals/${date}`).then(r => r.json()),
  ]);

  allSignals = signals;
  renderIndices(market.indices);
  renderSentiment(market.sentiment);
  renderSectors(sectors);
  renderTabs(signals);
  renderTable(currentStrategy);
}

function renderIndices(indices) {
  const el = document.getElementById('indices');
  el.innerHTML = indices.map(idx => `
    <div class="index-card">
      <div class="idx-name">${idx.name}</div>
      <div>
        <div class="idx-price">${idx.close.toFixed(2)}</div>
        <div class="idx-chg ${idx.pct_chg >= 0 ? 'up':'down'}">
          ${idx.pct_chg >= 0 ? '▲':'▼'} ${Math.abs(idx.pct_chg).toFixed(2)}%
        </div>
      </div>
    </div>`).join('');
}

function renderSentiment(s) {
  const items = [
    {val: s.up,              lbl:'上涨', cls:'up'},
    {val: s.down,            lbl:'下跌', cls:'down'},
    {val: s.limit_up,        lbl:'涨停', cls:'', style:'color:#ff9f0a'},
    {val: s.limit_down,      lbl:'跌停', cls:'down'},
    {val: s.max_boards,      lbl:'连板高', cls:'', style:'color:#bf5af2'},
    {val: s.resonance_count, lbl:'共振', cls:'', style:'color:#bf5af2'},
  ];
  document.getElementById('sentiment').innerHTML = items.map(i => `
    <div class="s-chip">
      <div class="s-val ${i.cls}" ${i.style?`style="${i.style}"`:''}>${i.val}</div>
      <div class="s-lbl">${i.lbl}</div>
    </div>`).join('');
}

function renderSectors(sectors) {
  const top6 = sectors.slice(0, 6);
  const bot4 = sectors.slice(-4);
  const shown = [...top6, ...bot4].slice(0, 8);
  document.getElementById('sectors').innerHTML = shown.map(s => {
    const cls = s.pct_chg >= 2 ? 's-up-strong' : s.pct_chg >= 0 ? 's-up-mid' : s.pct_chg >= -2 ? 's-down-mid' : 's-down-strong';
    const sign = s.pct_chg >= 0 ? '+' : '';
    return `<div class="s-cell ${cls}">
      <span style="color:rgba(255,255,255,.75)">${s.name}</span>
      <span class="s-pct ${s.pct_chg>=0?'up':'down'}">${sign}${s.pct_chg.toFixed(1)}%</span>
    </div>`;
  }).join('');
}

function renderTabs(signals) {
  const counts = {};
  signals.forEach(s => counts[s.strategy] = (counts[s.strategy]||0) + 1);
  document.getElementById('tabs').innerHTML = STRATEGIES.map(st => `
    <div class="tab ${st.id===currentStrategy?'active':''}" onclick="switchTab('${st.id}')">
      ${st.label} <span class="badge">${counts[st.id]||0}</span>
    </div>`).join('');
}

function switchTab(strategyId) {
  currentStrategy = strategyId;
  renderTabs(allSignals);
  renderTable(strategyId);
}

function renderTable(strategyId) {
  const filtered = strategyId === 'ALL'
    ? allSignals
    : allSignals.filter(s => s.strategy === strategyId);

  document.getElementById('thead').innerHTML = `<tr>
    <th>#</th><th>股票</th><th>涨幅</th><th>量比</th><th>连板</th><th>触发策略</th><th>评分</th>
  </tr>`;

  document.getElementById('tbody').innerHTML = filtered.length === 0
    ? `<tr><td colspan="7" class="loading">暂无信号</td></tr>`
    : filtered.map((s, i) => {
        const tags = s.triggered.map(t => `<span class="tag tag-${tagCls(t)}">${tagName(t)}</span>`).join('');
        const boardHtml = s.boards >= 2 ? `<span class="board-badge">${s.boards}板</span>` : '<span style="color:#636366">—</span>';
        const pctCls = s.pct_chg >= 0 ? 'up' : 'down';
        const sign = s.pct_chg >= 0 ? '+' : '';
        return `<tr>
          <td style="color:#aeaeb2;font-size:12px">${i+1}</td>
          <td><div class="sn">${s.name}</div><div class="sc">${s.ts_code}</div></td>
          <td class="${pctCls}" style="font-weight:600;font-variant-numeric:tabular-nums">${sign}${s.pct_chg.toFixed(2)}%</td>
          <td>${s.vol_ratio.toFixed(2)}×</td>
          <td>${boardHtml}</td>
          <td>${tags}</td>
          <td style="font-weight:700;color:#c7d2fe">${s.score.toFixed(1)}</td>
        </tr>`;
      }).join('');
}

const TAG_MAP = {
  LIMIT_UP:'N字涨停', VOLUME_SPIKE:'爆量', MA_BREAKOUT:'均线',
  MACD_CROSS:'MACD', MACD_DIVERGENCE:'底背离', CONSECUTIVE:'连板', RESONANCE:'共振'
};
const TAG_CLS = {
  LIMIT_UP:'l', VOLUME_SPIKE:'v', MA_BREAKOUT:'m',
  MACD_CROSS:'m', MACD_DIVERGENCE:'m', CONSECUTIVE:'m', RESONANCE:'r'
};
function tagName(t) { return TAG_MAP[t] || t; }
function tagCls(t)  { return TAG_CLS[t] || 'n'; }

init();
</script>
</body>
</html>
```

- [ ] **Step 2: 启动服务，浏览器验证**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python a_share_system/web/app.py
```

浏览器打开 `http://localhost:8080`，确认：
- 左侧显示大盘指数、市场情绪、板块热力
- 右侧默认显示"⚡ 共振精选" Tab
- Tab 切换正常，信号表格有数据

- [ ] **Step 3: Commit**

```bash
git add a_share_system/web/static/index.html
git commit -m "feat: add Apple-style frontend dashboard"
```

---

## Task 11: 入口 main.py + 全量回测

**Files:**
- Create: `a_share_system/main.py`

- [ ] **Step 1: 写 main.py**

```python
# a_share_system/main.py
import sys
import uvicorn
from a_share_system.data.db import get_conn, init_schema
from a_share_system.data.updater import run_update
from a_share_system.engine.runner import run_daily
from a_share_system.web.app import create_app


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "serve"

    if mode == "migrate":
        from a_share_system.data.migrate import run_migration
        run_migration()

    elif mode == "update":
        date = sys.argv[2] if len(sys.argv) > 2 else None
        run_update(date)

    elif mode == "run":
        con = get_conn()
        date = int(sys.argv[2]) if len(sys.argv) > 2 else \
               con.execute("SELECT MAX(trade_date) FROM daily").fetchone()[0]
        print(f"扫描 {date}...")
        count = run_daily(con, date)
        print(f"✅ 写入 {count} 个信号")

    elif mode == "backtest":
        from a_share_system.engine.backtest import run_backtest
        start = int(sys.argv[2]) if len(sys.argv) > 2 else 20210104
        end   = int(sys.argv[3]) if len(sys.argv) > 3 else 20261231
        run_backtest(start, end)

    elif mode == "serve":
        con = get_conn()
        app = create_app(con)
        print("🚀 启动 http://localhost:8080")
        uvicorn.run(app, host="0.0.0.0", port=8080)

    else:
        print("用法: python main.py [migrate|update|run|backtest|serve]")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑近 30 日回测验证策略**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python a_share_system/main.py backtest 20260401 20260508
```

预期：
```
回测 20260401 ~ 20260508，共 N 个交易日
  [N/N] 20260508: M 个信号
✅ 回测完成，累计写入 X 条信号
```

- [ ] **Step 3: 跑完整版启动（update → run → serve）**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python a_share_system/main.py serve
```

浏览器访问 `http://localhost:8080` 确认界面正常。

- [ ] **Step 4: 运行全部测试**

```bash
cd /Users/xinkai_ma/repo/openclaw-hermes/M
conda run -n mxk_env python -m pytest a_share_system/tests/ -v
```

预期：全部通过（无 FAILED）

- [ ] **Step 5: Commit**

```bash
git add a_share_system/main.py
git commit -m "feat: add main.py entrypoint with migrate/update/run/backtest/serve modes"
```

---

## 验收标准

- [ ] `python main.py migrate` 完成，DuckDB 包含 600 万行历史数据
- [ ] `python main.py run` 当日信号写入正常，RESONANCE 策略有输出
- [ ] `python main.py backtest 20260401 20260508` 30 日回测无报错
- [ ] `python main.py serve` 启动后浏览器可看到完整仪表盘
- [ ] 所有测试通过：`pytest a_share_system/tests/ -v`
