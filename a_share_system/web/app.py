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

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(str(static_dir / "favicon.ico"))

    return app


if __name__ == "__main__":
    import uvicorn
    from a_share_system.data.db import get_conn
    con = get_conn()
    app = create_app(con)
    uvicorn.run(app, host="0.0.0.0", port=8080)
