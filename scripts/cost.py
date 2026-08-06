#!/usr/bin/env python3
"""持倉加權平均成本計算。

用法：
    python3 scripts/cost.py <舊股數> <舊均價> <新股數> <新成交價>

範例：
    python3 scripts/cost.py 9 329.128 1 364.318
"""

import sys


def weighted_avg_cost(old_shares: float, old_avg: float,
                      new_shares: float, new_price: float) -> dict:
    """計算加倉後的加權平均成本。"""
    old_total = old_shares * old_avg
    new_total = new_shares * new_price
    total_shares = old_shares + new_shares
    total_cost = old_total + new_total
    new_avg = total_cost / total_shares

    return {
        "old_shares": old_shares,
        "old_avg": old_avg,
        "old_total": round(old_total, 3),
        "new_shares": new_shares,
        "new_price": new_price,
        "new_total": round(new_total, 3),
        "total_shares": total_shares,
        "total_cost": round(total_cost, 3),
        "new_avg": round(new_avg, 3),
    }


def fmt_shares(x: float) -> str:
    """整數股顯示為整數，碎股保留小數。"""
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def main():
    if len(sys.argv) != 5:
        print(f"用法: python3 {sys.argv[0]} <舊股數> <舊均價> <新股數> <新成交價>")
        sys.exit(1)

    try:
        old_shares = float(sys.argv[1])
        old_avg = float(sys.argv[2])
        new_shares = float(sys.argv[3])
        new_price = float(sys.argv[4])
    except ValueError:
        print("錯誤：四個參數都必須是數字")
        sys.exit(1)

    if old_shares < 0 or new_shares < 0:
        print("錯誤：股數不能為負數")
        sys.exit(1)
    if old_shares + new_shares == 0:
        print("錯誤：新舊股數合計不能為零")
        sys.exit(1)

    r = weighted_avg_cost(old_shares, old_avg, new_shares, new_price)

    print(f"原 {fmt_shares(r['old_shares'])} 股 × {r['old_avg']}     = {r['old_total']:,.3f}")
    print(f"新 {fmt_shares(r['new_shares'])} 股 × {r['new_price']}    = {r['new_total']:,.3f}")
    print(f"─────────────────────────────────")
    print(f"合計 {fmt_shares(r['total_shares'])} 股             = {r['total_cost']:,.3f}")
    print(f"加權均價                     = {r['new_avg']:,.3f}")


if __name__ == "__main__":
    main()
