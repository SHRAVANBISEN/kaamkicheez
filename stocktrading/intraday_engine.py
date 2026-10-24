"""Completed-bar structure and transparent, uncalibrated trend-breakout screening."""

import json
import math
from datetime import datetime

import pandas as pd

from stocktrading.config import (
    STRATEGY_FILE, DEFAULT_TIMEFRAME, TIMEZONE, RSI_PERIOD, EMA_SHORT, EMA_LONG,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL, BB_PERIOD, BB_STD, ATR_PERIOD, ADX_PERIOD,
)


def load_rules():
    with open(STRATEGY_FILE, encoding="utf-8") as handle:
        rules = json.load(handle)
    settings = rules["intraday"]
    for key in ("enabled", "require_event_review"):
        if not isinstance(settings[key], bool):
            raise ValueError(f"intraday.{key} must be true or false")
    for key, value in settings.items():
        if key in ("enabled", "require_event_review"):
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"intraday.{key} must be a positive finite number")
    for key in ("min_history_bars", "opening_range_minutes", "rvol_sessions"):
        if not isinstance(settings[key], int):
            raise ValueError(f"intraday.{key} must be an integer")
    return rules


def market_now(now=None):
    stamp = pd.Timestamp(now if now is not None else datetime.now().astimezone())
    if stamp.tzinfo is None:
        raise ValueError("Analysis time must include a timezone")
    return stamp.tz_convert(TIMEZONE)


def _smooth(series, length, alpha):
    """SMA seed followed by recursive EMA/Wilder smoothing."""
    result = pd.Series(float("nan"), index=series.index, dtype=float)
    valid = series.dropna()
    if len(valid) < length:
        return result
    position = series.index.get_loc(valid.index[length - 1])
    value = float(valid.iloc[:length].mean())
    result.iloc[position] = value
    for i in range(position + 1, len(series)):
        if pd.isna(series.iloc[i]):
            continue
        value += alpha * (float(series.iloc[i]) - value)
        result.iloc[i] = value
    return result


def _ema(series, length):
    return _smooth(series, length, 2 / (length + 1))


def _wilder(series, length):
    return _smooth(series, length, 1 / length)


def _number(value):
    return round(float(value), 6) if pd.notna(value) and math.isfinite(float(value)) else None


def prepare_candles(frame, now=None):
    if frame is None or frame.empty:
        raise ValueError("No candles received")
    minutes = int(frame.attrs.get("timeframe_minutes", DEFAULT_TIMEFRAME.removesuffix("minute")))
    if minutes not in (1, 5, 15):
        raise ValueError("Intraday calculations require 1, 5 or 15 minute candles")
    df = frame.copy()
    required = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        raise ValueError(f"Missing candle columns: {sorted(required - set(df.columns))}")
    if df["symbol"].nunique() != 1 or df["symbol"].isna().any():
        raise ValueError("Candles must contain exactly one symbol")
    stamps = [pd.Timestamp(value) for value in df["timestamp"]]
    if any(pd.isna(value) or value.tzinfo is None for value in stamps):
        raise ValueError("Candle timestamps must include their source timezone")
    df["timestamp"] = pd.to_datetime(stamps, utc=True).tz_convert(TIMEZONE)
    if df["timestamp"].duplicated().any():
        raise ValueError("Duplicate candle timestamps")
    for field in ("open", "high", "low", "close", "volume"):
        df[field] = pd.to_numeric(df[field], errors="raise")
        if not df[field].map(math.isfinite).all():
            raise ValueError(f"Non-finite {field} in candles")
    if (df[["open", "high", "low", "close"]] <= 0).any().any() or (df["volume"] < 0).any():
        raise ValueError("Prices must be positive and volumes nonnegative")
    if ((df["high"] < df[["open", "close", "low"]].max(axis=1)) |
            (df["low"] > df[["open", "close"]].min(axis=1))).any():
        raise ValueError("Inconsistent OHLC candle")
    clock = market_now(now)
    if (df["timestamp"] > clock).any():
        raise ValueError("Future candle timestamps received")
    slot = df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute
    regular = (slot >= 555) & (slot + minutes <= 930)
    if not regular.all() or (df["timestamp"].dt.weekday >= 5).any():
        raise ValueError("Unsupported non-regular NSE session candles")
    if ((slot - 555) % minutes != 0).any() or (df["timestamp"].dt.second != 0).any():
        raise ValueError("Candles are not aligned to the NSE session grid")
    df = df[df["timestamp"] + pd.Timedelta(minutes=minutes) <= clock]
    if df.empty:
        raise ValueError("No completed candles available")
    return df.sort_values("timestamp").reset_index(drop=True), minutes, clock


def calculate_features(frame, now=None, rules=None):
    rules = rules if rules is not None else load_rules()
    settings = rules["intraday"]
    df, minutes, clock = prepare_candles(frame, now)
    if len(df) < max(MACD_SLOW + MACD_SIGNAL, BB_PERIOD, 2 * ADX_PERIOD + 1):
        raise ValueError("At least 35 completed bars are required to calculate indicators")
    close = df["close"]
    ema_fast, ema_slow = _ema(close, EMA_SHORT), _ema(close, EMA_LONG)
    delta = close.diff()
    gain, loss = _wilder(delta.clip(lower=0), RSI_PERIOD), _wilder(-delta.clip(upper=0), RSI_PERIOD)
    rsi = 100 - 100 / (1 + gain / loss.replace(0, float("nan")))
    rsi = rsi.mask((loss == 0) & (gain > 0), 100).mask((loss == 0) & (gain == 0), 50)
    true_range = pd.concat([
        df["high"] - df["low"], (df["high"] - close.shift()).abs(),
        (df["low"] - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = _wilder(true_range, ATR_PERIOD)
    up, down = df["high"].diff(), -df["low"].diff()
    plus = _wilder(up.where((up > down) & (up > 0), 0.0), ADX_PERIOD)
    minus = _wilder(down.where((down > up) & (down > 0), 0.0), ADX_PERIOD)
    dx = 100 * (plus - minus).abs() / (plus + minus).replace(0, float("nan"))
    dx = dx.mask((plus + minus) == 0, 0)
    adx = _wilder(dx, ADX_PERIOD)
    macd = _ema(close, MACD_FAST) - _ema(close, MACD_SLOW)
    macd_signal = _ema(macd, MACD_SIGNAL)
    mid = close.rolling(BB_PERIOD).mean()
    deviation = close.rolling(BB_PERIOD).std(ddof=0) * BB_STD
    upper, lower = mid + deviation, mid - deviation
    latest = df.iloc[-1]
    dates = df["timestamp"].dt.date
    session = df[dates == latest["timestamp"].date()]
    session_start = latest["timestamp"].normalize() + pd.Timedelta(hours=9, minutes=15)
    expected = pd.date_range(session_start, latest["timestamp"], freq=f"{minutes}min")
    continuous = list(session["timestamp"]) == list(expected)
    blockers, warnings = [], []
    if len(df) < settings["min_history_bars"]:
        blockers.append(f"Warm-up: {len(df)} bars; need {settings['min_history_bars']}")
    if not continuous:
        blockers.append("Current session is missing bars or its opening; VWAP/opening range unavailable")
    historical_gaps = df.groupby(dates)["timestamp"].diff().dropna().ne(pd.Timedelta(minutes=minutes)).any()
    if historical_gaps:
        blockers.append("Within-session gaps detected in indicator history")
    age = (clock - (latest["timestamp"] + pd.Timedelta(minutes=minutes))).total_seconds()
    if latest["timestamp"].date() != clock.date() or age > minutes * 60 + settings["freshness_grace_seconds"]:
        blockers.append("Candle feed is stale for an intraday decision")
    minute_now = clock.hour * 60 + clock.minute
    if clock.weekday() >= 5 or not 555 <= minute_now < 930:
        blockers.append("Outside regular NSE cash-equity market hours")
    filters = rules.get("filters", {})
    if minute_now < 555 + filters.get("avoid_first_minutes", 15):
        blockers.append("Inside opening no-entry window")
    if minute_now >= 930 - filters.get("avoid_last_minutes", 15):
        blockers.append("Inside closing no-entry window")
    volume = float(session["volume"].sum())
    vwap = float((((session["high"] + session["low"] + session["close"]) / 3) *
                  session["volume"]).sum() / volume) if continuous and volume > 0 else None
    or_minutes = settings["opening_range_minutes"]
    opening = session[session["timestamp"] < session_start + pd.Timedelta(minutes=or_minutes)]
    or_complete = continuous and or_minutes % minutes == 0 and len(opening) == or_minutes // minutes
    or_high = float(opening["high"].max()) if or_complete else None
    or_low = float(opening["low"].min()) if or_complete else None
    if not or_complete:
        blockers.append("Opening range is incomplete or incompatible with the bar interval")
    past = df[dates < latest["timestamp"].date()]
    same_slot = past[past["timestamp"].dt.time == latest["timestamp"].time()].tail(settings["rvol_sessions"])
    baseline = float(same_slot["volume"].mean()) if len(same_slot) else 0
    rvol = float(latest["volume"]) / baseline if len(same_slot) == settings["rvol_sessions"] and baseline > 0 else None
    if rvol is None:
        blockers.append("Insufficient same-time-of-day volume history")
    previous = {}
    if not past.empty:
        previous_session = past[past["timestamp"].dt.date == past.iloc[-1]["timestamp"].date()]
        expected_previous = pd.date_range(
            previous_session.iloc[0]["timestamp"].normalize() + pd.Timedelta(hours=9, minutes=15),
            previous_session.iloc[0]["timestamp"].normalize() + pd.Timedelta(hours=15, minutes=30 - minutes),
            freq=f"{minutes}min",
        )
        if list(previous_session["timestamp"]) == list(expected_previous):
            previous = {"date": str(previous_session.iloc[-1]["timestamp"].date()),
                        "high": _number(previous_session["high"].max()),
                        "low": _number(previous_session["low"].min()),
                        "close": _number(previous_session.iloc[-1]["close"])}
    if not previous:
        warnings.append("Previous complete observed session levels unavailable")
    warnings.append("No exchange holiday/special-session calendar or spread/order-book validation")
    trend = "BULLISH" if ema_fast.iloc[-1] > ema_slow.iloc[-1] else "BEARISH" if ema_fast.iloc[-1] < ema_slow.iloc[-1] else "NEUTRAL"
    adx_value, atr_value = _number(adx.iloc[-1]), _number(atr.iloc[-1])
    regime = "TREND" if adx_value is not None and adx_value >= settings["min_adx"] else "RANGE_OR_WEAK"
    price, rsi_value = float(latest["close"]), _number(rsi.iloc[-1])
    distance = abs(price - vwap) / atr_value if vwap is not None and atr_value and atr_value > 0 else None
    setup = "WAIT"
    reasons = list(blockers)
    if regime != "TREND":
        reasons.append("ADX does not support the trend-breakout setup")
    if rvol is not None and rvol < settings["min_relative_volume"]:
        reasons.append("Relative volume is below the configured participation threshold")
    if distance is None or distance > settings["max_vwap_distance_atr"]:
        reasons.append("VWAP/ATR unavailable or price is overextended")
    if not reasons:
        if price > or_high and price > vwap and trend == "BULLISH" and 50 <= rsi_value <= filters.get("avoid_rsi_above", 75):
            setup = "BUY"
        elif price < or_low and price < vwap and trend == "BEARISH" and filters.get("avoid_rsi_below", 20) <= rsi_value <= 50:
            setup = "SELL"
        else:
            reasons.append("Price structure, VWAP, EMA and RSI do not align")
    ema_cross = "GOLDEN_CROSS" if ema_fast.iloc[-2] <= ema_slow.iloc[-2] and trend == "BULLISH" else "DEATH_CROSS" if ema_fast.iloc[-2] >= ema_slow.iloc[-2] and trend == "BEARISH" else "NONE"
    histogram = macd - macd_signal
    macd_cross = "BULLISH_CROSS" if histogram.iloc[-2] <= 0 < histogram.iloc[-1] else "BEARISH_CROSS" if histogram.iloc[-2] >= 0 > histogram.iloc[-1] else "NONE"
    return {
        "symbol": str(latest["symbol"]), "timestamp": latest["timestamp"].isoformat(),
        **{key: _number(latest[key]) for key in ("open", "high", "low", "close")},
        "volume": int(latest["volume"]), "rsi": rsi_value,
        "rsi_zone": "OVERBOUGHT" if rsi_value >= 70 else "OVERSOLD" if rsi_value <= 30 else "BULLISH_ZONE" if rsi_value >= 55 else "BEARISH_ZONE" if rsi_value <= 45 else "NEUTRAL",
        "ema9": _number(ema_fast.iloc[-1]), "ema21": _number(ema_slow.iloc[-1]),
        "ema_trend": trend, "ema_crossover": ema_cross,
        "macd": _number(macd.iloc[-1]), "macd_signal": _number(macd_signal.iloc[-1]),
        "macd_hist": _number(histogram.iloc[-1]),
        "macd_momentum": "BULLISH" if histogram.iloc[-1] > 0 else "BEARISH" if histogram.iloc[-1] < 0 else "NEUTRAL",
        "macd_crossover": macd_cross, "bb_upper": _number(upper.iloc[-1]),
        "bb_mid": _number(mid.iloc[-1]), "bb_lower": _number(lower.iloc[-1]),
        "bb_width": _number(2 * deviation.iloc[-1]),
        "bb_position": "ABOVE_UPPER" if price >= upper.iloc[-1] else "BELOW_LOWER" if price <= lower.iloc[-1] else "UPPER_HALF" if price >= mid.iloc[-1] else "LOWER_HALF",
        "preliminary_signal": setup,
        "intraday": {
            "methodology_version": "2.0", "settings": settings,
            "indicator_parameters": {
                "rsi": RSI_PERIOD, "ema_fast": EMA_SHORT, "ema_slow": EMA_LONG,
                "atr": ATR_PERIOD, "di": ADX_PERIOD, "adx_smoothing": ADX_PERIOD,
                "macd": [MACD_FAST, MACD_SLOW, MACD_SIGNAL], "bollinger": [BB_PERIOD, BB_STD],
            },
            "source": frame.attrs.get("source", "Unspecified candle input"),
            "received_at": frame.attrs.get("received_at"),
            "evaluated_at": clock.isoformat(), "timeframe_minutes": minutes,
            "completed_bar_end": (latest["timestamp"] + pd.Timedelta(minutes=minutes)).isoformat(),
            "bar_age_seconds": age, "history_bars": len(df),
            "vwap": _number(vwap), "atr": atr_value, "adx": adx_value,
            "regime": regime, "relative_volume": _number(rvol),
            "rvol_samples": len(same_slot), "opening_range_high": or_high,
            "opening_range_low": or_low, "previous_observed_session": previous,
            "vwap_distance_atr": _number(distance), "setup": setup,
            "blockers": blockers, "setup_reasons": reasons, "warnings": warnings,
        },
    }
