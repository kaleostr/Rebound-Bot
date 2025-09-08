from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
import os, json

app = FastAPI(title="KuCoin Rebound Bot")

def _options_path():
    return "/data/options.json"

def _user_cfg_path():
    return "/data/user_config.json"

def _read_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

@app.get("/")
def home():
    ui = "/app/ui.html"
    if os.path.exists(ui):
        with open(ui, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return JSONResponse({"ok": True, "msg": "KuCoin Rebound Bot v0.1.1 running"})

@app.get("/health")
def health():
    opts = _read_json(_options_path(), {})
    ucfg = _read_json(_user_cfg_path(), {})
    merged = {**opts, **ucfg}
    return {"ok": True, "options": merged}
