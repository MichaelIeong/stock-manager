#!/usr/bin/env python3
"""缺口帳本 (Deficit Ledger) — 單一事實來源，與 deficits.md 同步。

回補定義：用**投資收益（持倉未實現 + 已實現盈利）**賺返缺口；
每月加倉嘅本金唔計入回補進度。

⚠️ 基準線（BASELINE）機制：
2026 缺口 17,538 已經係**扣埋 2026-08-06 當日全倉盈虧之後嘅淨數**，
即當日嘅投資收益 +15,415 已經內含喺缺口計算入面。
所以回補進度由 **2026-08-06 當日 0 起計**：
    回補進度 = 當前投資收益 − BASELINE_INCOME
賺多過基準線先算回補，跌返落基準線以下則進度為負。

用法：
    python3 scripts/deficit.py            # 只印帳本與目標
    python3 scripts/deficit.py 0          # 帶入當前投資收益，印回補進度
quotes.py 會 import 本檔的 TOTAL_DEFICIT / HALF_TARGET / FLOOR_TARGET / BASELINE_INCOME。
"""

import sys

# ── 歷年缺口（HKD） ──
DEFICITS = []  # 模板預設值（空白）— 請填入你自己的資料

TOTAL_DEFICIT = sum(d["amount"] for d in DEFICITS)
TOTAL_RECOVERED = sum(d["recovered"] for d in DEFICITS)
TOTAL_OUTSTANDING = TOTAL_DEFICIT - TOTAL_RECOVERED

HALF_TARGET = TOTAL_DEFICIT / 2   # 「回補一半」基準
FLOOR_TARGET = 0.0  # 模板預設值
MONTHS_LEFT = 0  # 模板預設值

# ── 回補進度基準線 ──
# 2026-08-06 當日投資收益（未實現 +14,083 + 已實現 +1,332），已內含於 17,538 缺口。
BASELINE_DATE = ""  # 模板預設值
BASELINE_INCOME = 0.0  # 模板預設值


def net_recovery(income: float) -> float:
    """扣除基準線後嘅淨回補額（消除浮點負零）。"""
    return round(income - BASELINE_INCOME, 2) + 0.0


def print_ledger() -> None:
    print("━" * 66)
    print("📕 缺口帳本 (Deficit Ledger)")
    print("━" * 66)
    print(f"  {'年度':<6}{'來源':<28}{'缺口':>12}{'未回補':>12}")
    print("-" * 66)
    for d in DEFICITS:
        out = d["amount"] - d["recovered"]
        print(f"  {d['year']:<8}{d['source']:<26}{d['amount']:>12,.0f}{out:>12,.0f}")
    print("-" * 66)
    print(f"  {'合計':<8}{'':<26}{TOTAL_DEFICIT:>12,.0f}{TOTAL_OUTSTANDING:>12,.0f}")
    print()
    print(f"  2026 年終目標：一半基準 {HALF_TARGET:,.0f} ｜ 硬下限 {FLOOR_TARGET:,.0f}")
    print(f"  進度基準線：{BASELINE_DATE} 投資收益 HK${BASELINE_INCOME:+,.0f} = 進度 0")


def print_progress(income: float) -> None:
    net = net_recovery(income)
    print()
    print("━" * 66)
    print("📈 回補進度（唔計加倉本金；由基準線起計）")
    print("━" * 66)
    print(f"  當前投資收益:  HK${income:>+12,.0f}")
    print(f"  基準線({BASELINE_DATE}): HK${BASELINE_INCOME:>+12,.0f}   ← 已計入 2026 缺口，進度 0")
    print(f"  淨回補額:      HK${net:>+12,.0f}")
    print("-" * 66)
    print(f"  對硬下限 {FLOOR_TARGET:>7,.0f}:  {net / FLOOR_TARGET * 100:>6.1f}%"
          f"   仲差 HK${max(FLOOR_TARGET - net, 0):>10,.0f}")
    print(f"  對一半   {HALF_TARGET:>7,.0f}:  {net / HALF_TARGET * 100:>6.1f}%"
          f"   仲差 HK${max(HALF_TARGET - net, 0):>10,.0f}")
    print(f"  對總缺口 {TOTAL_DEFICIT:>7,.0f}:  {net / TOTAL_DEFICIT * 100:>6.1f}%"
          f"   仲差 HK${max(TOTAL_DEFICIT - net, 0):>10,.0f}")
    if MONTHS_LEFT > 0:
        need = max(FLOOR_TARGET - net, 0)
        need_half = max(HALF_TARGET - net, 0)
        print(f"  → 距硬下限：8–12 月共 {MONTHS_LEFT} 個月，平均每月需賺 "
              f"HK${need / MONTHS_LEFT:,.0f}")
        print(f"  → 距一半　：平均每月需賺 HK${need_half / MONTHS_LEFT:,.0f}")


def main() -> None:
    print_ledger()
    if len(sys.argv) > 1:
        print_progress(float(sys.argv[1].replace(",", "")))


if __name__ == "__main__":
    main()
