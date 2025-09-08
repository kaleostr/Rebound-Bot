import httpx

BASE = "https://api.kucoin.com"

async def fetch_json(client, url, params=None):
    r = await client.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

async def get_top_usdt_symbols(top_n=120, min_vol_usd=5_000_000):
    async with httpx.AsyncClient(timeout=20) as c:
        data = await fetch_json(c, f"{BASE}/api/v1/market/allTickers")
        items = (data.get("data") or {}).get("ticker", []) or []
        rows = []
        for it in items:
            sym = it.get("symbol")
            if not sym or not sym.endswith("-USDT"):
                continue
            try:
                vol_usd = float(it.get("volValue") or 0.0)
            except:
                vol_usd = 0.0
            if vol_usd >= min_vol_usd:
                rows.append((sym, vol_usd))
        rows.sort(key=lambda x: x[1], reverse=True)
        return [s for s,_ in rows[:top_n]]

TF_MAP = {"5m": "5min", "15m": "15min", "1h": "1hour"}

async def get_klines(symbol: str, tf: str, limit: int = 200):
    ktype = TF_MAP[tf]
    async with httpx.AsyncClient(timeout=20) as c:
        res = await fetch_json(c, f"{BASE}/api/v1/market/candles", params={"type": ktype, "symbol": symbol})
        arr = res.get("data") or []
        arr = list(reversed(arr))
        if len(arr) > limit:
            arr = arr[-limit:]
        candles = []
        for x in arr:
            ts, o, c_, h, l, v, *_ = x
            candles.append({
                "ts": int(float(ts))*1000,
                "open": float(o), "high": float(h), "low": float(l), "close": float(c_), "volume": float(v)
            })
        return candles
