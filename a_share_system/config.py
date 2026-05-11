# a_share_system/config.py
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DATA_ROOT = PROJECT_ROOT.parent / "tushare"
DB_PATH = PROJECT_ROOT / "market.duckdb"

TUSHARE_TOKEN = "a5482c79be93fad0aad0340890cc47a44e010cee27f25e8fdf5d5fb5"

# 指数代码
INDEX_CODES = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
}

# 策略参数
STRATEGY_PARAMS = {
    "LIMIT_UP": {"threshold": 9.5},
    "VOLUME_SPIKE": {"vol_ratio_min": 3.0, "pct_chg_min": 3.0},
    "MA_BREAKOUT": {"ma_short": 5, "ma_long": 10, "ma_trend": 60},
    "MACD_CROSS": {"ema_fast": 12, "ema_slow": 26, "signal": 9},
    "MACD_DIVERGENCE": {"lookback": 30, "local_window": 4},
    "CONSECUTIVE": {"min_boards": 2},
    "RESONANCE": {"min_strategies": 2},
    "BIG_MONEY": {"net_ratio_min": 0.08, "pct_min": 1.0, "amount_min": 5000},
    "PULLBACK":  {"limit_threshold": 9.5, "max_pullback": 0.15, "vol_shrink": 0.7,
                  "vol_expand": 1.3, "pct_today": 1.5},
}
