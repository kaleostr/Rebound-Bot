import numpy as np
from features import macd_features, ema_series, rsi_series, sma_series

def all_four_confirm(df5, df15, df1h,
                     macd_fast=12, macd_slow=26, macd_signal=9, macd_hist_contract_bars=2,
                     ema_fast=5, ema_mid=10, ema_body_max_atr_mult=1.8,
                     rsi_length=14, rsi_oversold=30, rsi_confirm_15m=False,
                     vol_lookback=20, vol_boost_mult=1.4, green_share_lookback=10, green_share_min=0.6):
    # Returns True if all 4 conditions met on 5m (and optional 15m RSI confirm).
    if any([df.empty for df in (df5, df15, df1h)]):
        return False, {}

    feats = macd_features(df5, macd_fast, macd_slow, macd_signal)
    if not feats: return False, {}
    hist = feats['macd_hist']
    macd = feats['macd']
    sig = feats['macd_signal']
    if len(hist) < macd_hist_contract_bars + 2:
        return False, {}
    last = hist.iloc[-1]
    prev = hist.iloc[-2]
    cond_macd = (last > prev) and (last < 0.0) and (prev < 0.0)
    dif_last = abs(macd.iloc[-1] - sig.iloc[-1])
    dif_prev = abs(macd.iloc[-2] - sig.iloc[-2])
    cond_macd = cond_macd and (dif_last <= dif_prev)
    ok_bars = True
    if macd_hist_contract_bars >= 2:
        seq = hist.iloc[-macd_hist_contract_bars:]
        ok_bars = all((seq.iloc[i] > seq.iloc[i-1]) for i in range(1, len(seq))) and all(seq < 0.0)
    cond_macd = cond_macd and ok_bars

    ema5 = ema_series(df5, ema_fast)
    ema10 = ema_series(df5, ema_mid)
    close = df5['close']
    open_ = df5['open']
    crossed_up = (close.iloc[-1] > ema5.iloc[-1]) and (open_.iloc[-2] <= ema5.iloc[-2])
    dist_now = abs(close.iloc[-1] - ema10.iloc[-1])
    dist_prev = abs(close.iloc[-2] - ema10.iloc[-2])
    toward10 = (dist_now < dist_prev) or (close.iloc[-1] > ema10.iloc[-1])
    tr = (df5['high'] - df5['low'])
    atr = tr.rolling(14).mean().iloc[-1]
    body = abs(close.iloc[-1] - open_.iloc[-1])
    cond_ema = crossed_up and toward10 and (atr is not None and body <= ema_body_max_atr_mult * (atr if atr>0 else 1e-9))

    rsi5 = rsi_series(df5, rsi_length)
    cond_rsi5 = (rsi5.iloc[-2] < rsi_oversold) and (rsi5.iloc[-1] >= rsi_oversold)
    cond_rsi = cond_rsi5
    if rsi_confirm_15m:
        rsi15 = rsi_series(df15, rsi_length)
        cond_rsi = cond_rsi and ((rsi15.iloc[-1] >= rsi_oversold) or (rsi15.iloc[-2] < rsi_oversold and rsi15.iloc[-1] >= rsi_oversold))

    vol = df5['volume']
    avg_vol = vol.rolling(vol_lookback).mean().iloc[-1]
    green = (close > open_).astype(int)
    green_share = green.iloc[-green_share_lookback:].mean() if green_share_lookback>0 else 1.0
    cond_vol = (close.iloc[-1] > open_.iloc[-1]) and (vol.iloc[-1] > (avg_vol * vol_boost_mult if avg_vol>0 else vol.iloc[-1])) and (green_share >= green_share_min)

    details = {
        "cond_macd": bool(cond_macd),
        "cond_ema": bool(cond_ema),
        "cond_rsi": bool(cond_rsi),
        "cond_vol": bool(cond_vol)
    }
    ok = cond_macd and cond_ema and cond_rsi and cond_vol
    return ok, details
