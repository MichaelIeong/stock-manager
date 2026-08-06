---
name: fx-rates
description: "Fetch live exchange rates (USD/CNY, USD/HKD, HKD/CNY) from open.er-api.com. Free, no API key required. Use when calculating cross-currency portfolio values or converting between HKD/USD/CNY."
description_zh: "實時汇率查询（美元/人民幣/港幣），免 API key，数据源 open.er-api.com"
version: 1.0.0
allowed-tools: Bash
---

# FX Rates — 實時汇率查询

## 概述

从 `open.er-api.com` 拉取最新汇率，支持任意貨幣對。免登入、免 API key。

## 使用方法

```bash
python3 skills/fx-rates/scripts/fx.py
```

預設輸出 USD/CNY、USD/HKD、HKD/CNY。可传參数查任意貨幣對：

```bash
python3 skills/fx-rates/scripts/fx.py EUR JPY    # 查 EUR/JPY
python3 skills/fx-rates/scripts/fx.py all         # 輸出全部主要貨幣對
```

## 集成

`scripts/quotes.py` 已调用此模塊的 `fetch_fx()` 函数自動拉取汇率。
