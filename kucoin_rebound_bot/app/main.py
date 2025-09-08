from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os, json, asyncio, time, httpx
from notifier import TelegramNotifier
from kucoin_client import get_top_usdt_symbols, get_klines
from features import df_from_candles
from rules import all_four_confirm

APP_VERSION = "0.1.5"

import os as _os
app = FastAPI(title="KuCoin Rebound Bot", root_path=_os.environ.get("INGRESS_ENTRY",""))
START_TS = time.time()
STATE = {"last_signal_ts": {}, "scans": 0}

def _options_path(): return "/data/options.json"
def _user_cfg_path(): return "/data/user_config.json"

def _read_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def _merged_options():
    # base options from Supervisor + user overrides
    opts = _read_json(_options_path(), {})
    ucfg = _read_json(_user_cfg_path(), {})
    m = dict(opts or {})
    m.update(ucfg or {})
    return m

def _defaults_params():
    return {
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9, "macd_hist_contract_bars": 2,
        "ema_fast": 5, "ema_mid": 10, "ema_body_max_atr_mult": 1.8,
        "rsi_length": 14, "rsi_oversold": 30, "rsi_confirm_15m": False,
        "vol_lookback": 20, "vol_boost_mult": 1.4, "green_share_lookback": 10, "green_share_min": 0.6,
        "tp1_pct": 0.007, "tp2_pct": 0.012, "tp3_pct": 0.020
    }

def _merged_params():
    m = _merged_options()
    d = _defaults_params()
    for k in d.keys():
        if k in m:
            d[k] = m[k]
    return d

async def tg_send(text: str):
    o = _merged_options()
    tg = TelegramNotifier(o.get("telegram_token",""), o.get("telegram_chat_id",""))
    if tg.ready():
        try:
            ok = await tg.send(text)
            return ok
        except Exception as e:
            print("[tg] send error:", e)
    return False

async def tg_long_poll():
    o = _merged_options()
    token = (o.get("telegram_token") or "").strip()
    allowed = str(o.get("telegram_chat_id") or "").strip()
    if not token:
        print("[tg] token not configured; long-poll disabled")
        return
    url = f"https://api.telegram.org/bot{token}"
    offset = 0
    print("[tg] long-poll started")
    while True:
        try:
            async with httpx.AsyncClient(timeout=35) as c:
                r = await c.get(f"{url}/getUpdates", params={"timeout": 30, "offset": offset})
                data = r.json()
                if not data.get("ok"):
                    await asyncio.sleep(2); continue
                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    msg = upd.get("message") or {}
                    chat = msg.get("chat",{})
                    text = (msg.get("text") or "").strip()
                    chat_id = str(chat.get("id") or "")
                    if allowed and chat_id != allowed:
                        continue
                    if text == "/ping":
                        await tg_send("pong")
                    elif text == "/status":
                        o = _merged_options()
                        st = {
                            "version": APP_VERSION,
                            "uptime_s": int(time.time()-START_TS),
                            "quote": o.get("symbols_quote"),
                            "top_n_by_volume": o.get("top_n_by_volume"),
                            "cooldown_minutes": o.get("cooldown_minutes"),
                            "scans": STATE["scans"]
                        }
                        await tg_send("<b>Status</b>\n" + json.dumps(st, ensure_ascii=False, indent=2))
        except Exception as e:
            print("[tg] poll error:", e)
            await asyncio.sleep(3)

async def scanner_loop():
    while True:
        try:
            o = _merged_options()
            p = _merged_params()
            top_n = int(o.get("top_n_by_volume", 120) or 120)
            min_vol = int(o.get("min_vol_24h_usd", 5_000_000) or 5_000_000)
            cooldown_min = int(o.get("cooldown_minutes", 20) or 20)
            symbols = await get_top_usdt_symbols(top_n, min_vol)
            if not symbols:
                await asyncio.sleep(30); continue

            for sym in symbols:
                try:
                    c5 = await get_klines(sym, "5m", 200)
                    c15 = await get_klines(sym, "15m", 200)
                    c1h = await get_klines(sym, "1h", 200)
                    df5 = df_from_candles(c5); df15 = df_from_candles(c15); df1h = df_from_candles(c1h)
                    ok, details = all_four_confirm(
                        df5, df15, df1h,
                        macd_fast=int(p["macd_fast"]), macd_slow=int(p["macd_slow"]), macd_signal=int(p["macd_signal"]), macd_hist_contract_bars=int(p["macd_hist_contract_bars"]),
                        ema_fast=int(p["ema_fast"]), ema_mid=int(p["ema_mid"]), ema_body_max_atr_mult=float(p["ema_body_max_atr_mult"]),
                        rsi_length=int(p["rsi_length"]), rsi_oversold=int(p["rsi_oversold"]), rsi_confirm_15m=bool(p["rsi_confirm_15m"]),
                        vol_lookback=int(p["vol_lookback"]), vol_boost_mult=float(p["vol_boost_mult"]), green_share_lookback=int(p["green_share_lookback"]), green_share_min=float(p["green_share_min"])
                    )
                    if not ok:
                        continue
                    last_ts = STATE["last_signal_ts"].get(sym, 0)
                    if time.time() - last_ts < cooldown_min*60:
                        continue
                    last_price = df5['close'].iloc[-1]
                    sl = float(df5['low'].iloc[-20:].min())
                    tp1 = last_price * (1 + float(p["tp1_pct"]))
                    tp2 = last_price * (1 + float(p["tp2_pct"]))
                    tp3 = last_price * (1 + float(p["tp3_pct"]))
                    text = f"🟢 {sym}\nEntry: {last_price:.6f}\nSL: {sl:.6f}\nTP1: {tp1:.6f}\nTP2: {tp2:.6f}\nTP3: {tp3:.6f}"
                    await tg_send(text)
                    STATE["last_signal_ts"][sym] = time.time()
                except Exception as se:
                    print("[scan] error on", sym, se)
            STATE["scans"] += 1
            await asyncio.sleep(60)
        except Exception as e:
            print("[scan] loop error", e)
            await asyncio.sleep(10)

@app.get("/", response_class=HTMLResponse)
def home():
    ui = "/app/ui.html"
    if os.path.exists(ui):
        with open(ui, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>KuCoin Rebound Bot</h1>"

@app.get("/health")
def health():
    o = _merged_options()
    p = _merged_params()
    return {"ok": True, "version": APP_VERSION, "uptime_s": int(time.time()-START_TS), "has_tg": bool(o.get("telegram_token") and o.get("telegram_chat_id")), "scans": STATE["scans"], "params": p}

@app.get("/api/status")
def api_status():
    o = _merged_options()
    status = {
        "version": APP_VERSION,
        "uptime_s": int(time.time()-START_TS),
        "quote": o.get("symbols_quote"),
        "top_n_by_volume": o.get("top_n_by_volume"),
        "cooldown_minutes": o.get("cooldown_minutes"),
        "scans": STATE["scans"]
    }
    return status

@app.get("/api/get_config")
def api_get_config():
    return _merged_params()

@app.post("/api/set_config")
async def api_set_config(req: Request):
    data = await req.json()
    # persist to /data/user_config.json
    cur = _read_json(_user_cfg_path(), {})
    cur.update(data or {})
    try:
        with open(_user_cfg_path(), "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}

@app.post("/api/ping")
async def api_ping():
    ok = await tg_send("pong")
    return {"ok": ok}

@app.on_event("startup")
async def on_start():
    await tg_send(f"✅ KuCoin Rebound Bot started (v{APP_VERSION})")
    asyncio.create_task(tg_long_poll())
    asyncio.create_task(scanner_loop())
