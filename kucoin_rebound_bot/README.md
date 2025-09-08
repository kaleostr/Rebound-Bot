# KuCoin Rebound Signal Bot (Ingress)

Home Assistant add-on that scans KuCoin spot market for rebound setups using **strict 4/4** confirmations:
1) MACD: red histogram contracts, DIF → DEA
2) EMA: price reclaimed EMA5 and moves toward EMA10
3) RSI: exits oversold
4) Volume: rising green volume

Telegram:
- on startup sends ✅ message
- supports `/ping` and `/status`
- sends signals only when 4/4 are true

Web UI:
- Open via *Open Web UI* (Ingress). No external port exposed.
- Edit indicator params (stored in `/data/user_config.json`).

## Config (Supervisor options)
- `telegram_token` (string)
- `telegram_chat_id` (string)
- `min_vol_24h_usd` (int, default 5_000_000)
- `cooldown_minutes` (int, default 20)
- `symbols_quote` (string, default `USDT`)
- `top_n_by_volume` (int, default 120)
- `timezone` (string)

