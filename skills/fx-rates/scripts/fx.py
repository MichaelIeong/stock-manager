#!/usr/bin/env python3
"""实时汇率查询 — 从 open.er-api.com 拉取，免 API key。

用法：
    python3 skills/fx-rates/scripts/fx.py              # 默认输出 USD/CNY, USD/HKD, HKD/CNY
    python3 skills/fx-rates/scripts/fx.py EUR JPY       # 查任意货币对 (base=EUR, quote=JPY)
    python3 skills/fx-rates/scripts/fx.py all            # 输出全部主要货币
"""

import json
import sys
import urllib.request


API_URL = "https://open.er-api.com/v6/latest/USD"

# 默认输出的货币对
DEFAULT_PAIRS = [
    ("USD", "CNY"),
    ("USD", "HKD"),
    ("HKD", "CNY"),
]

# all 模式输出的主要货币
MAJOR_CURRENCIES = ["USD", "CNY", "HKD", "EUR", "JPY", "GBP", "KRW", "TWD", "SGD", "AUD"]


def fetch_rates() -> dict:
    """从 er-api.com 拉取以 USD 为基准的全部汇率。"""
    req = urllib.request.Request(API_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.load(resp)
    if "rates" not in data:
        raise RuntimeError(f"API 回傳異常: {data}")
    return data["rates"]


def convert(rates: dict, base: str, quote: str) -> float | None:
    """計算 base/quote 匯率（USD 為中介）。"""
    if base == "USD":
        return rates.get(quote)
    if quote == "USD":
        r = rates.get(base)
        return 1 / r if r else None
    # base → USD → quote
    base_to_usd = 1 / rates[base] if base in rates else None
    if base_to_usd is None:
        return None
    return base_to_usd * rates.get(quote, 0) or None


def fetch_fx():
    """供 quotes.py 調用，回傳 (usd_hkd, hkd_cny)。"""
    rates = fetch_rates()
    usd_hkd = rates.get("HKD")
    usd_cny = rates.get("CNY")
    hkd_cny = usd_cny / usd_hkd if (usd_hkd and usd_cny) else 0.8606
    return usd_hkd, hkd_cny


def main():
    rates = fetch_rates()
    update_time = "(latest)"

    if len(sys.argv) == 3:
        base, quote = sys.argv[1].upper(), sys.argv[2].upper()
        rate = convert(rates, base, quote)
        if rate:
            print(f"{base}/{quote} = {rate:.4f}")
        else:
            print(f"找不到 {base} 或 {quote}")
        return

    if len(sys.argv) > 1 and sys.argv[1] == "all":
        print(f"💱 主要貨幣匯率 {update_time}")
        print("-" * 40)
        for cur in MAJOR_CURRENCIES:
            if cur == "USD":
                continue
            r = rates.get(cur)
            if r:
                print(f"  USD/{cur} = {r:.4f}")
        # 交叉匯率
        print("-" * 40)
        hkd_cny = convert(rates, "HKD", "CNY")
        cny_hkd = convert(rates, "CNY", "HKD")
        eur_usd = convert(rates, "EUR", "USD")
        if hkd_cny: print(f"  HKD/CNY = {hkd_cny:.4f}")
        if cny_hkd: print(f"  CNY/HKD = {cny_hkd:.4f}")
        if eur_usd: print(f"  EUR/USD = {eur_usd:.4f}")
        return

    # 預設輸出
    print(f"💱 匯率 {update_time}")
    print("-" * 40)
    for base, quote in DEFAULT_PAIRS:
        rate = convert(rates, base, quote)
        if rate:
            inv = 1 / rate
            print(f"  {base}/{quote} = {rate:.4f}  ({quote}/{base} = {inv:.4f})")


if __name__ == "__main__":
    main()
