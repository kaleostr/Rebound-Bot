import pandas as pd
import numpy as np
import ta

def df_from_candles(candles):
    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(candles)
    df['time'] = pd.to_datetime(df['ts'], unit='ms')
    return df.set_index('time')

def macd_features(df, fast=12, slow=26, signal=9):
    out = {}
    if len(df) < slow + signal + 5:
        return out
    macd_ind = ta.trend.MACD(close=df['close'], window_fast=fast, window_slow=slow, window_sign=signal)
    macd = macd_ind.macd()
    macd_signal = macd_ind.macd_signal()
    hist = macd_ind.macd_diff()
    out['macd'] = macd
    out['macd_signal'] = macd_signal
    out['macd_hist'] = hist
    return out

def ema_series(df, period):
    return df['close'].ewm(span=period, adjust=False).mean()

def rsi_series(df, length=14):
    return ta.momentum.RSIIndicator(close=df['close'], window=length).rsi()

def sma_series(x, n):
    return x.rolling(n).mean()
