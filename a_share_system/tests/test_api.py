# a_share_system/tests/test_api.py
from fastapi.testclient import TestClient
import duckdb
from a_share_system.data.db import init_schema


def make_test_db():
    con = duckdb.connect(":memory:")
    init_schema(con)
    con.execute("INSERT INTO stock_basic VALUES ('600111.SH','北方稀土','小金属',19970924)")
    con.execute("INSERT INTO daily VALUES ('600111.SH',20260508,54.0,55.5,53.5,54.75,55.31,-0.56,-1.01,9980000,7708740000)")
    con.execute("INSERT INTO index_daily VALUES ('000001.SH',20260508,4179.95,0.0,0.0,0.0)")
    con.execute("INSERT INTO signals VALUES ('600111.SH',20260508,'LIMIT_UP',85.0,'[\"LIMIT_UP\"]',9.98,3.2,2)")
    return con


def get_test_app(con):
    from a_share_system.web.app import create_app
    return create_app(con)


def test_dates_endpoint():
    con = make_test_db()
    app = get_test_app(con)
    client = TestClient(app)
    r = client.get("/api/dates")
    assert r.status_code == 200
    assert 20260508 in r.json()


def test_market_endpoint():
    con = make_test_db()
    app = get_test_app(con)
    client = TestClient(app)
    r = client.get("/api/market/20260508")
    assert r.status_code == 200
    data = r.json()
    assert "indices" in data
    assert "sentiment" in data


def test_signals_endpoint():
    con = make_test_db()
    app = get_test_app(con)
    client = TestClient(app)
    r = client.get("/api/signals/20260508")
    assert r.status_code == 200
    signals = r.json()
    assert isinstance(signals, list)
    assert signals[0]["ts_code"] == "600111.SH"


def test_signals_filtered_by_strategy():
    con = make_test_db()
    app = get_test_app(con)
    client = TestClient(app)
    r = client.get("/api/signals/20260508?strategy=RESONANCE")
    assert r.status_code == 200
    assert r.json() == []
