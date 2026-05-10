# a_share_system/tests/test_signal.py
import json
from a_share_system.engine.signal import Signal


def test_signal_defaults():
    s = Signal(ts_code="600111.SH", name="北方稀土",
               trade_date=20260508, strategy="LIMIT_UP",
               score=85.0, pct_chg=9.98, vol_ratio=3.2)
    assert s.boards == 0
    assert s.triggered == []
    assert s.extra == {}


def test_signal_to_dict():
    s = Signal(ts_code="600111.SH", name="北方稀土",
               trade_date=20260508, strategy="LIMIT_UP",
               score=85.0, pct_chg=9.98, vol_ratio=3.2,
               boards=2, triggered=["LIMIT_UP", "VOLUME_SPIKE"])
    d = s.to_dict()
    assert d["ts_code"] == "600111.SH"
    assert d["boards"] == 2
    assert json.loads(d["triggered"]) == ["LIMIT_UP", "VOLUME_SPIKE"]
