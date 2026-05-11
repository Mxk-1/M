# a_share_system/web/app.py
from pathlib import Path
import duckdb
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from a_share_system.web.api import market, signals


def create_app(con: duckdb.DuckDBPyConnection) -> FastAPI:
    app = FastAPI(title="A股交易系统")
    app.include_router(market.router)
    app.include_router(signals.router)

    static_dir = Path(__file__).parent / "frontend" / "dist"
    static_dir.mkdir(exist_ok=True)
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(static_dir / "index.html"))

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        return FileResponse(str(static_dir / "favicon.svg"))

    return app


if __name__ == "__main__":
    import uvicorn
    from a_share_system.data.db import get_conn
    con = get_conn()
    app = create_app(con)
    uvicorn.run(app, host="0.0.0.0", port=8080)
