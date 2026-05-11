# a_share_system/data/db.py
import threading
import duckdb
from pathlib import Path
from a_share_system.config import DB_PATH

_conn: duckdb.DuckDBPyConnection | None = None
_thread_local = threading.local()


def get_conn(path: str | None = None) -> duckdb.DuckDBPyConnection:
    global _conn
    if path == ":memory:":
        return duckdb.connect(":memory:")
    if _conn is None:
        db_path = Path(path) if path else DB_PATH
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _conn = duckdb.connect(str(db_path))
    return _conn


def get_web_conn() -> duckdb.DuckDBPyConnection:
    """每个线程独立连接，供 Web API 并发使用。"""
    if not hasattr(_thread_local, "conn") or _thread_local.conn is None:
        _thread_local.conn = duckdb.connect(str(DB_PATH))
    return _thread_local.conn


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    schema_path = Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt)
