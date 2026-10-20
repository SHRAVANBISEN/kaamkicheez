# indicators.py — Technical indicator calculator
# Input:  OHLCV DataFrame from data_fetcher.py
# Output: Clean dictionary of indicator values per stock

import pandas as pd
import pandas_ta as ta
from config import (
    RSI_PERIOD,
    EMA_SHORT, EMA_LONG,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    BB_PERIOD, BB_STD
)


# ── Core indicator calculator ──────────────────────────────

def calculate_indicators(df):
    if df is None or len(df) < 25:
        print(f"⚠️  Not enough candles "
              f"(got {len(df) if df is not None else 0}, need 25+)")
        return None

    symbol = df["symbol"].iloc[-1]

    try:
        # ── RSI ───────────────────────────────────────────
        df["rsi"] = ta.rsi(df["close"], length=RSI_PERIOD)

        # ── EMA ───────────────────────────────────────────
        df["ema9"]  = ta.ema(df["close"], length=EMA_SHORT)
        df["ema21"] = ta.ema(df["close"], length=EMA_LONG)

        # ── MACD ──────────────────────────────────────────
        macd_df = ta.macd(df["close"],
                          fast=MACD_FAST,
                          slow=MACD_SLOW,
                          signal=MACD_SIGNAL)

        if macd_df is None:
            print(f"⚠️  MACD returned None for {symbol} "
                  f"— need more candles (got {len(df)}, need 35+)")
            return None

        macd_cols       = macd_df.columns.tolist()
        macd_line_col   = [c for c in macd_cols if c.startswith("MACD_")][0]
        macd_signal_col = [c for c in macd_cols if c.startswith("MACDs_")][0]
        macd_hist_col   = [c for c in macd_cols if c.startswith("MACDh_")][0]

        df["macd"]        = macd_df[macd_line_col]
        df["macd_signal"] = macd_df[macd_signal_col]
        df["macd_hist"]   = macd_df[macd_hist_col]

        # ── Bollinger Bands ────────────────────────────────
        bb_df = ta.bbands(df["close"], length=BB_PERIOD, std=BB_STD)

        if bb_df is None:
            print(f"⚠️  BB returned None for {symbol}")
            return None

        bb_cols      = bb_df.columns.tolist()
        bb_upper_col = [c for c in bb_cols if c.startswith("BBU")][0]
        bb_mid_col   = [c for c in bb_cols if c.startswith("BBM")][0]
        bb_lower_col = [c for c in bb_cols if c.startswith("BBL")][0]

        df["bb_upper"] = bb_df[bb_upper_col]
        df["bb_mid"]   = bb_df[bb_mid_col]
        df["bb_lower"] = bb_df[bb_lower_col]

        # ── Extract latest row ─────────────────────────────
        latest = df.iloc[-1]

        # ── Derived signals ────────────────────────────────
        ema_crossover      = _check_ema_crossover(df)
        macd_crossover     = _check_macd_crossover(df)
        bb_position        = _check_bb_position(latest)
        preliminary_signal = _get_preliminary_signal(
            latest, ema_crossover, macd_crossover, bb_position
        )

        return {
            "symbol":    symbol,
            "timestamp": str(latest["timestamp"]),

            "open":   round(float(latest["open"]),  2),
            "high":   round(float(latest["high"]),  2),
            "low":    round(float(latest["low"]),   2),
            "close":  round(float(latest["close"]), 2),
            "volume": int(latest["volume"]),

            "rsi":      round(float(latest["rsi"]), 2),
            "rsi_zone": _rsi_zone(latest["rsi"]),

            "ema9":          round(float(latest["ema9"]),  2),
            "ema21":         round(float(latest["ema21"]), 2),
            "ema_trend":     "BULLISH" if latest["ema9"] > latest["ema21"] else "BEARISH",
            "ema_crossover": ema_crossover,

            "macd":           round(float(latest["macd"]),        2),
            "macd_signal":    round(float(latest["macd_signal"]), 2),
            "macd_hist":      round(float(latest["macd_hist"]),   2),
            "macd_momentum":  "BULLISH" if latest["macd_hist"] > 0 else "BEARISH",
            "macd_crossover": macd_crossover,

            "bb_upper":    round(float(latest["bb_upper"]), 2),
            "bb_mid":      round(float(latest["bb_mid"]),   2),
            "bb_lower":    round(float(latest["bb_lower"]), 2),
            "bb_position": bb_position,
            "bb_width":    round(float(latest["bb_upper"] - latest["bb_lower"]), 2),

            "preliminary_signal": preliminary_signal,
        }

    except Exception as e:
        print(f"❌ Error calculating indicators for {symbol}: {e}")
        return None


# ── Signal helpers ─────────────────────────────────────────

def _rsi_zone(rsi_value):
    if rsi_value >= 70: return "OVERBOUGHT"
    elif rsi_value <= 30: return "OVERSOLD"
    elif rsi_value >= 55: return "BULLISH_ZONE"
    elif rsi_value <= 45: return "BEARISH_ZONE"
    else: return "NEUTRAL"


def _check_ema_crossover(df):
    if len(df) < 3:
        return "NONE"
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    if prev["ema9"] <= prev["ema21"] and curr["ema9"] > curr["ema21"]:
        return "GOLDEN_CROSS"
    if prev["ema9"] >= prev["ema21"] and curr["ema9"] < curr["ema21"]:
        return "DEATH_CROSS"
    return "NONE"


def _check_macd_crossover(df):
    if len(df) < 3:
        return "NONE"
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    if prev["macd"] <= prev["macd_signal"] and curr["macd"] > curr["macd_signal"]:
        return "BULLISH_CROSS"
    if prev["macd"] >= prev["macd_signal"] and curr["macd"] < curr["macd_signal"]:
        return "BEARISH_CROSS"
    return "NONE"


def _check_bb_position(latest):
    close    = latest["close"]
    bb_upper = latest["bb_upper"]
    bb_lower = latest["bb_lower"]
    bb_mid   = latest["bb_mid"]
    if close >= bb_upper:  return "ABOVE_UPPER"
    elif close <= bb_lower: return "BELOW_LOWER"
    elif close >= bb_mid:   return "UPPER_HALF"
    else:                   return "LOWER_HALF"


def _get_preliminary_signal(latest, ema_crossover,
                             macd_crossover, bb_position):
    score = 0

    rsi = latest["rsi"]
    if rsi <= 35:   score += 1
    elif rsi >= 65: score -= 1

    if latest["ema9"] > latest["ema21"]: score += 1
    else:                                score -= 1

    if ema_crossover == "GOLDEN_CROSS":  score += 2
    elif ema_crossover == "DEATH_CROSS": score -= 2

    if latest["macd_hist"] > 0: score += 1
    else:                       score -= 1

    if macd_crossover == "BULLISH_CROSS":  score += 2
    elif macd_crossover == "BEARISH_CROSS": score -= 2

    if bb_position == "BELOW_LOWER":  score += 1
    elif bb_position == "ABOVE_UPPER": score -= 1

    if score >= 3:   return "STRONG_BUY"
    elif score >= 1: return "BUY"
    elif score <= -3: return "STRONG_SELL"
    elif score <= -1: return "SELL"
    else:             return "WAIT"


# ── Batch processor ────────────────────────────────────────

def calculate_all(watchlist_data):
    print(f"\n🔢 Calculating indicators for {len(watchlist_data)} stocks...")
    results = {}
    for symbol, df in watchlist_data.items():
        indicators = calculate_indicators(df)
        if indicators:
            results[symbol] = indicators
            print(f"  ✅ {symbol:12} | "
                  f"RSI: {indicators['rsi']:>5.1f} | "
                  f"Signal: {indicators['preliminary_signal']}")
        else:
            print(f"  ❌ {symbol} — failed")
    return results


# ── Entry point ────────────────────────────────────────────

if __name__ == "__main__":
    from auth import get_access_token
    from data_fetcher import fetch_watchlist, init_watchlist_db

    init_watchlist_db()
    token = get_access_token()

    if token:
        raw_data   = fetch_watchlist(token)
        indicators = calculate_all(raw_data)

        if indicators:
            sample = list(indicators.values())[0]
            print(f"\n── Sample: {sample['symbol']} ──")
            for key, val in sample.items():
                print(f"  {key:<20}: {val}")

        print(f"\n✅ Indicators ready for {len(indicators)}/{len(raw_data)} stocks")