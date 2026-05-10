# a_share_system/web/api/signals.py
import json
import duckdb
from fastapi import APIRouter, Query

router = APIRouter()
_con: duckdb.DuckDBPyConnection = None


def set_conn(con: duckdb.DuckDBPyConnection):
    global _con
    _con = con


@router.get("/api/signals/{date}")
def get_signals(date: int, strategy: str = Query(default="ALL")):
    where = f"sig.trade_date = {date}"
    if strategy != "ALL":
        where += f" AND sig.strategy = '{strategy}'"

    rows = _con.execute(f"""
        SELECT sig.ts_code,
               COALESCE(sb.name, sig.ts_code) AS name,
               sig.strategy, sig.score, sig.triggered,
               sig.pct_chg, sig.vol_ratio, sig.boards
        FROM signals sig
        LEFT JOIN stock_basic sb ON sig.ts_code = sb.ts_code
        WHERE {where}
        ORDER BY sig.score DESC
    """).fetchall()

    return [
        {
            "ts_code":   r[0],
            "name":      r[1],
            "strategy":  r[2],
            "score":     r[3],
            "triggered": json.loads(r[4]) if r[4] else [],
            "pct_chg":   r[5],
            "vol_ratio": r[6],
            "boards":    r[7],
        }
        for r in rows
    ]
