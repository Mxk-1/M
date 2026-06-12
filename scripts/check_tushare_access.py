"""验证 2000 积分下各接口的可用性。"""
import os
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)

import tushare as ts

TOKEN = "a5482c79be93fad0aad0340890cc47a44e010cee27f25e8fdf5d5fb5"
pro = ts.pro_api(TOKEN)

TESTS = [
    # (接口名, 调用方式, 说明)
    ("adj_factor",       lambda: pro.adj_factor(ts_code="000001.SZ", start_date="20260101", end_date="20260110"),       "复权因子"),
    ("pro_bar(前复权)",  lambda: pro.pro_bar(ts_code="000001.SZ", adj="qfq", start_date="20260101", end_date="20260110"), "前复权行情"),
    ("daily_basic",      lambda: pro.daily_basic(trade_date="20260509"),                                                 "每日PE/PB/市值"),
    ("income",           lambda: pro.income(ts_code="000001.SZ", start_date="20250101", end_date="20260101"),            "利润表"),
    ("fina_indicator",   lambda: pro.fina_indicator(ts_code="000001.SZ", start_date="20250101", end_date="20260101"),    "财务指标ROE等"),
    ("index_classify",   lambda: pro.index_classify(level="L1", src="SW2021"),                                          "申万行业分类"),
    ("sw_daily",         lambda: pro.sw_daily(ts_code="801010.SI", start_date="20260501", end_date="20260510"),          "申万行业指数日行情"),
    ("stk_holdernumber", lambda: pro.stk_holdernumber(ts_code="000001.SZ", start_date="20250101", end_date="20260101"), "股东户数"),
    ("moneyflow_hsgt",   lambda: pro.moneyflow_hsgt(start_date="20260501", end_date="20260510"),                        "北向资金"),
    ("limit_step",       lambda: pro.limit_step(trade_date="20260509"),                                                 "连板天梯"),
    ("cyq_perf",         lambda: pro.cyq_perf(ts_code="000001.SZ", start_date="20260501", end_date="20260510"),         "筹码胜率"),
    ("stk_factor_pro",   lambda: pro.stk_factor_pro(ts_code="000001.SZ", start_date="20260501", end_date="20260510"),   "技术面因子(专业版)"),
    ("hm_detail",        lambda: pro.hm_detail(trade_date="20260509"),                                                  "游资明细"),
]

print(f"{'接口':<22} {'状态':<8} {'行数':<8} 说明")
print("-" * 65)

for name, fn, desc in TESTS:
    try:
        df = fn()
        if df is None or df.empty:
            print(f"{name:<22} {'⚠ 空结果':<10} {'-':<8} {desc}")
        else:
            print(f"{name:<22} {'✅ OK':<10} {len(df):<8} {desc}")
    except Exception as e:
        err = str(e)[:50]
        print(f"{name:<22} {'❌ 失败':<10} {'-':<8} {desc}  [{err}]")
