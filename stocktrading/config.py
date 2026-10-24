# config.py — Central configuration for StockTradingAlgo
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESOURCE_DIR = PROJECT_ROOT / "resources"
DOCS_DIR = PROJECT_ROOT / "docs"
load_dotenv(PROJECT_ROOT / ".env")

# ── API Credentials ────────────────────────────────────────
UPSTOX_API_KEY      = os.getenv("UPSTOX_API_KEY")
UPSTOX_API_SECRET   = os.getenv("UPSTOX_API_SECRET")
UPSTOX_REDIRECT_URL = os.getenv("UPSTOX_REDIRECT_URL", "http://127.0.0.1:5000/callback")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ── Token Storage ──────────────────────────────────────────
TOKEN_FILE = str(PROJECT_ROOT / "db" / "upstox_token.json")

# ── Watchlist ──────────────────────────────────────────────
# Upstox instrument keys for NSE stocks (format: NSE_EQ|INE...)
# We'll fill instrument keys after auth is working.
# For now, define by ticker symbol — we'll map to keys shortly.
WATCHLIST = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "WIPRO",
    "AXISBANK",
    "LT",
    "BAJFINANCE",
]

# ── Trading Settings ───────────────────────────────────────
DEFAULT_TIMEFRAME   = "5minute"    # Intraday engine supports 1, 5 and 15 minute bars
CANDLE_LOOKBACK     = 100          # How many candles to fetch for indicator calculation
MARKET_OPEN         = "09:15"
MARKET_CLOSE        = "15:30"
TIMEZONE            = "Asia/Kolkata"

# ── Paths ──────────────────────────────────────────────────
DB_PATH             = str(PROJECT_ROOT / "db" / "trades.db")
STRATEGY_FILE       = str(RESOURCE_DIR / "strategy_rules.json")
LOG_DIR             = str(PROJECT_ROOT / "logs")

# ── Indicator Defaults ─────────────────────────────────────
RSI_PERIOD          = 14
EMA_SHORT           = 9
EMA_LONG            = 21
MACD_FAST           = 12
MACD_SLOW           = 26
MACD_SIGNAL         = 9
BB_PERIOD           = 20
BB_STD              = 2

ATR_PERIOD          = 14
ADX_PERIOD          = 14

# ── Sanity Check ───────────────────────────────────────────
if __name__ == "__main__":
    print("=== Config Check ===")
    print(f"API Key loaded:      {'✅' if UPSTOX_API_KEY else '❌ MISSING'}")
    print(f"API Secret loaded:   {'✅' if UPSTOX_API_SECRET else '❌ MISSING'}")
    print(f"Gemini key:          {'✅' if GEMINI_API_KEY else '❌ MISSING'}")
    print(f"Watchlist stocks:    {len(WATCHLIST)}")
    print(f"Default timeframe:   {DEFAULT_TIMEFRAME}")