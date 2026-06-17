# XAUUSD historical data — how to get it

The MT5 demo account exposes only ~3 months of M15 history, so we need
to import external XAUUSD data for the Phase B benchmark and Phase D
portfolio screen.

## Recommended sources

### Option 1 — HistData.com (free, no signup, easy)
- URL: https://www.histdata.com/download-free-forex-data/
- Format: **Generic ASCII**, **1 Minute Bars**, instrument **XAUUSD**
- Download year by year (2023, 2024, 2025), unzip each, you get files
  like `DAT_ASCII_XAUUSD_M1_2024.csv`.
- Drop them all in this folder (`python/data/raw_histdata/`).

### Option 2 — Dukascopy Historical Data Feed (free, signup)
- URL: https://www.dukascopy.com/swiss/english/marketwatch/historical/
- Instrument: **XAU/USD**, Period: **15 Min**, Format: **CSV**
- Date range: 2023-01-01 to today
- Save as `XAUUSD_M15_dukascopy.csv` in this folder.

## What this folder should contain when ready

```
python/data/
├── README.md                                (this file)
├── raw_histdata/                            (optional, if using HistData)
│   ├── DAT_ASCII_XAUUSD_M1_2023.csv
│   ├── DAT_ASCII_XAUUSD_M1_2024.csv
│   └── DAT_ASCII_XAUUSD_M1_2025.csv
└── XAUUSD_M15.csv                            (if Dukascopy direct M15)
```

## Once the CSV is in place

I'll add a small import script that:
1. Loads the CSV(s) via `quantumking.data.load_csv`.
2. Resamples M1 → M15 and M15 → H4 if needed.
3. Writes parquet caches: `XAUUSD_M15.parquet`, `XAUUSD_H4.parquet`.
4. Runs the MA_Trend benchmark.

Just tell me when the file is here and which source you used.
