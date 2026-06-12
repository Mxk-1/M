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


def update_adj_factor(con, trade_date: str) -> int:
    pro = get_pro()
    try:
        df = pro.adj_factor(trade_date=trade_date)
        if df is None or df.empty:
            print(f"  adj_factor {trade_date}: 无数据")
            return 0
        df = df[["ts_code", "trade_date", "adj_factor"]]
        con.executemany(
            "INSERT OR IGNORE INTO adj_factor VALUES (?,?,?)",
            df.values.tolist()
        )
        print(f"  adj_factor {trade_date}: +{len(df)} 行")
        return len(df)
    except Exception as e:
        print(f"  ⚠ adj_factor {trade_date} 失败: {e}")
        return 0


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


def update_daily_basic(con, trade_date: str) -> int:
    pro = get_pro()
    try:
        df = pro.daily_basic(trade_date=trade_date,
                             fields="ts_code,trade_date,pe_ttm,pb,ps_ttm,total_mv,circ_mv,turnover_rate,volume_ratio")
        if df is None or df.empty:
            print(f"  daily_basic {trade_date}: 无数据")
            return 0
        rows = [
            [r.ts_code, int(r.trade_date),
             float(r.get("pe_ttm", 0) or 0),
             float(r.get("pb", 0) or 0),
             float(r.get("ps_ttm", 0) or 0),
             float(r.get("total_mv", 0) or 0),
             float(r.get("circ_mv", 0) or 0),
             float(r.get("turnover_rate", 0) or 0),
             float(r.get("volume_ratio", 0) or 0)]
            for _, r in df.iterrows()
        ]
        con.executemany("INSERT OR IGNORE INTO daily_basic VALUES (?,?,?,?,?,?,?,?,?)", rows)
        print(f"  daily_basic {trade_date}: +{len(rows)} 行")
        return len(rows)
    except Exception as e:
        print(f"  ⚠ daily_basic {trade_date} 失败: {e}")
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


def get_trade_dates(start: str, end: str) -> list[str]:
    """从 Tushare 获取 [start, end] 之间的交易日列表。"""
    pro = get_pro()
    df = pro.trade_cal(exchange="SSE", start_date=start, end_date=end, is_open="1")
    if df is None or df.empty:
        return []
    return sorted(df["cal_date"].tolist())


def _update_one_date(con, trade_date: str) -> None:
    print(f"更新 {trade_date} 数据...")
    update_daily(con, trade_date)
    time.sleep(0.5)
    update_adj_factor(con, trade_date)
    time.sleep(0.5)
    update_index_daily(con, trade_date)
    time.sleep(0.5)
    update_moneyflow(con, trade_date)
    time.sleep(0.5)
    update_top_list(con, trade_date)
    time.sleep(0.5)
    update_daily_basic(con, trade_date)
    time.sleep(0.5)
    update_limit_list(con, trade_date)
    print(f"✅ {trade_date} 更新完成")


def run_update(trade_date: str | None = None) -> None:
    con = get_conn()
    init_schema(con)

    today = datetime.now().strftime("%Y%m%d")

    if trade_date is not None:
        # 指定了单个日期，直接更新
        _update_one_date(con, trade_date)
        return

    # 未指定日期：从数据库最新日期的下一个交易日补全到今天
    row = con.execute("SELECT MAX(trade_date) FROM daily").fetchone()
    latest = str(row[0]) if row and row[0] else None

    if latest is None or latest >= today:
        _update_one_date(con, today)
        return

    # latest 是 int 存储，转成字符串后加 1 天作为 start
    from datetime import timedelta
    start_dt = datetime.strptime(latest, "%Y%m%d") + timedelta(days=1)
    start = start_dt.strftime("%Y%m%d")

    print(f"检测到数据缺口：{latest} → {today}，获取交易日历...")
    dates = get_trade_dates(start, today)

    if not dates:
        print("区间内无交易日，无需更新。")
        return

    print(f"共 {len(dates)} 个交易日待更新：{dates[0]} ~ {dates[-1]}\n")
    for d in dates:
        _update_one_date(con, d)
        print()


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else None
    run_update(date)
