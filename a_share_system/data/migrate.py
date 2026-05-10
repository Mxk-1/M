# a_share_system/data/migrate.py
"""
一次性将 tushare/ 历史 CSV 导入 DuckDB。
幂等：主键冲突时忽略（INSERT OR IGNORE）。
"""
import duckdb
from pathlib import Path
from a_share_system.config import DATA_ROOT
from a_share_system.data.db import get_conn, init_schema


def _count(con: duckdb.DuckDBPyConnection, table: str) -> int:
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _insert_csv(con: duckdb.DuckDBPyConnection, csv_path: Path,
                table: str, columns: list[str]) -> int:
    col_str = ", ".join(columns)
    try:
        before = _count(con, table)
        con.execute(f"""
            INSERT OR IGNORE INTO {table} ({col_str})
            SELECT {col_str}
            FROM read_csv_auto('{csv_path}', ignore_errors=true)
        """)
        return _count(con, table) - before
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
                # Detect column names from CSV header
                header = con.execute(
                    f"SELECT * FROM read_csv_auto('{csv_file}', ignore_errors=true) LIMIT 0"
                ).description
                col_names = [d[0] for d in header]
                fd_col = "fd_amount" if "fd_amount" in col_names else "fd"
                has_open_times = "open_times" in col_names
                open_times_expr = 'TRY_CAST(open_times AS INTEGER)' if has_open_times else 'NULL'
                before = _count(con, "limit_list")
                con.execute(f"""
                    INSERT OR IGNORE INTO limit_list (ts_code, trade_date, lmt, fd_amount, open_times)
                    SELECT ts_code,
                           CAST(trade_date AS INTEGER),
                           "limit",
                           TRY_CAST({fd_col} AS DOUBLE),
                           {open_times_expr}
                    FROM read_csv_auto('{csv_file}', ignore_errors=true)
                """)
                rows = _count(con, "limit_list") - before
                total += rows
            except Exception as e:
                print(f"  ⚠ 跳过 {csv_file.name}: {e}")
    print(f"  limit_list 合计: {total:,} 行")


def migrate_top_list(con: duckdb.DuckDBPyConnection) -> None:
    total = 0
    for year_dir in sorted(DATA_ROOT.glob("*/other")):
        for csv_file in sorted(year_dir.glob("top_list*.csv")):
            try:
                before = _count(con, "top_list")
                con.execute(f"""
                    INSERT OR IGNORE INTO top_list (ts_code, trade_date, net_amount, reason)
                    SELECT ts_code,
                           CAST(trade_date AS INTEGER),
                           TRY_CAST(net_amount AS DOUBLE),
                           reason
                    FROM read_csv_auto('{csv_file}', ignore_errors=true)
                """)
                rows = _count(con, "top_list") - before
                total += rows
            except Exception as e:
                print(f"  ⚠ 跳过 {csv_file.name}: {e}")
    print(f"  top_list 合计: {total:,} 行")


def migrate_stock_basic(con: duckdb.DuckDBPyConnection) -> None:
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

    daily_cnt = con.execute("SELECT COUNT(*) FROM daily").fetchone()[0]
    dates_cnt = con.execute("SELECT COUNT(DISTINCT trade_date) FROM daily").fetchone()[0]
    print(f"\n✅ 导入完成: daily={daily_cnt:,}行, {dates_cnt}个交易日")


if __name__ == "__main__":
    run_migration()
