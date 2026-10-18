#!/usr/bin/env python3
"""Breakout detector (research only, no trading, no advice).
Rule distilled from Quack AI (Q) 17/10: volume x12 vs prior hours in the same hour price moved +4..10%.
Catches the FIRST hour of a breakout, cannot predict ahead.
Appends alerts to data/alerts.jsonl and measures what earlier alerts did 3-12h later."""
import json, time, urllib.request, datetime, os

MIN_LIQ, MIN_MULT, MIN_CHG, MAX_CHG, MIN_BUY, MIN_TX = 25000, 3.5, 2.5, 120, 0.5, 25
ALERTS = "data/alerts.jsonl"

def get(url):
    for _ in range(2):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode())
        except Exception as e:
            if "429" in str(e): time.sleep(6)
            else: time.sleep(1)
    return None

def load():
    if not os.path.exists(ALERTS): return []
    return [json.loads(l) for l in open(ALERTS) if l.strip()]

def main():
    os.makedirs("data", exist_ok=True)
    now = datetime.datetime.utcnow()
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    old = load()
    recent_keys = {(a["net"], a["addr"]) for a in old if (now - datetime.datetime.strptime(a["ts"], "%Y-%m-%dT%H:%M:%SZ")).total_seconds() < 6 * 3600}

    toks = {}
    for ep in ("token-boosts/latest/v1", "token-boosts/top/v1", "token-profiles/latest/v1"):
        b = get("https://api.dexscreener.com/" + ep)
        for t in (b if isinstance(b, list) else [])[:40]:
            if t.get("chainId") and t.get("tokenAddress"): toks[(t["chainId"], t["tokenAddress"])] = 1
        time.sleep(0.4)

    hits, scanned = [], 0
    for (ch, addr) in list(toks)[:70]:
        r = get(f"https://api.dexscreener.com/tokens/v1/{ch}/{addr}"); time.sleep(0.25)
        if not isinstance(r, list) or not r: continue
        p = max(r, key=lambda x: (x.get("liquidity") or {}).get("usd", 0))
        scanned += 1
        liq = (p.get("liquidity") or {}).get("usd", 0)
        v, c, tx = p.get("volume") or {}, p.get("priceChange") or {}, ((p.get("txns") or {}).get("h1") or {})
        v1, v6 = v.get("h1", 0) or 0, v.get("h6", 0) or 0
        prior = max(0, v6 - v1) / 5
        mult = v1 / prior if prior > 0 else (99 if v1 > 0 else 0)
        buys, sells = tx.get("buys", 0) or 0, tx.get("sells", 0) or 0
        n = buys + sells; br = buys / n if n else 0
        chg = c.get("h1") or 0
        age = (time.time() * 1000 - p["pairCreatedAt"]) / 86400000 if p.get("pairCreatedAt") else 0
        if not (liq >= MIN_LIQ and mult >= MIN_MULT and MIN_CHG <= chg <= MAX_CHG and br >= MIN_BUY and n >= MIN_TX): continue
        if (p["chainId"], p["pairAddress"]) in recent_keys: continue
        score = round(min(40, mult * 2.5) + min(25, chg * 1.2) + min(15, (br - .5) * 60) + min(20, __import__("math").log10(liq / MIN_LIQ + 1) * 20))
        hits.append({"ts": ts, "net": p["chainId"], "addr": p["pairAddress"], "name": f'{p["baseToken"]["symbol"]}/{p["quoteToken"]["symbol"]}',
                     "liq": round(liq), "price": p.get("priceUsd"), "chg_h1": chg, "vol_mult": round(mult, 1), "buy_ratio": round(br, 2),
                     "age_d": round(age, 1), "score": score, "url": p.get("url"), "followup_chg": None,
                     "risk": "very new pair, high rug risk" if age < 1 else ""})
    hits.sort(key=lambda h: -h["score"])

    # follow-up on alerts 3-12h old
    changed = False
    for a in old:
        age_h = (now - datetime.datetime.strptime(a["ts"], "%Y-%m-%dT%H:%M:%SZ")).total_seconds() / 3600
        if a.get("followup_chg") is None and a.get("price") and 3 < age_h < 12:
            r = get(f'https://api.dexscreener.com/latest/dex/pairs/{a["net"]}/{a["addr"]}'); time.sleep(0.25)
            cur = ((r or {}).get("pairs") or [{}])[0].get("priceUsd")
            if cur and float(a["price"]) > 0:
                a["followup_chg"] = round((float(cur) / float(a["price"]) - 1) * 100, 1); changed = True
    if hits or changed:
        with open(ALERTS, "w") as f:
            for a in old + hits: f.write(json.dumps(a, ensure_ascii=False) + "\n")
    with open("data/detector_runs.log", "a") as f:
        f.write(f"{ts} scanned={scanned} new_alerts={len(hits)}\n")
    for h in hits: print("ALERT", h["score"], h["name"], h["net"], h["url"])
    print("scanned", scanned, "alerts", len(hits))

main()
