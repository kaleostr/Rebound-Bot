from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os, json, asyncio, time, httpx
from notifier import TelegramNotifier
from kucoin_client import get_top_usdt_symbols, get_klines
from features import df_from_candles
from rules import all_four_confirm

APP_VERSION = "0.1.4"

app = FastAPI(title="KuCoin Rebound Bot")
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
    opts = _read_json(_options_path(), {})
    ucfg = _read_json(_user_cfg_path(), {})
    m = dict(opts or {})
    m.update(ucfg or {})
    return m

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
                    from features import df_from_candles
                    df5 = df_from_candles(c5); df15 = df_from_candles(c15); df1h = df_from_candles(c1h)
                    ok, details = all_four_confirm(df5, df15, df1h)
                    if not ok:
                        continue
                    last_ts = STATE["last_signal_ts"].get(sym, 0)
                    if time.time() - last_ts < cooldown_min*60:
                        continue
                    last_price = df5['close'].iloc[-1]
                    sl = float(df5['low'].iloc[-20:].min())
                    tp1 = last_price * (1 + 0.007)
                    tp2 = last_price * (1 + 0.012)
                    tp3 = last_price * (1 + 0.020)
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
    return {"ok": True, "version": APP_VERSION, "uptime_s": int(time.time()-START_TS), "has_tg": bool(o.get("telegram_token") and o.get("telegram_chat_id")), "scans": STATE["scans"]}

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

@app.post("/api/ping")
async def api_ping():
    ok = await tg_send("pong")
    return {"ok": ok}

@app.on_event("startup")
async def on_start():
    await tg_send(f"✅ KuCoin Rebound Bot started (v{APP_VERSION})")
    asyncio.create_task(tg_long_poll())
    asyncio.create_task(scanner_loop())
