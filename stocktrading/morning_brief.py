# morning_brief.py — Daily morning analysis report
# Runs full pipeline and formats as clean report
# Saved to logs/ folder automatically

import os
from datetime import datetime
from stocktrading.config import DB_PATH, LOG_DIR


def generate_morning_brief(all_analysis, all_indicators, journal_summary=None):
    """
    Takes analysis results and formats a clean morning brief.
    Returns (report_text, filepath)
    """
    now        = datetime.now()
    date_str   = now.strftime("%A, %d %b %Y")
    time_str   = now.strftime("%H:%M")
    file_date  = now.strftime("%Y-%m-%d")

    # Categorise signals
    buys  = {s: r for s, r in all_analysis.items() if "BUY"  in str(r.get("signal",""))}
    sells = {s: r for s, r in all_analysis.items() if "SELL" in str(r.get("signal",""))}
    waits = {s: r for s, r in all_analysis.items()
             if s not in buys and s not in sells}

    lines = []
    lines.append("=" * 54)
    lines.append(f"  📋 MORNING BRIEF — {date_str}")
    lines.append(f"  Generated: {time_str}")
    lines.append("=" * 54)

    # Best opportunities
    lines.append("\n🎯 TODAY'S SIGNALS\n")

    if buys:
        lines.append("  BUY SIGNALS:")
        for symbol, r in buys.items():
            ind  = all_indicators.get(symbol, {})
            rsi  = ind.get("rsi", "—")
            viols = r.get("rule_violations", [])
            flag = " ⚠️" if viols else ""
            lines.append(
                f"  🟢 {symbol:12} | Conf: {r.get('confidence',0)}%"
                f" | Entry: ₹{r.get('entry','—')}"
                f" | Target: ₹{r.get('target','—')}"
                f" | SL: ₹{r.get('stop_loss','—')}"
                f" | R:R {r.get('risk_reward','—')}"
                f" | RSI: {rsi}{flag}"
            )
        lines.append("")

    if sells:
        lines.append("  SELL SIGNALS:")
        for symbol, r in sells.items():
            ind  = all_indicators.get(symbol, {})
            rsi  = ind.get("rsi", "—")
            viols = r.get("rule_violations", [])
            flag = " ⚠️" if viols else ""
            lines.append(
                f"  🔴 {symbol:12} | Conf: {r.get('confidence',0)}%"
                f" | Entry: ₹{r.get('entry','—')}"
                f" | Target: ₹{r.get('target','—')}"
                f" | SL: ₹{r.get('stop_loss','—')}"
                f" | R:R {r.get('risk_reward','—')}"
                f" | RSI: {rsi}{flag}"
            )
        lines.append("")

    if waits:
        lines.append("  WAIT / NO TRADE:")
        for symbol, r in waits.items():
            ind = all_indicators.get(symbol, {})
            rsi = ind.get("rsi", "—")
            lines.append(
                f"  🟡 {symbol:12} | Conf: {r.get('confidence',0)}%"
                f" | RSI: {rsi}"
                f" | {ind.get('ema_trend','—')} trend"
            )
        lines.append("")

    # Market overview
    total    = len(all_analysis)
    actionable = len(buys) + len(sells)
    lines.append("─" * 54)
    lines.append(f"  📊 OVERVIEW: {total} stocks | "
                 f"{len(buys)} BUY | {len(sells)} SELL | "
                 f"{len(waits)} WAIT | {actionable} actionable")
    lines.append("─" * 54)

    # Key indicator summary
    lines.append("\n📈 INDICATOR SNAPSHOT\n")
    lines.append(f"  {'Stock':<12} {'RSI':>6} {'EMA':>8} {'MACD':>8} {'BB Position':<14} Pre-Signal")
    lines.append(f"  {'─'*12} {'─'*6} {'─'*8} {'─'*8} {'─'*14} {'─'*10}")
    for symbol, ind in all_indicators.items():
        lines.append(
            f"  {symbol:<12}"
            f" {str(ind.get('rsi','—')):>6}"
            f" {ind.get('ema_trend','—'):>8}"
            f" {ind.get('macd_momentum','—'):>8}"
            f" {ind.get('bb_position','—'):<14}"
            f" {ind.get('preliminary_signal','—')}"
        )

    # AI reasoning for actionable signals only
    if buys or sells:
        lines.append("\n─" * 27)
        lines.append("\n🤖 AI REASONING (Actionable Signals)\n")
        for symbol, r in {**buys, **sells}.items():
            lines.append(f"  {symbol}:")
            reasoning = r.get("reasoning", "—")
            # Wrap at 60 chars
            words = reasoning.split()
            line  = "    "
            for word in words:
                if len(line) + len(word) > 62:
                    lines.append(line)
                    line = "    " + word + " "
                else:
                    line += word + " "
            if line.strip():
                lines.append(line)
            lines.append("")

    # Journal stats
    if journal_summary:
        lines.append("─" * 54)
        lines.append("\n📓 JOURNAL STATS\n")
        lines.append(
            f"  Trades: {journal_summary.get('total_trades',0)} total | "
            f"{journal_summary.get('open_trades',0)} open | "
            f"{journal_summary.get('closed_trades',0)} closed"
        )
        lines.append(
            f"  Win Rate: {journal_summary.get('win_rate',0)}% | "
            f"Total P&L: ₹{journal_summary.get('total_pnl',0)} | "
            f"Best: {journal_summary.get('best_trade','—')}"
        )
        lines.append("")

    lines.append("=" * 54)
    lines.append(f"  End of Morning Brief — {date_str}")
    lines.append("=" * 54)

    report = "\n".join(lines)

    # Save to logs/
    os.makedirs(LOG_DIR, exist_ok=True)
    filepath = os.path.join(LOG_DIR, f"morning_brief_{file_date}.txt")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    return report, filepath


if __name__ == "__main__":
    from stocktrading.auth import get_access_token
    from stocktrading.data_fetcher import fetch_watchlist, init_watchlist_db
    from stocktrading.indicators import calculate_all
    from stocktrading.ai_analyst import analyze_all_at_once
    from stocktrading.trade_journal import init_trade_journal, get_journal_summary

    init_watchlist_db()
    init_trade_journal()
    token = get_access_token()

    if token:
        raw_data       = fetch_watchlist(token)
        all_indicators = calculate_all(raw_data)
        all_analysis   = analyze_all_at_once(all_indicators)
        summary        = get_journal_summary()
        report, path   = generate_morning_brief(all_analysis, all_indicators, summary)
        print(report)
        print(f"\n✅ Saved to {path}")