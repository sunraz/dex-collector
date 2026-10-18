#!/usr/bin/env python3
# DEX snapshot, one per run (GitHub Actions, every 15 min). Research only.
# Base layer = DexScreener (stable, no key): boosted/profiled tokens + pairs for a rotating seed list -> per-pair liquidity, volume m5/h1/h6/h24, price change, txns, age.
# Extra layer = GeckoTerminal new/trending pools; best effort (heavily rate-limited), never fails the run.
import json, urllib.request, time, datetime as dt, os, sys
UA={"User-Agent":"Mozilla/5.0","Accept":"application/json"}
OUT="data/dex_snapshots.jsonl"; LOG="data/runs.log"
ts=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
st={"ds_calls":0,"ds_err":0,"gt_calls":0,"gt_err":0}
def get(u,kind,retries=2):
    for i in range(retries+1):
        st[kind+"_calls"]+=1
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=30).read().decode())
        except urllib.error.HTTPError as e:
            st[kind+"_err"]+=1
            if e.code==429 and kind=="ds": time.sleep(15); continue
            return None
        except Exception: st[kind+"_err"]+=1; time.sleep(2)
    return None
rows=[]; seen=set()
def pair_row(p,src):
    k=(p.get("chainId"),p.get("pairAddress"))
    if k in seen or not p.get("pairAddress"): return
    seen.add(k); v=p.get("volume") or {}; c=p.get("priceChange") or {}; tx=p.get("txns") or {}; h1=tx.get("h1") or {}
    rows.append(dict(ts=ts,src=src,net=p.get("chainId"),dex=p.get("dexId"),addr=p.get("pairAddress"),name=(p.get("baseToken") or {}).get("symbol","")+"/"+(p.get("quoteToken") or {}).get("symbol",""),
        token=(p.get("baseToken") or {}).get("address"),created_ms=p.get("pairCreatedAt"),liq=(p.get("liquidity") or {}).get("usd") or 0,
        vol_m5=v.get("m5") or 0,vol_h1=v.get("h1") or 0,vol_h6=v.get("h6") or 0,vol_h24=v.get("h24") or 0,chg_m5=c.get("m5"),chg_h1=c.get("h1"),chg_h6=c.get("h6"),chg_h24=c.get("h24"),
        tx_h1_buys=h1.get("buys"),tx_h1_sells=h1.get("sells"),fdv=p.get("fdv") or 0,price=p.get("priceUsd")))
# 1) tokens being boosted / newly profiled, then resolve each to its pairs
toks=[]
for ep,src in (("token-boosts/latest/v1","ds_boost"),("token-boosts/top/v1","ds_boost_top"),("token-profiles/latest/v1","ds_profile")):
    b=get("https://api.dexscreener.com/"+ep,"ds")
    for t in (b if isinstance(b,list) else [])[:30]: toks.append((t.get("chainId"),t.get("tokenAddress"),src))
    time.sleep(1.2)
bytok={}
for ch,addr,src in toks:
    if addr and (ch,addr) not in bytok: bytok[(ch,addr)]=src
for (ch,addr),src in list(bytok.items())[:60]:
    r=get("https://api.dexscreener.com/tokens/v1/%s/%s"%(ch,addr),"ds")
    for p in (r if isinstance(r,list) else [])[:3]: pair_row(p,src)
    time.sleep(0.5)
# 2) rotating search seeds for broad coverage of active pairs
SEEDS=["WETH","SOL","USDC","USDT","BNB","PEPE","DOGE","SHIB","AI","MEME","CAT","TRUMP","BASE","BONK","WIF","PUMP"]
slot=(int(ts[11:13])*4+int(ts[14:16])//15)%4
for q in SEEDS[slot*4:slot*4+4]:
    r=get("https://api.dexscreener.com/latest/dex/search?q="+q,"ds")
    for p in (r or {}).get("pairs",[])[:30]: pair_row(p,"ds_search")
    time.sleep(0.5)
n_ds=len(rows)
# 3) GeckoTerminal: best effort, 4 calls max, never fatal
for u,src in (("https://api.geckoterminal.com/api/v2/networks/new_pools?page=1","gt_new_all"),("https://api.geckoterminal.com/api/v2/networks/trending_pools?page=1","gt_trending_all")):
    r=get(u,"gt",retries=0)
    for p in (r or {}).get("data",[]):
        a=p["attributes"]; v=a.get("volume_usd") or {}; c=a.get("price_change_percentage") or {}
        rows.append(dict(ts=ts,src=src,net=p["id"].split("_")[0],addr=a.get("address"),name=a.get("name"),created=a.get("pool_created_at"),liq=float(a.get("reserve_in_usd") or 0),
            vol_m5=float(v.get("m5") or 0),vol_h1=float(v.get("h1") or 0),vol_h6=float(v.get("h6") or 0),vol_h24=float(v.get("h24") or 0),chg_h1=float(c.get("h1") or 0),chg_h24=float(c.get("h24") or 0),fdv=float(a.get("fdv_usd") or 0)))
    time.sleep(8)
os.makedirs("data",exist_ok=True)
with open(OUT,"a",encoding="utf-8") as f:
    for r in rows: f.write(json.dumps(r,ensure_ascii=False)+"\n")
line="%s rows=%d ds_rows=%d ds_calls=%d ds_err=%d gt_calls=%d gt_err=%d"%(ts,len(rows),n_ds,st["ds_calls"],st["ds_err"],st["gt_calls"],st["gt_err"])
open(LOG,"a").write(line+"\n"); print(line)
if n_ds<40: sys.exit(1)     # fail loudly if the stable base layer came back thin
