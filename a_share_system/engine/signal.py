# a_share_system/engine/signal.py
import json
from dataclasses import dataclass, field


@dataclass
class Signal:
    ts_code:    str
    name:       str
    trade_date: int
    strategy:   str
    score:      float
    pct_chg:    float
    vol_ratio:  float
    boards:     int       = 0
    triggered:  list[str] = field(default_factory=list)
    extra:      dict      = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ts_code":    self.ts_code,
            "name":       self.name,
            "trade_date": self.trade_date,
            "strategy":   self.strategy,
            "score":      self.score,
            "pct_chg":    self.pct_chg,
            "vol_ratio":  self.vol_ratio,
            "boards":     self.boards,
            "triggered":  json.dumps(self.triggered, ensure_ascii=False),
            "extra":      json.dumps(self.extra, ensure_ascii=False),
        }
