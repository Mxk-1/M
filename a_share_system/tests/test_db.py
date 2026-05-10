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
