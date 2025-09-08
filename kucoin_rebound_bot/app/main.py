from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os, json, asyncio, time
from notifier import TelegramNotifier

APP_VERSION = "0.1.2"

app = FastAPI(title="KuCoin Rebound Bot")

START_TS = time.time()

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

def get_options():
    # options.json (Supervisor) has base config
    opts = _read_json(_options_path(), {})
    # user_config.json (UI) can override fields later (not used yet)
    ucfg = _read_json(_user_cfg_path(), {})
    merged = {**opts, **ucfg}
    return merged

@app.get("/", response_class=HTMLResponse)
def home():
    ui = "/app/ui.html"
    if os.path.exists(ui):
        with open(ui, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>KuCoin Rebound Bot</h1>"

@app.get("/health")
def health():
    o = get_options()
    return {"ok": True, "version": APP_VERSION, "uptime_s": int(time.time()-START_TS), "has_tg": bool(o.get("telegram_token") and o.get("telegram_chat_id"))}

@app.get("/api/status")
def api_status():
    o = get_options()
    status = {
        "version": APP_VERSION,
        "uptime_s": int(time.time()-START_TS),
        "quote": o.get("symbols_quote"),
        "top_n_by_volume": o.get("top_n_by_volume"),
        "cooldown_minutes": o.get("cooldown_minutes"),
    }
    return status

@app.post("/api/ping")
async def api_ping():
    o = get_options()
    tg = TelegramNotifier(o.get("telegram_token",""), o.get("telegram_chat_id",""))
    ok = await tg.send("pong")
    return {"ok": ok}

@app.on_event("startup")
async def on_start():
    # Send startup message if Telegram configured
    o = get_options()
    tg = TelegramNotifier(o.get("telegram_token",""), o.get("telegram_chat_id",""))
    if tg.ready():
        await tg.send("✅ KuCoin Rebound Bot started (v%s)" % APP_VERSION)
