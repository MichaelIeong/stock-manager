#!/usr/bin/env python3
"""缺口回補難度模型 — 帶每月加倉（月供）的複利試算。

⚠️ 為何要獨立腳本：
用固定本金算「需要 X% 報酬」是錯的——每月加倉 20,000 之後本金逐月變大，
而且新加的錢只賺到剩餘月份的回報。本腳本用月度迭代模型：

    V0 = 起始投資本金
    每月：V = V * (1 + r) + C      （C 於月末投入，保守假設）
    投資收益 = V_n − (V0 + n × C)   ← 只算賺到的，本金不算回補

兩個方向都算：
  1. 逆解：要達成目標收益，需要幾多月報酬率 r（二分法求解）
  2. 正推：假設年化報酬 a%，5 個月能賺幾多、幾時掂到目標

用法：
    python3 scripts/recovery.py                      # 用預設值
    python3 scripts/recovery.py --capital 0 --monthly 0 --months 5
    python3 scripts/recovery.py --cash 0             # 現金閒置版（不投入市場）
    python3 scripts/recovery.py --start-of-month     # 月供改為月初投入
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deficit import FLOOR_TARGET, HALF_TARGET, TOTAL_DEFICIT  # noqa: E402

# ── 預設假設（2026-08-06 基準） ──
DEFAULT_CAPITAL = 0.0  # 模板預設值
DEFAULT_MONTHLY = 0.0  # 模板預設值
DEFAULT_MONTHS = 5           # 8–12 月


def final_value(capital: float, monthly: float, months: int,
                r: float, start_of_month: bool = False) -> float:
    """月度迭代：月供於月末（預設）或月初投入。"""
    v = capital
    for _ in range(months):
        if start_of_month:
            v = (v + monthly) * (1 + r)
        else:
            v = v * (1 + r) + monthly
    return v


def gain(capital: float, monthly: float, months: int,
         r: float, start_of_month: bool = False) -> float:
    """投資收益 = 期末市值 − 累計投入本金。"""
    invested = capital + monthly * months
    return final_value(capital, monthly, months, r, start_of_month) - invested


def solve_monthly_rate(target: float, capital: float, monthly: float,
                       months: int, start_of_month: bool = False) -> float:
    """二分法逆解：要賺到 target，需要幾多月報酬率。"""
    lo, hi = -0.5, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if gain(capital, monthly, months, mid, start_of_month) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def avg_capital(capital: float, monthly: float, months: int,
                start_of_month: bool = False) -> float:
    """時間加權平均在倉本金（衡量「實際攤幾多錢落場」）。"""
    total = 0.0
    v = capital
    for _ in range(months):
        if start_of_month:
            v += monthly
            total += v
        else:
            total += v
            v += monthly
    return total / months


def months_to_target(target: float, capital: float, monthly: float,
                     annual: float, cap_months: int = 60,
                     start_of_month: bool = False) -> int | None:
    """假設年化 annual，持續月供，幾多個月先賺夠 target。"""
    r = (1 + annual) ** (1 / 12) - 1
    for n in range(1, cap_months + 1):
        if gain(capital, monthly, n, r, start_of_month) >= target:
            return n
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="缺口回補難度模型（帶月供）")
    ap.add_argument("--capital", type=float, default=DEFAULT_CAPITAL,
                    help="起始投資本金（HKD），預設 279,872")
    ap.add_argument("--monthly", type=float, default=DEFAULT_MONTHLY,
                    help="每月加倉（HKD），預設 20,000")
    ap.add_argument("--months", type=int, default=DEFAULT_MONTHS,
                    help="剩餘月數，預設 5")
    ap.add_argument("--cash", type=float, default=0.0,
                    help="閒置現金（不投入市場，從本金扣除）")
    ap.add_argument("--start-of-month", action="store_true",
                    help="月供改為月初投入（較樂觀）")
    a = ap.parse_args()

    cap = a.capital - a.cash
    som = a.start_of_month
    timing = "月初" if som else "月末"
    invested_end = cap + a.monthly * a.months
    avg = avg_capital(cap, a.monthly, a.months, som)

    print("━" * 70)
    print("🎯 缺口回補難度模型（帶每月加倉）")
    print("━" * 70)
    print(f"  起始投資本金:   HK${cap:>12,.0f}"
          + (f"   （已扣閒置現金 {a.cash:,.0f}）" if a.cash else ""))
    print(f"  每月加倉:       HK${a.monthly:>12,.0f}  × {a.months} 個月"
          f"（{timing}投入）")
    print(f"  期末累計本金:   HK${invested_end:>12,.0f}")
    print(f"  時間加權平均在倉本金: HK${avg:>12,.0f}   ← 報酬率的實際分母")
    print()

    print("── 逆解：達成目標所需報酬率 ──")
    print(f"  {'目標':<14}{'金額':>10}{'月報酬':>10}{'期內累計':>10}"
          f"{'年化':>10}{'期末市值':>14}")
    print("-" * 70)
    for name, tgt in [("硬下限", FLOOR_TARGET), ("缺口一半", HALF_TARGET),
                      ("全額缺口", TOTAL_DEFICIT)]:
        r = solve_monthly_rate(tgt, cap, a.monthly, a.months, som)
        cum = (1 + r) ** a.months - 1
        ann = (1 + r) ** 12 - 1
        fv = final_value(cap, a.monthly, a.months, r, som)
        print(f"  {name:<14}{tgt:>10,.0f}{r*100:>9.2f}%{cum*100:>9.1f}%"
              f"{ann*100:>9.1f}%{fv:>14,.0f}")
    print()

    print(f"── 正推：假設年化報酬，{a.months} 個月賺幾多 ──")
    print(f"  {'年化':>8}{'期內收益':>12}{'達硬下限':>12}{'達一半':>12}"
          f"{'期末市值':>14}")
    print("-" * 70)
    for ann in [0.05, 0.08, 0.12, 0.15, 0.20, 0.30, 0.40]:
        r = (1 + ann) ** (1 / 12) - 1
        g = gain(cap, a.monthly, a.months, r, som)
        fv = final_value(cap, a.monthly, a.months, r, som)
        m_floor = months_to_target(FLOOR_TARGET, cap, a.monthly, ann,
                                   start_of_month=som)
        m_half = months_to_target(HALF_TARGET, cap, a.monthly, ann,
                                  start_of_month=som)
        f_txt = f"{m_floor} 個月" if m_floor else ">5年"
        h_txt = f"{m_half} 個月" if m_half else ">5年"
        print(f"  {ann*100:>7.0f}%{g:>+12,.0f}{f_txt:>12}{h_txt:>12}{fv:>14,.0f}")
    print()
    print("  註：「達硬下限／達一半」= 由今日起持續月供，需要幾多個月先賺夠"
          "（可超過年底）。")
    print("━" * 70)


if __name__ == "__main__":
    main()
