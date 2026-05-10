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
    con = get_conn()
    latest = con.execute("SELECT MAX(trade_date) FROM daily").fetchone()[0]
    days = get_trading_days(con, 0, latest)
    start = days[-30] if len(days) >= 30 else days[0]
    run_backtest(start, latest, con)
