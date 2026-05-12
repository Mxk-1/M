# a_share_system/data/updater.py
"""每日盘后运行：从 Tushare 拉今日数据写入 DuckDB。"""
import os
import time
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
        df = df[["ts_code", "trade_date", "open", "high", "low",
                  "close", "pre_close", "pct_chg", "vol", "amount"]]
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
                    [row.ts_code, int(row.trade_date), row.close,
                     row.pct_chg, row.vol, row.amount]
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
        rows = [
            [r.ts_code, int(r.trade_date),
             float(r.get("net_mf_amount", 0) or 0),
             float(r.get("buy_lg_amount", 0) or 0),
             float(r.get("sell_lg_amount", 0) or 0)]
            for _, r in df.iterrows()
        ]
        con.executemany("INSERT OR IGNORE INTO moneyflow VALUES (?,?,?,?,?)", rows)
        print(f"  moneyflow {trade_date}: +{len(rows)} 行")
        return len(rows)
    except Exception as e:
        print(f"  ⚠ moneyflow {trade_date} 失败: {e}")
        return 0


def update_top_list(con, trade_date: str) -> int:
    pro = get_pro()
    try:
        df = pro.top_list(trade_date=trade_date)
        if df is None or df.empty:
            return 0
        rows = [
            [r.ts_code, int(r.trade_date),
             float(r.get("net_amount", 0) or 0),
             str(r.get("reason", "") or "")]
            for _, r in df.iterrows()
        ]
        con.executemany("INSERT OR IGNORE INTO top_list VALUES (?,?,?,?)", rows)
        print(f"  top_list {trade_date}: +{len(rows)} 行")
        return len(rows)
    except Exception as e:
        print(f"  ⚠ top_list {trade_date} 失败: {e}")
        return 0


def update_limit_list(con, trade_date: str) -> int:
    pro = get_pro()
    try:
        df = pro.limit_list_d(trade_date=trade_date)
        if df is None or df.empty:
            return 0
        rows = [
            [r.ts_code, int(r.trade_date),
             str(r.get("limit", "") or ""),
             float(r.get("fd_amount", 0) or 0),
             int(r.get("open_times", 0) or 0)]
            for _, r in df.iterrows()
        ]
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
    update_top_list(con, trade_date)
    time.sleep(0.5)
    update_limit_list(con, trade_date)
    print(f"✅ {trade_date} 更新完成")


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else None
    run_update(date)
