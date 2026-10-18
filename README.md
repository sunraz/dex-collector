# DEX collector (research only)
Runs on GitHub Actions every 15 minutes, free, no server. Each run appends a snapshot of new and trending pools on 8 networks
(Ethereum, BSC, Solana, Base, Arbitrum, Polygon, Avalanche, Optimism) to data/dex_snapshots.jsonl and logs the run in data/runs.log.
Fields: ts, src, net, addr, name, created, liq, vol_m5/h1/h6/h24, chg_h1/h24, tx_h1_buys/sells, fdv.
Public repos get unlimited Actions minutes. Private repos get 2,000 free min/month; each run is ~3 min, so ~96 runs/day is NOT free for private. Use a public repo.


## Breakout detector (detector.py)
Runs right after the collector in the same job. Flags pools where last-hour volume is >=3.5x the prior 5h average, price is up >=2.5% in the hour, buys >=50%, liquidity >=$25k. Writes data/alerts.jsonl and, 3-12h later, fills followup_chg so we can measure whether the rule has any edge. Research only, not advice.
