# a_share_system/web/api/market.py
import duckdb
from fastapi import APIRouter

router = APIRouter()
_con: duckdb.DuckDBPyConnection = None


def set_conn(con: duckdb.DuckDBPyConnection):
    global _con
    _con = con


@router.get("/api/dates")
def get_dates():
    rows = _con.execute(
        "SELECT DISTINCT trade_date FROM signals ORDER BY trade_date DESC LIMIT 100"
    ).fetchall()
    return [r[0] for r in rows]


@router.get("/api/market/{date}")
def get_market(date: int):
    index_codes = {"000001.SH": "上证指数", "399001.SZ": "深证成指", "399006.SZ": "创业板指"}
    indices = []
    for code, name in index_codes.items():
        row = _con.execute(
            f"SELECT close, pct_chg FROM index_daily WHERE ts_code='{code}' AND trade_date={date}"
        ).fetchone()
        if row:
            indices.append({"code": code, "name": name, "close": row[0], "pct_chg": row[1]})

    today = _con.execute(f"SELECT pct_chg FROM daily WHERE trade_date={date}").fetchall()
    pcts = [r[0] for r in today]
    up = sum(1 for p in pcts if p > 0)
    down = sum(1 for p in pcts if p < 0)
    limit_up = sum(1 for p in pcts if p >= 9.5)
    limit_down = sum(1 for p in pcts if p <= -9.5)

    resonance_count = _con.execute(
        f"SELECT COUNT(*) FROM signals WHERE trade_date={date} AND strategy='RESONANCE'"
    ).fetchone()[0]

    max_boards = _con.execute(
        f"SELECT COALESCE(MAX(boards),0) FROM signals WHERE trade_date={date}"
    ).fetchone()[0]

    return {
        "date": str(date),
        "indices": indices,
        "sentiment": {
            "up": up, "down": down,
            "limit_up": limit_up, "limit_down": limit_down,
            "max_boards": max_boards,
            "resonance_count": resonance_count,
        }
    }


@router.get("/api/sectors/{date}")
def get_sectors(date: int):
    rows = _con.execute(f"""
        SELECT s.industry, AVG(d.pct_chg) AS avg_pct, COUNT(*) AS cnt
        FROM daily d
        JOIN stock_basic s ON d.ts_code = s.ts_code
        WHERE d.trade_date = {date} AND s.industry IS NOT NULL AND s.industry != ''
        GROUP BY s.industry HAVING cnt >= 3
        ORDER BY avg_pct DESC
    """).fetchall()
    return [
        {"name": r[0], "pct_chg": round(r[1], 2), "stock_count": r[2]}
        for r in rows
    ]


@router.get("/api/stocks/{date}")
def get_stocks(date: int):
    rows = _con.execute(f"""
        SELECT d.ts_code,
               COALESCE(sb.name, d.ts_code) AS name,
               COALESCE(sb.industry, '') AS industry,
               d.close, d.pct_chg, d.vol, d.amount,
               d.open, d.high, d.low, d.pre_close
        FROM daily d
        LEFT JOIN stock_basic sb ON d.ts_code = sb.ts_code
        WHERE d.trade_date = {date}
        ORDER BY d.pct_chg DESC
    """).fetchall()
    return [
        {
            "ts_code":   r[0],
            "name":      r[1],
            "industry":  r[2],
            "close":     r[3],
            "pct_chg":   r[4],
            "vol":       r[5],
            "amount":    r[6],
            "open":      r[7],
            "high":      r[8],
            "low":       r[9],
            "pre_close": r[10],
        }
        for r in rows
    ]
