# a_share_system/data/news.py
from datetime import datetime, timezone
import duckdb


def save_news(con: duckdb.DuckDBPyConnection, items: list[dict]) -> int:
    """批量写入新闻，url 为主键，已存在则跳过。返回实际插入条数。"""
    if not items:
        return 0
    saved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [
        (
            item["url"],
            item.get("ts_code"),
            item.get("pub_date"),
            item["title"],
            item.get("source"),
            item.get("summary"),
            item.get("keyword"),
            saved_at,
        )
        for item in items
    ]
    con.executemany(
        """
        INSERT OR IGNORE INTO news
            (url, ts_code, pub_date, title, source, summary, keyword, saved_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    return len(rows)


def query_news(
    con: duckdb.DuckDBPyConnection,
    ts_code: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """按股票代码或关键字检索新闻，按发布日期倒序。"""
    sql = "SELECT url, ts_code, pub_date, title, source, summary, keyword, saved_at FROM news WHERE 1=1"
    params: list = []
    if ts_code:
        sql += " AND ts_code = ?"
        params.append(ts_code)
    if keyword:
        sql += " AND (title LIKE ? OR summary LIKE ? OR keyword LIKE ?)"
        like = f"%{keyword}%"
        params.extend([like, like, like])
    sql += " ORDER BY pub_date DESC, saved_at DESC LIMIT ?"
    params.append(limit)
    rows = con.execute(sql, params).fetchall()
    cols = ["url", "ts_code", "pub_date", "title", "source", "summary", "keyword", "saved_at"]
    return [dict(zip(cols, r)) for r in rows]
