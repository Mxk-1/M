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
        import time
        con = get_conn()
        date = int(sys.argv[2]) if len(sys.argv) > 2 else \
               con.execute("SELECT MAX(trade_date) FROM daily").fetchone()[0]
        d = str(date)
        print(f"\n扫描 {d[:4]}-{d[4:6]}-{d[6:]} 全市场策略信号\n")
        t0 = time.time()
        count = run_daily(con, date)
        elapsed = time.time() - t0
        print(f"\n✅ 共写入 {count} 条信号，耗时 {elapsed:.1f}s")

    elif mode == "backtest":
        from a_share_system.engine.backtest import run_backtest
        start = int(sys.argv[2]) if len(sys.argv) > 2 else 20210104
        end   = int(sys.argv[3]) if len(sys.argv) > 3 else 20261231
        run_backtest(start, end)

    elif mode == "serve":
        con = get_conn()
        app = create_app(con)
        print("启动 http://localhost:8080")
        uvicorn.run(app, host="0.0.0.0", port=8080)

    elif mode == "news":
        # news import — 从内置列表写入新闻
        from a_share_system.data.news import save_news
        from a_share_system.data.news_seed import SEED_NEWS
        con = get_conn()
        init_schema(con)
        n = save_news(con, SEED_NEWS)
        print(f"✅ 写入 {n} 条新闻（已存在的跳过）")

    else:
        print("用法: python main.py [migrate|update|run|backtest|serve|news]")


if __name__ == "__main__":
    main()
