# data_fetcher.py — Fetches OHLCV candle data from Upstox
# Watchlist + instrument keys stored in SQLite DB
# Any NSE stock can be added without touching code

import requests
import pandas as pd
import sqlite3
import gzip
import io
import json
from datetime import datetime, timedelta
from config import WATCHLIST, DEFAULT_TIMEFRAME, CANDLE_LOOKBACK, TIMEZONE, DB_PATH

# ── Hardcoded keys (fallback + pre-loaded) ─────────────────
INSTRUMENT_KEYS = {
    "RELIANCE":   "NSE_EQ|INE002A01018",
    "TCS":        "NSE_EQ|INE467B01029",
    "INFY":       "NSE_EQ|INE009A01021",
    "HDFCBANK":   "NSE_EQ|INE040A01034",
    "ICICIBANK":  "NSE_EQ|INE090A01021",
    "SBIN":       "NSE_EQ|INE062A01020",
    "WIPRO":      "NSE_EQ|INE075A01022",
    "AXISBANK":   "NSE_EQ|INE238A01034",
    "LT":         "NSE_EQ|INE018A01030",
    "BAJFINANCE": "NSE_EQ|INE296A01032",
}

BASE_URL = "https://api.upstox.com/v2"


# ── DB Setup ───────────────────────────────────────────────

def init_watchlist_db():
    conn = sqlite3.connect(DB_PATH)

    # Watchlist table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            symbol     TEXT PRIMARY KEY,
            added_on   TEXT DEFAULT (date('now')),
            is_active  INTEGER DEFAULT 1
        )
    """)

    # Instrument keys table — stores ALL looked-up keys
    conn.execute("""
        CREATE TABLE IF NOT EXISTS instrument_keys (
            symbol          TEXT PRIMARY KEY,
            instrument_key  TEXT NOT NULL,
            added_on        TEXT DEFAULT (date('now'))
        )
    """)
    conn.commit()

    # Seed instrument_keys table from hardcoded dict
    for symbol, key in INSTRUMENT_KEYS.items():
        conn.execute("""
            INSERT OR IGNORE INTO instrument_keys (symbol, instrument_key)
            VALUES (?, ?)
        """, (symbol, key))
    conn.commit()

    # Seed watchlist if empty
    count = conn.execute(
        "SELECT COUNT(*) FROM watchlist WHERE is_active = 1"
    ).fetchone()[0]

    if count == 0:
        print("📋 Seeding watchlist from config.py...")
        for symbol in WATCHLIST:
            conn.execute("""
                INSERT OR IGNORE INTO watchlist (symbol, is_active)
                VALUES (?, 1)
            """, (symbol,))
        conn.commit()
        print(f"   ✅ {len(WATCHLIST)} stocks added")
    else:
        print(f"   ✅ Watchlist has {count} active stocks")

    conn.close()


# ── Instrument key helpers ─────────────────────────────────

def get_instrument_key(symbol):
    """Get instrument key from DB first, then hardcoded dict."""
    symbol = symbol.upper().strip()
    try:
        conn = sqlite3.connect(DB_PATH)
        row  = conn.execute(
            "SELECT instrument_key FROM instrument_keys WHERE symbol = ?",
            (symbol,)
        ).fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception:
        pass
    return INSTRUMENT_KEYS.get(symbol)


def save_instrument_key(symbol, instrument_key):
    """Save a newly looked-up instrument key to DB."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT OR REPLACE INTO instrument_keys (symbol, instrument_key)
            VALUES (?, ?)
        """, (symbol.upper(), instrument_key))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️  Could not save key: {e}")
        return False


def lookup_and_save_instrument_key(symbol):
    """
    Look up instrument key from Upstox master file.
    Saves to DB automatically.
    Returns instrument_key string or None.
    """
    symbol = symbol.upper().strip()
    print(f"🔍 Looking up {symbol} on Upstox...")

    url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
    try:
        resp = requests.get(url, timeout=20)
        with gzip.open(io.BytesIO(resp.content)) as f:
            instruments = json.load(f)

        matches = [
            i for i in instruments
            if i.get("trading_symbol") == symbol
            and i.get("instrument_type") == "EQ"
        ]

        if matches:
            key = matches[0]["instrument_key"]
            save_instrument_key(symbol, key)
            print(f"   ✅ {symbol} → {key} (saved to DB)")
            return key
        else:
            print(f"   ❌ {symbol} not found on NSE")
            return None

    except Exception as e:
        print(f"   ❌ Lookup failed: {e}")
        return None


def get_all_available_symbols():
    """Returns all symbols we have keys for (DB + hardcoded)."""
    symbols = set(INSTRUMENT_KEYS.keys())
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT symbol FROM instrument_keys").fetchall()
        conn.close()
        symbols.update(row[0] for row in rows)
    except Exception:
        pass
    return sorted(symbols)


# ── Watchlist helpers ──────────────────────────────────────

def get_watchlist_from_db():
    try:
        conn    = sqlite3.connect(DB_PATH)
        rows    = conn.execute(
            "SELECT symbol FROM watchlist WHERE is_active = 1 ORDER BY symbol"
        ).fetchall()
        conn.close()
        symbols = [row[0] for row in rows]
        if symbols:
            return symbols
    except Exception as e:
        print(f"⚠️  DB read failed: {e}")
    return WATCHLIST


def add_stock_to_watchlist(symbol):
    """
    Add stock to watchlist.
    If instrument key not known, looks it up automatically.
    """
    symbol = symbol.upper().strip()

    # Check if we have the instrument key
    key = get_instrument_key(symbol)
    if not key:
        print(f"🔍 No key for {symbol} — looking up...")
        key = lookup_and_save_instrument_key(symbol)
        if not key:
            return False, f"❌ '{symbol}' not found on NSE. Check the symbol and try again."

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO watchlist (symbol, is_active)
            VALUES (?, 1)
            ON CONFLICT(symbol) DO UPDATE SET is_active = 1
        """, (symbol,))
        conn.commit()
        conn.close()
        return True, f"✅ {symbol} added to watchlist"
    except Exception as e:
        return False, f"❌ DB error: {e}"


def remove_stock_from_watchlist(symbol):
    symbol = symbol.upper().strip()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE watchlist SET is_active = 0 WHERE symbol = ?", (symbol,)
        )
        conn.commit()
        conn.close()
        return True, f"✅ {symbol} removed"
    except Exception as e:
        return False, f"❌ DB error: {e}"


# ── Core data fetching ─────────────────────────────────────

def get_headers(access_token):
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept":        "application/json",
    }


def fetch_candles(symbol, access_token,
                  timeframe=DEFAULT_TIMEFRAME,
                  days_back=10):
    symbol         = symbol.upper().strip()
    instrument_key = get_instrument_key(symbol)

    if not instrument_key:
        # Try live lookup
        print(f"🔍 No key for {symbol} — attempting live lookup...")
        instrument_key = lookup_and_save_instrument_key(symbol)
        if not instrument_key:
            print(f"⚠️  Cannot fetch {symbol} — instrument key not found")
            return None

    to_date   = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    url = (
        f"{BASE_URL}/historical-candle"
        f"/{instrument_key}"
        f"/{timeframe}"
        f"/{to_date}"
        f"/{from_date}"
    )

    try:
        resp = requests.get(url, headers=get_headers(access_token))
        data = resp.json()

        if data.get("status") != "success":
            print(f"❌ API error for {symbol}: {data}")
            return None

        candles = data["data"]["candles"]
        if not candles:
            print(f"⚠️  No candles for {symbol}")
            return None

        df = pd.DataFrame(candles, columns=[
            "timestamp", "open", "high", "low", "close", "volume", "oi"
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df              = df.sort_values("timestamp").reset_index(drop=True)
        df["symbol"]    = symbol
        return df

    except Exception as e:
        print(f"❌ Exception fetching {symbol}: {e}")
        return None


def fetch_watchlist(access_token, timeframe=DEFAULT_TIMEFRAME):
    symbols = get_watchlist_from_db()
    print(f"\n📊 Fetching {len(symbols)} stocks...")
    results = {}
    for symbol in symbols:
        df = fetch_candles(symbol, access_token, timeframe)
        if df is not None:
            results[symbol] = df
            latest = df.iloc[-1]
            print(f"  ✅ {symbol:12} | ₹{latest['close']:.2f} | {len(df)} candles")
        else:
            print(f"  ❌ {symbol} — failed")
    return results


def fetch_single_stock(symbol, access_token,
                       timeframe=DEFAULT_TIMEFRAME,
                       days_back=10):
    symbol = symbol.upper().strip()
    print(f"\n🔍 Fetching on-demand: {symbol}")
    df = fetch_candles(symbol, access_token, timeframe, days_back=days_back)
    if df is not None:
        print(f"  ✅ {symbol} | ₹{df.iloc[-1]['close']:.2f} | {len(df)} candles")
    return df


def get_latest_price(symbol, access_token):
    df = fetch_candles(symbol, access_token, timeframe="1minute", days_back=1)
    if df is not None and not df.empty:
        return df.iloc[-1]["close"]
    return None


# ── Entry point ────────────────────────────────────────────

if __name__ == "__main__":
    from auth import get_access_token
    init_watchlist_db()
    token = get_access_token()
    if token:
        symbols = get_watchlist_from_db()
        data    = fetch_watchlist(token)
        print(f"\n✅ {len(data)}/{len(symbols)} stocks fetched")