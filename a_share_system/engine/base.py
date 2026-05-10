# a_share_system/engine/base.py
import duckdb
from abc import ABC, abstractmethod
from a_share_system.engine.signal import Signal


class BaseStrategy(ABC):
    name: str
    display_name: str

    @abstractmethod
    def scan(self, con: duckdb.DuckDBPyConnection,
             trade_date: int) -> list[Signal]:
        ...
