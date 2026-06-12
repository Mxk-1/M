"""
回填 adj_factor 历史数据。
只补 daily 表中已有、但 adj_factor 中缺失的交易日。
用法：conda run -n mxk_env python -m a_share_system.data.backfill_adj_factor
"""
import os
import time
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)

from a_share_system.data.db import get_conn, init_schema
from a_share_system.data.updater import update_adj_factor


def run_backfill():
    con = get_conn()
    init_schema(con)

    # 找出 daily 有、adj_factor 没有的交易日
    missing = con.execute("""
        SELECT DISTINCT d.trade_date
        FROM daily d
        LEFT JOIN adj_factor a ON d.trade_date = a.trade_date
        WHERE a.trade_date IS NULL
        ORDER BY d.trade_date
    """).fetchall()

    dates = [str(r[0]) for r in missing]
    print(f"需要回填 {len(dates)} 个交易日")

    for i, d in enumerate(dates, 1):
        n = update_adj_factor(con, d)
        print(f"  [{i}/{len(dates)}] {d}  +{n}")
        time.sleep(0.35)   # tushare 限流保护

    print("✅ 回填完成")


if __name__ == "__main__":
    run_backfill()
