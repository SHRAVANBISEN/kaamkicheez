# trade_journal.py — Logs and retrieves all trades
# Stores in SQLite trades.db — same DB as watchlist

import sqlite3
import json
from datetime import datetime, timedelta
from config import DB_PATH


# ── DB Setup ───────────────────────────────────────────────

def init_trade_journal():
    """Creates trades table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_date     TEXT,
            analysis_time     TEXT,
            trade_date        TEXT,
            trade_day         TEXT,
            symbol            TEXT,
            signal            TEXT,
            confidence        INTEGER,
            entry             REAL,
            target            REAL,
            stop_loss         REAL,
            risk_reward       TEXT,
            reasoning         TEXT,
            indicators_summary TEXT,
            rsi               REAL,
            ema_trend         TEXT,
            macd_momentum     TEXT,
            bb_position       TEXT,
            preliminary_signal TEXT,
            status            TEXT DEFAULT 'OPEN',
            exit_price        REAL,
            pnl               REAL,
            outcome           TEXT,
            notes             TEXT,
            logged_at         TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def _next_trading_day(from_date=None):
    """
    Returns the next trading day from given date.
    Skips weekends. Does not account for holidays.
    """
    if from_date is None:
        from_date = datetime.now()
    next_day = from_date + timedelta(days=1)
    # Skip Saturday (5) and Sunday (6)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)
    return next_day


def _is_market_hours():
    """Returns True if current time is within NSE market hours."""
    now = datetime.now()
    market_open  = now.replace(hour=9,  minute=15, second=0)
    market_close = now.replace(hour=15, minute=30, second=0)
    return market_open <= now <= market_close and now.weekday() < 5


def _get_trade_date_info():
    """
    Returns analysis date, trade date, and trade day label.
    If market is open now → trade today
    If after market hours or weekend → trade next trading day
    """
    now           = datetime.now()
    analysis_date = now.strftime("%Y-%m-%d")
    analysis_time = now.strftime("%H:%M:%S")
    weekday       = now.weekday()  # 0=Mon, 6=Sun

    market_open  = now.replace(hour=9,  minute=15, second=0)
    market_close = now.replace(hour=15, minute=30, second=0)

    if weekday < 5 and market_open <= now <= market_close:
        # Market is open right now
        trade_date = now
        trade_day  = f"TODAY ({now.strftime('%A, %d %b %Y')})"
    elif weekday < 5 and now < market_open:
        # Weekday but before market open
        trade_date = now
        trade_day  = f"TODAY ({now.strftime('%A, %d %b %Y')}) — Market opens at 9:15 AM"
    else:
        # After market close or weekend
        trade_date = _next_trading_day(now)
        trade_day  = f"NEXT TRADING DAY ({trade_date.strftime('%A, %d %b %Y')})"

    return {
        "analysis_date": analysis_date,
        "analysis_time": analysis_time,
        "trade_date":    trade_date.strftime("%Y-%m-%d"),
        "trade_day":     trade_day,
    }


# ── Log a trade ────────────────────────────────────────────

def log_trade(analysis: dict, indicators: dict = None, notes: str = ""):
    """
    Log a trade from Gemini analysis dict.
    Automatically calculates when to place the trade.
    Returns trade_id.
    """
    date_info = _get_trade_date_info()
    ind       = indicators or {}

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        INSERT INTO trades (
            analysis_date, analysis_time,
            trade_date, trade_day,
            symbol, signal, confidence,
            entry, target, stop_loss, risk_reward,
            reasoning, indicators_summary,
            rsi, ema_trend, macd_momentum,
            bb_position, preliminary_signal,
            status, notes
        ) VALUES (
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?,
            'OPEN', ?
        )
    """, (
        date_info["analysis_date"],
        date_info["analysis_time"],
        date_info["trade_date"],
        date_info["trade_day"],
        analysis.get("symbol"),
        analysis.get("signal"),
        analysis.get("confidence"),
        analysis.get("entry"),
        analysis.get("target"),
        analysis.get("stop_loss"),
        analysis.get("risk_reward"),
        analysis.get("reasoning"),
        analysis.get("indicators_summary"),
        ind.get("rsi"),
        ind.get("ema_trend"),
        ind.get("macd_momentum"),
        ind.get("bb_position"),
        ind.get("preliminary_signal"),
        notes
    ))
    trade_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return trade_id, date_info["trade_day"]


# ── Close a trade ──────────────────────────────────────────

def close_trade(trade_id: int, exit_price: float, notes: str = ""):
    """Mark trade closed, calculate P&L automatically."""
    conn  = sqlite3.connect(DB_PATH)
    trade = conn.execute(
        "SELECT signal, entry FROM trades WHERE id = ?",
        (trade_id,)
    ).fetchone()

    if not trade:
        conn.close()
        return False, "Trade not found"

    signal, entry = trade
    if entry is None:
        conn.close()
        return False, "No entry price on record"

    if signal in ["BUY", "STRONG_BUY"]:
        pnl = round(exit_price - entry, 2)
    else:
        pnl = round(entry - exit_price, 2)

    outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN"

    conn.execute("""
        UPDATE trades
        SET status     = 'CLOSED',
            exit_price = ?,
            pnl        = ?,
            outcome    = ?,
            notes      = COALESCE(NULLIF(notes,''), '') || ?
        WHERE id = ?
    """, (exit_price, pnl, outcome, f" | Closed: {notes}" if notes else "", trade_id))
    conn.commit()
    conn.close()
    return True, f"{outcome} | P&L: ₹{pnl}"


# ── Read trades ────────────────────────────────────────────

def get_all_trades():
    """Returns all trades as list of dicts, newest first."""
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT id, analysis_date, analysis_time,
               trade_date, trade_day,
               symbol, signal, confidence,
               entry, target, stop_loss, risk_reward,
               reasoning, indicators_summary,
               rsi, ema_trend, macd_momentum, bb_position,
               status, exit_price, pnl, outcome, notes
        FROM trades
        ORDER BY id DESC
    """)
    cols = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip(cols, row)) for row in rows]


def get_open_trades():
    """Returns only open/pending trades."""
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT id, trade_date, trade_day, symbol, signal,
               entry, target, stop_loss, risk_reward, confidence
        FROM trades WHERE status = 'OPEN'
        ORDER BY id DESC
    """)
    cols = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip(cols, row)) for row in rows]


def get_journal_summary():
    """Returns summary stats for dashboard display."""
    conn = sqlite3.connect(DB_PATH)

    total = conn.execute(
        "SELECT COUNT(*) FROM trades"
    ).fetchone()[0]

    closed = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE status = 'CLOSED'"
    ).fetchone()[0]

    wins = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE outcome = 'WIN'"
    ).fetchone()[0]

    losses = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE outcome = 'LOSS'"
    ).fetchone()[0]

    total_pnl = conn.execute(
        "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE status = 'CLOSED'"
    ).fetchone()[0]

    open_count = conn.execute(
        "SELECT COUNT(*) FROM trades WHERE status = 'OPEN'"
    ).fetchone()[0]

    best_trade = conn.execute(
        "SELECT symbol, pnl FROM trades WHERE outcome='WIN' ORDER BY pnl DESC LIMIT 1"
    ).fetchone()

    worst_trade = conn.execute(
        "SELECT symbol, pnl FROM trades WHERE outcome='LOSS' ORDER BY pnl ASC LIMIT 1"
    ).fetchone()

    conn.close()

    win_rate = round((wins / closed * 100), 1) if closed > 0 else 0

    return {
        "total_trades":  total,
        "open_trades":   open_count,
        "closed_trades": closed,
        "wins":          wins,
        "losses":        losses,
        "win_rate":      win_rate,
        "total_pnl":     round(float(total_pnl), 2),
        "best_trade":    f"{best_trade[0]} +₹{best_trade[1]}" if best_trade else "—",
        "worst_trade":   f"{worst_trade[0]} -₹{abs(worst_trade[1])}" if worst_trade else "—",
    }


def delete_trade(trade_id: int):
    """Delete a trade by ID."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
    conn.commit()
    conn.close()
    return True


# ── Entry point ────────────────────────────────────────────

if __name__ == "__main__":
    init_trade_journal()

    date_info = _get_trade_date_info()
    print(f"\n📅 Analysis Date : {date_info['analysis_date']} {date_info['analysis_time']}")
    print(f"📅 Trade Date    : {date_info['trade_day']}")

    sample = {
        "symbol":              "RELIANCE",
        "signal":              "BUY",
        "confidence":          75,
        "entry":               1467.20,
        "target":              1490.00,
        "stop_loss":           1455.00,
        "risk_reward":         "1:1.9",
        "reasoning":           "RSI bullish, EMA positive, MACD rising.",
        "indicators_summary":  "All indicators bullish except BB slightly extended."
    }
    sample_ind = {
        "rsi": 76.0, "ema_trend": "BULLISH",
        "macd_momentum": "BULLISH", "bb_position": "UPPER_HALF",
        "preliminary_signal": "BUY"
    }

    trade_id, trade_day = log_trade(sample, sample_ind, notes="Test trade")
    print(f"\n✅ Trade logged — ID: {trade_id}")
    print(f"📅 Place this trade: {trade_day}")

    summary = get_journal_summary()
    print(f"\n📊 Summary: {summary}")