# system_info.py — Live system documentation tab
# Shows everything running under the hood:
# indicators, news sources, strategy rules, AI config, data pipeline

import streamlit as st
import json
import os
from datetime import datetime


def render_system_info_tab():
    """Renders the complete System Info tab in dashboard."""

    st.markdown('<div class="section-label">System Overview</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="card">
        <div style="font-size:0.85rem;color:#94a3b8;line-height:1.8">
        This tab shows everything running under the hood of StockTradingAlgo.<br>
        Every indicator, every news source, every rule — all in one place.<br>
        <span style="color:#38bdf8">When you add something new to the system, it appears here automatically.</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Section tabs inside the main tab ──────────────────
    s1, s2, s3, s4, s5 = st.tabs([
        "📈 Indicators",
        "📰 News Sources",
        "⚙️ Strategy Rules",
        "🤖 AI Config",
        "🔄 Data Pipeline",
    ])

    # ═══════════════════════════════════════════════════════
    # SECTION 1 — INDICATORS
    # ═══════════════════════════════════════════════════════
    with s1:
        st.markdown('<div class="section-label">Technical Indicators in Use</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="card">
        <div style="font-size:0.78rem;color:#94a3b8;line-height:1.7">
        All indicators are calculated locally using <b style="color:#38bdf8">pandas-ta</b> library
        on raw OHLCV candle data from Upstox. No external indicator API is used.
        </div>
        </div>
        """, unsafe_allow_html=True)

        indicators = [
            {
                "name": "RSI — Relative Strength Index",
                "period": "14 periods",
                "library": "pandas-ta",
                "input": "Close price",
                "what_it_does": "Measures whether a stock is overbought or oversold on a scale of 0-100.",
                "how_we_use": "RSI > 70 = OVERBOUGHT (avoid BUY) | RSI < 30 = OVERSOLD (potential bounce)",
                "zones": "< 30 OVERSOLD | 30-45 BEARISH | 45-55 NEUTRAL | 55-70 BULLISH | > 70 OVERBOUGHT",
                "scoring": "+1 if RSI ≤ 35 (oversold) | -1 if RSI ≥ 65 (overbought)",
                "color": "#22c55e",
            },
            {
                "name": "EMA — Exponential Moving Average",
                "period": "9 & 21 periods",
                "library": "pandas-ta",
                "input": "Close price",
                "what_it_does": "Tracks short-term (EMA9) and medium-term (EMA21) price trends. More weight on recent prices than simple moving average.",
                "how_we_use": "EMA9 > EMA21 = BULLISH trend | EMA9 < EMA21 = BEARISH trend",
                "zones": "Golden Cross (EMA9 crosses above EMA21) = strong BUY | Death Cross = strong SELL",
                "scoring": "+1 if EMA9 > EMA21 | -1 if EMA9 < EMA21 | +2 Golden Cross | -2 Death Cross",
                "color": "#38bdf8",
            },
            {
                "name": "MACD — Moving Average Convergence Divergence",
                "period": "Fast:12, Slow:26, Signal:9",
                "library": "pandas-ta",
                "input": "Close price",
                "what_it_does": "Measures momentum — whether buying or selling pressure is building. Three components: MACD line, Signal line, Histogram.",
                "how_we_use": "Histogram > 0 = bullish momentum building | Histogram < 0 = bearish momentum",
                "zones": "BULLISH_CROSS (MACD crosses above signal) = momentum turning up | BEARISH_CROSS = momentum turning down",
                "scoring": "+1 if hist > 0 | -1 if hist < 0 | +2 Bullish Cross | -2 Bearish Cross",
                "color": "#a78bfa",
            },
            {
                "name": "Bollinger Bands",
                "period": "20 period, 2 std deviations",
                "library": "pandas-ta",
                "input": "Close price",
                "what_it_does": "Shows price volatility. Three bands: Upper (resistance), Middle (mean), Lower (support). Bands widen when volatile, narrow when calm.",
                "how_we_use": "Price at BB Lower = oversold bounce candidate | Price at BB Upper = overbought reversal risk",
                "zones": "ABOVE_UPPER | UPPER_HALF | LOWER_HALF | BELOW_LOWER",
                "scoring": "+1 if price at BB Lower (oversold) | -1 if price at BB Upper (overbought)",
                "color": "#f59e0b",
            },
        ]

        for ind in indicators:
            st.markdown(f"""
            <div class="card" style="border-left:3px solid {ind['color']};margin-bottom:1rem">
                <div style="font-size:0.95rem;font-weight:800;color:#f1f5f9;font-family:'JetBrains Mono',monospace">{ind['name']}</div>
                <div style="display:flex;gap:12px;margin:8px 0;flex-wrap:wrap">
                    <span style="background:#1e2d4a;color:#60a5fa;padding:2px 8px;border-radius:12px;font-size:0.68rem;font-family:'JetBrains Mono',monospace">Period: {ind['period']}</span>
                    <span style="background:#1e2d4a;color:#60a5fa;padding:2px 8px;border-radius:12px;font-size:0.68rem;font-family:'JetBrains Mono',monospace">Library: {ind['library']}</span>
                    <span style="background:#1e2d4a;color:#60a5fa;padding:2px 8px;border-radius:12px;font-size:0.68rem;font-family:'JetBrains Mono',monospace">Input: {ind['input']}</span>
                </div>
                <div style="font-size:0.8rem;color:#94a3b8;margin-top:6px"><b style="color:#e2e8f0">What it does:</b> {ind['what_it_does']}</div>
                <div style="font-size:0.8rem;color:#94a3b8;margin-top:4px"><b style="color:#e2e8f0">How we use it:</b> {ind['how_we_use']}</div>
                <div style="font-size:0.78rem;color:#64748b;margin-top:4px;font-family:'JetBrains Mono',monospace">Zones: {ind['zones']}</div>
                <div style="font-size:0.78rem;color:{ind['color']};margin-top:4px;font-family:'JetBrains Mono',monospace">Scoring: {ind['scoring']}</div>
            </div>
            """, unsafe_allow_html=True)

        # Preliminary signal scoring
        st.markdown('<div class="section-label" style="margin-top:1rem">Preliminary Signal Scoring System</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="card">
            <div style="font-size:0.82rem;color:#94a3b8;line-height:1.9;font-family:'JetBrains Mono',monospace">
            All indicator scores are added together to get a preliminary signal BEFORE Gemini analysis:<br><br>
            <span style="color:#22c55e">Score ≥ +3 → STRONG_BUY</span><br>
            <span style="color:#22c55e">Score ≥ +1 → BUY</span><br>
            <span style="color:#eab308">Score = 0  → WAIT</span><br>
            <span style="color:#ef4444">Score ≤ -1 → SELL</span><br>
            <span style="color:#ef4444">Score ≤ -3 → STRONG_SELL</span><br><br>
            <span style="color:#38bdf8">Note: This is only the preliminary signal. Gemini can override it based on news + fuller context analysis.</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Candle data
        st.markdown('<div class="section-label" style="margin-top:1rem">Candle Data Configuration</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="card">
            <div style="font-size:0.82rem;color:#94a3b8;line-height:1.9;font-family:'JetBrains Mono',monospace">
            Timeframe    : 30-minute candles<br>
            Days fetched : 10 calendar days (~65-78 candles per stock)<br>
            Min candles  : 25 required (MACD needs 35+, RSI needs 14+, BB needs 20+)<br>
            Source       : Upstox API v2 historical-candle endpoint<br>
            Market hours : NSE 09:15 AM — 03:30 PM IST (Mon-Fri)
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════
    # SECTION 2 — NEWS SOURCES
    # ═══════════════════════════════════════════════════════
    with s2:
        st.markdown('<div class="section-label">Active News Sources</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="card">
        <div style="font-size:0.78rem;color:#94a3b8;line-height:1.7">
        All news is fetched via <b style="color:#f59e0b">RSS feeds</b> — completely free, no API key, no rate limits.
        News is fetched fresh every time you run analysis. Delay: ~15-30 minutes from publication.
        </div>
        </div>
        """, unsafe_allow_html=True)

        # Global feeds
        global_feeds = [
            {"name": "Reuters Business News",       "url": "feeds.reuters.com/reuters/businessNews",      "type": "Global", "covers": "World economy, corporate earnings, geopolitics affecting markets"},
            {"name": "CNBC World Markets",          "url": "search.cnbc.com (worldmarketsNews)",           "type": "Global", "covers": "Wall Street, US markets, Fed decisions, global indices"},
            {"name": "Yahoo Finance",               "url": "finance.yahoo.com/news/rssindex",             "type": "Global", "covers": "Stock earnings, M&A, corporate news, analyst upgrades/downgrades"},
            {"name": "Economic Times Markets",      "url": "economictimes.indiatimes.com/markets",        "type": "India",  "covers": "NSE/BSE stocks, FII/DII activity, Nifty/Sensex movements"},
            {"name": "Economic Times Economy",      "url": "economictimes.indiatimes.com/news/economy",   "type": "India",  "covers": "RBI policy, inflation, GDP, government schemes affecting markets"},
            {"name": "Mint Markets",                "url": "livemint.com/rss/markets",                    "type": "India",  "covers": "Indian stock market, commodity prices, mutual funds"},
            {"name": "Business Standard Markets",   "url": "business-standard.com/rss/markets-106.rss",  "type": "India",  "covers": "NSE/BSE, company results, sector news"},
            {"name": "Google News - India Markets", "url": "news.google.com (nifty+sensex query)",        "type": "India",  "covers": "Aggregated Indian market news from all sources"},
            {"name": "Google News - Global Economy","url": "news.google.com (global+economy+fed query)",  "type": "Global", "covers": "Fed rates, global trade, dollar index, crude oil"},
            {"name": "Google News - FII/DII",       "url": "news.google.com (FII+DII+india query)",       "type": "India",  "covers": "Foreign and domestic institutional investor flows"},
        ]

        macro_feeds = [
            {"query": "RBI interest rate india",          "covers": "RBI monetary policy, rate cuts/hikes affecting banking stocks"},
            {"query": "US Fed rate decision markets",     "covers": "Federal Reserve decisions, dollar strength, global market impact"},
            {"query": "FII selling buying india",         "covers": "Foreign institutional flows — biggest driver of Indian market direction"},
            {"query": "india inflation GDP economy",      "covers": "Inflation data, GDP numbers, economic indicators"},
            {"query": "crude oil price india impact",     "covers": "Oil prices affecting energy stocks, OMCs, inflation"},
            {"query": "dollar rupee exchange rate",       "covers": "USD/INR rate affecting IT exporters, import-heavy companies"},
        ]

        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown('<div style="font-size:0.72rem;color:#22c55e;font-family:\'JetBrains Mono\',monospace;letter-spacing:1px;margin-bottom:0.5rem">GLOBAL SOURCES</div>', unsafe_allow_html=True)
            for f in [x for x in global_feeds if x["type"] == "Global"]:
                st.markdown(f"""
                <div style="background:#0f172a;border:1px solid #1e2d4a;border-radius:8px;padding:0.7rem;margin-bottom:0.5rem">
                    <div style="font-size:0.8rem;font-weight:700;color:#f1f5f9;font-family:'JetBrains Mono',monospace">{f['name']}</div>
                    <div style="font-size:0.7rem;color:#38bdf8;font-family:'JetBrains Mono',monospace;margin-top:2px">{f['url']}</div>
                    <div style="font-size:0.72rem;color:#64748b;margin-top:4px">{f['covers']}</div>
                </div>
                """, unsafe_allow_html=True)

        with c2:
            st.markdown('<div style="font-size:0.72rem;color:#f59e0b;font-family:\'JetBrains Mono\',monospace;letter-spacing:1px;margin-bottom:0.5rem">INDIAN MARKET SOURCES</div>', unsafe_allow_html=True)
            for f in [x for x in global_feeds if x["type"] == "India"]:
                st.markdown(f"""
                <div style="background:#0f172a;border:1px solid #1e2d4a;border-radius:8px;padding:0.7rem;margin-bottom:0.5rem">
                    <div style="font-size:0.8rem;font-weight:700;color:#f1f5f9;font-family:'JetBrains Mono',monospace">{f['name']}</div>
                    <div style="font-size:0.7rem;color:#38bdf8;font-family:'JetBrains Mono',monospace;margin-top:2px">{f['url']}</div>
                    <div style="font-size:0.72rem;color:#64748b;margin-top:4px">{f['covers']}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown('<div class="section-label" style="margin-top:1rem">Macro News Queries (Google News RSS)</div>', unsafe_allow_html=True)
        for m in macro_feeds:
            st.markdown(f"""
            <div style="background:#0f172a;border:1px solid #1e2d4a;border-radius:8px;padding:0.6rem 0.8rem;margin-bottom:0.4rem;display:flex;align-items:flex-start;gap:12px">
                <span style="color:#a78bfa;font-family:'JetBrains Mono',monospace;font-size:0.72rem;white-space:nowrap">🔍 "{m['query']}"</span>
                <span style="color:#64748b;font-size:0.72rem">{m['covers']}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div class="section-label" style="margin-top:1rem">Stock-Specific News (per stock)</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="card">
            <div style="font-size:0.8rem;color:#94a3b8;line-height:1.8;font-family:'JetBrains Mono',monospace">
            For each stock being analysed, two Google News RSS searches are run:<br>
            1. <span style="color:#f59e0b">"{Company Name} stock share"</span> — e.g. "Reliance Industries stock share"<br>
            2. <span style="color:#f59e0b">"{SYMBOL} NSE"</span> — e.g. "RELIANCE NSE"<br><br>
            Results: Top 4-5 headlines per stock (last 72 hours)<br>
            These are sent to Gemini alongside technical indicators for combined analysis.<br><br>
            <span style="color:#38bdf8">Macro news is fetched once and shared across all stocks in a batch run.</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Live test button
        st.markdown('<div class="section-label" style="margin-top:1rem">Live News Test</div>', unsafe_allow_html=True)
        col_a, col_b = st.columns([2, 1])
        with col_a:
            test_symbol = st.text_input("Test stock news", placeholder="e.g. RELIANCE", label_visibility="collapsed")
        with col_b:
            test_btn = st.button("🔍 Fetch Sample News", use_container_width=True)

        if test_btn and test_symbol.strip():
            with st.spinner("Fetching news..."):
                try:
                    from news_fetcher import fetch_stock_news, fetch_macro_news
                    stock_news = fetch_stock_news(test_symbol.strip().upper(), max_items=5)
                    macro_news = fetch_macro_news(max_items=4)

                    if stock_news:
                        st.markdown(f'<div style="font-size:0.72rem;color:#f59e0b;letter-spacing:1px;font-family:\'JetBrains Mono\',monospace;margin-bottom:0.4rem">{test_symbol.upper()} HEADLINES</div>', unsafe_allow_html=True)
                        for h in stock_news:
                            st.markdown(f'<div style="background:#0f172a;border:1px solid #1e2d4a;border-radius:6px;padding:0.5rem 0.8rem;margin-bottom:0.3rem;font-size:0.78rem;color:#e2e8f0">• {h}</div>', unsafe_allow_html=True)
                    else:
                        st.warning(f"No recent news found for {test_symbol.upper()}")

                    if macro_news:
                        st.markdown('<div style="font-size:0.72rem;color:#38bdf8;letter-spacing:1px;font-family:\'JetBrains Mono\',monospace;margin:0.8rem 0 0.4rem 0">MACRO HEADLINES</div>', unsafe_allow_html=True)
                        for h in macro_news[:3]:
                            st.markdown(f'<div style="background:#0f172a;border:1px solid #1e2d4a;border-radius:6px;padding:0.5rem 0.8rem;margin-bottom:0.3rem;font-size:0.78rem;color:#e2e8f0">• {h}</div>', unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"News fetch error: {e}")

    # ═══════════════════════════════════════════════════════
    # SECTION 3 — STRATEGY RULES
    # ═══════════════════════════════════════════════════════
    with s3:
        st.markdown('<div class="section-label">Current Strategy Rules</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="card">
        <div style="font-size:0.78rem;color:#94a3b8;line-height:1.7">
        Rules are loaded from <b style="color:#38bdf8">strategy_rules.json</b> before every analysis.
        Edit that file anytime — no code changes needed. Gemini reads these AND our local code enforces them as a double check.
        </div>
        </div>
        """, unsafe_allow_html=True)

        try:
            from config import STRATEGY_FILE
            with open(STRATEGY_FILE, "r") as f:
                rules = json.load(f)

            filters = rules.get("filters", {})
            prefs   = rules.get("preferences", {})
            risk    = rules.get("risk_management", {})

            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown('<div style="font-size:0.72rem;color:#22c55e;font-family:\'JetBrains Mono\',monospace;letter-spacing:1px;margin-bottom:0.5rem">FILTERS</div>', unsafe_allow_html=True)
                filter_items = [
                    ("Min R:R Ratio",      filters.get("min_risk_reward", 1.5),  "Trades below this R:R → overridden to WAIT"),
                    ("Min Confidence",     f"{filters.get('min_confidence',60)}%","Signals below this → overridden to WAIT"),
                    ("Avoid RSI Above",    filters.get("avoid_rsi_above", 75),   "BUY when RSI > this → overridden to WAIT"),
                    ("Avoid RSI Below",    filters.get("avoid_rsi_below", 20),   "SELL when RSI < this → overridden to WAIT"),
                    ("Avoid First Mins",   f"{filters.get('avoid_first_minutes',15)} min", "Skip first N minutes of market open"),
                    ("Avoid Last Mins",    f"{filters.get('avoid_last_minutes',15)} min",  "Skip last N minutes before close"),
                    ("Max Trades/Day",     filters.get("max_trades_per_day", 3), "Informational limit"),
                ]
                for label, value, note in filter_items:
                    st.markdown(f"""
                    <div style="background:#0f172a;border:1px solid #1e2d4a;border-radius:8px;padding:0.6rem;margin-bottom:0.4rem">
                        <div style="font-size:0.7rem;color:#475569;font-family:'JetBrains Mono',monospace">{label}</div>
                        <div style="font-size:0.95rem;font-weight:700;color:#22c55e;font-family:'JetBrains Mono',monospace">{value}</div>
                        <div style="font-size:0.68rem;color:#475569;margin-top:2px">{note}</div>
                    </div>
                    """, unsafe_allow_html=True)

            with col2:
                st.markdown('<div style="font-size:0.72rem;color:#38bdf8;font-family:\'JetBrains Mono\',monospace;letter-spacing:1px;margin-bottom:0.5rem">PREFERENCES</div>', unsafe_allow_html=True)
                pref_items = [
                    ("MACD Confirmation", str(prefs.get("require_macd_confirmation", True)),  "BUY needs bullish MACD | SELL needs bearish MACD"),
                    ("EMA Confirmation",  str(prefs.get("require_ema_confirmation", False)), "BUY needs EMA bullish trend"),
                ]
                for label, value, note in pref_items:
                    color = "#22c55e" if value == "True" else "#ef4444"
                    st.markdown(f"""
                    <div style="background:#0f172a;border:1px solid #1e2d4a;border-radius:8px;padding:0.6rem;margin-bottom:0.4rem">
                        <div style="font-size:0.7rem;color:#475569;font-family:'JetBrains Mono',monospace">{label}</div>
                        <div style="font-size:0.95rem;font-weight:700;color:{color};font-family:'JetBrains Mono',monospace">{value}</div>
                        <div style="font-size:0.68rem;color:#475569;margin-top:2px">{note}</div>
                    </div>
                    """, unsafe_allow_html=True)

            with col3:
                st.markdown('<div style="font-size:0.72rem;color:#f59e0b;font-family:\'JetBrains Mono\',monospace;letter-spacing:1px;margin-bottom:0.5rem">RISK MANAGEMENT</div>', unsafe_allow_html=True)
                risk_items = [
                    ("Max Loss/Trade", f"{risk.get('max_loss_per_trade_pct',1.0)}%", "Maximum capital loss per trade"),
                    ("Trailing SL",    str(risk.get("trailing_sl", False)),           "Dynamic stop loss that moves with price"),
                ]
                for label, value, note in risk_items:
                    st.markdown(f"""
                    <div style="background:#0f172a;border:1px solid #1e2d4a;border-radius:8px;padding:0.6rem;margin-bottom:0.4rem">
                        <div style="font-size:0.7rem;color:#475569;font-family:'JetBrains Mono',monospace">{label}</div>
                        <div style="font-size:0.95rem;font-weight:700;color:#f59e0b;font-family:'JetBrains Mono',monospace">{value}</div>
                        <div style="font-size:0.68rem;color:#475569;margin-top:2px">{note}</div>
                    </div>
                    """, unsafe_allow_html=True)

            # Raw JSON viewer
            st.markdown('<div class="section-label" style="margin-top:1rem">Raw strategy_rules.json</div>', unsafe_allow_html=True)
            st.code(json.dumps(rules, indent=2), language="json")

        except Exception as e:
            st.error(f"Could not load strategy rules: {e}")
            st.info("Make sure strategy_rules.json exists in your project folder.")

    # ═══════════════════════════════════════════════════════
    # SECTION 4 — AI CONFIG
    # ═══════════════════════════════════════════════════════
    with s4:
        st.markdown('<div class="section-label">AI Analysis Configuration</div>', unsafe_allow_html=True)

        st.markdown("""
        <div class="card" style="border-left:3px solid #a78bfa">
            <div style="font-size:0.95rem;font-weight:800;color:#f1f5f9;font-family:'JetBrains Mono',monospace">Current AI: Gemini 2.5 Flash</div>
            <div style="font-size:0.78rem;color:#94a3b8;margin-top:6px;line-height:1.7">
            Provider: Google AI Studio<br>
            Model: gemini-2.5-flash<br>
            Tier: Free (500 RPD, 15 RPM)<br>
            API calls per analysis run: <span style="color:#22c55e">1 (batch — all stocks in one call)</span><br>
            Daily usage at 10 stocks: ~1-3 calls per morning routine
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-label" style="margin-top:1rem">What Gemini Receives Per Analysis</div>', unsafe_allow_html=True)
        items = [
            ("📊 Technical Indicators", "RSI, EMA (9+21), MACD (12/26/9), Bollinger Bands (20,2) for each stock"),
            ("📰 Stock-Specific News",  "Top 4-5 headlines for that stock from Google News + ET (last 72 hours)"),
            ("🌍 Macro/Global News",    "Top 4 macro headlines: RBI, Fed, FII/DII, crude, USD/INR (last 48 hours)"),
            ("⚙️ Strategy Rules",       "All filters and preferences from strategy_rules.json"),
            ("🔢 Preliminary Signal",   "Our scoring system's pre-computed signal before AI override"),
        ]
        for icon_label, desc in items:
            st.markdown(f"""
            <div style="background:#0f172a;border:1px solid #1e2d4a;border-radius:8px;padding:0.7rem;margin-bottom:0.4rem;display:flex;gap:12px">
                <span style="color:#a78bfa;font-weight:700;font-family:'JetBrains Mono',monospace;font-size:0.8rem;white-space:nowrap">{icon_label}</span>
                <span style="color:#94a3b8;font-size:0.78rem">{desc}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div class="section-label" style="margin-top:1rem">What Gemini Returns Per Stock</div>', unsafe_allow_html=True)
        outputs = [
            ("signal",             "BUY / SELL / WAIT — final trade recommendation"),
            ("confidence",         "0-100% — how confident Gemini is in the signal"),
            ("entry",              "Suggested entry price based on current price action"),
            ("target",             "Price target — typically BB mid or upper band"),
            ("stop_loss",          "Stop loss level — typically below BB lower band"),
            ("risk_reward",        "R:R ratio e.g. 1:2.5 — must meet minimum rule"),
            ("news_sentiment",     "BULLISH / BEARISH / NEUTRAL — news-only assessment"),
            ("reasoning",          "2-3 plain English sentences covering both technicals AND news"),
            ("indicators_summary", "One line summary of what all indicators are saying"),
        ]
        rows_html = ""
        for field, desc in outputs:
            rows_html += f"""<tr>
                <td style="font-family:'JetBrains Mono',monospace;color:#a78bfa;font-size:0.75rem">{field}</td>
                <td style="font-size:0.75rem;color:#94a3b8">{desc}</td>
            </tr>"""
        st.markdown(f"""
        <table style="width:100%;border-collapse:collapse">
            <thead><tr>
                <th style="text-align:left;padding:8px;font-size:0.62rem;letter-spacing:1px;text-transform:uppercase;color:#475569;font-family:'JetBrains Mono',monospace;border-bottom:1px solid #1e2d4a">Field</th>
                <th style="text-align:left;padding:8px;font-size:0.62rem;letter-spacing:1px;text-transform:uppercase;color:#475569;font-family:'JetBrains Mono',monospace;border-bottom:1px solid #1e2d4a">Description</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-label" style="margin-top:1.5rem">Claude API Swap (When Going Live)</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="card" style="border-left:3px solid #f59e0b">
            <div style="font-size:0.8rem;color:#94a3b8;line-height:1.8">
            When you're ready to go live with real money, swap Gemini for Claude in <b style="color:#38bdf8">ai_analyst.py</b>:<br><br>
            </div>
        </div>
        """, unsafe_allow_html=True)
        st.code("""
# REMOVE (Gemini):
from google import genai
client = genai.Client(api_key=GEMINI_API_KEY)
response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
raw_text = response.text

# ADD (Claude):
import anthropic
client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
response = client.messages.create(
    model="claude-opus-4-5", max_tokens=4096,
    messages=[{"role": "user", "content": prompt}])
raw_text = response.content[0].text
        """, language="python")

    # ═══════════════════════════════════════════════════════
    # SECTION 5 — DATA PIPELINE
    # ═══════════════════════════════════════════════════════
    with s5:
        st.markdown('<div class="section-label">Complete Data Pipeline</div>', unsafe_allow_html=True)

        st.markdown("""
        <div class="card">
        <div style="font-size:0.82rem;color:#94a3b8;line-height:2;font-family:'JetBrains Mono',monospace">
        <span style="color:#38bdf8">STEP 1 — AUTH</span><br>
        &nbsp;&nbsp;Load token from db/upstox_token.json<br>
        &nbsp;&nbsp;If expired (&gt;23 hrs) → browser login → new token saved<br>
        &nbsp;&nbsp;Token expires: 3:30 AM next day (login once per morning)<br><br>

        <span style="color:#38bdf8">STEP 2 — WATCHLIST</span><br>
        &nbsp;&nbsp;Read active symbols from trades.db → watchlist table<br>
        &nbsp;&nbsp;Falls back to config.py WATCHLIST if DB is empty<br>
        &nbsp;&nbsp;Add any NSE stock → auto-lookup instrument key → saved to DB<br><br>

        <span style="color:#38bdf8">STEP 3 — FETCH CANDLES (per stock)</span><br>
        &nbsp;&nbsp;Upstox API v2 → /historical-candle/{instrument_key}/30minute<br>
        &nbsp;&nbsp;days_back=10 → ~65-78 candles per stock<br>
        &nbsp;&nbsp;Returns: timestamp, open, high, low, close, volume<br><br>

        <span style="color:#38bdf8">STEP 4 — CALCULATE INDICATORS (per stock)</span><br>
        &nbsp;&nbsp;pandas-ta → RSI(14), EMA(9), EMA(21), MACD(12,26,9), BB(20,2)<br>
        &nbsp;&nbsp;Crossover detection: Golden Cross, Death Cross, MACD Cross<br>
        &nbsp;&nbsp;Preliminary signal scoring (-6 to +6)<br><br>

        <span style="color:#38bdf8">STEP 5 — FETCH NEWS (batch)</span><br>
        &nbsp;&nbsp;Macro news: fetched once, shared across all stocks<br>
        &nbsp;&nbsp;Stock news: 2 Google News RSS queries per stock<br>
        &nbsp;&nbsp;Total RSS feeds: 10 global/Indian + 6 macro + 2 per stock<br><br>

        <span style="color:#22c55e">STEP 6 — GEMINI AI ANALYSIS (1 API call for ALL stocks)</span><br>
        &nbsp;&nbsp;One batch prompt: all stocks + all indicators + all news<br>
        &nbsp;&nbsp;Gemini returns JSON with signal, confidence, entry, target, SL<br>
        &nbsp;&nbsp;Local rule filter double-checks results<br>
        &nbsp;&nbsp;Rule violations → signal overridden to WAIT<br><br>

        <span style="color:#38bdf8">STEP 7 — DISPLAY</span><br>
        &nbsp;&nbsp;Results table: signal, news sentiment, confidence bar<br>
        &nbsp;&nbsp;Side panel: full detail, AI reasoning, news headlines, indicators<br>
        &nbsp;&nbsp;Date pills: when analysed + when to place trade<br><br>

        <span style="color:#38bdf8">STEP 8 — TRADE JOURNAL (optional)</span><br>
        &nbsp;&nbsp;Log trade → saved to trades.db with all analysis data<br>
        &nbsp;&nbsp;Close trade → P&L auto-calculated → WIN/LOSS/BREAKEVEN<br>
        &nbsp;&nbsp;Journal stats: win rate, total P&L, best/worst trade
        </div>
        </div>
        """, unsafe_allow_html=True)

        # File structure
        st.markdown('<div class="section-label" style="margin-top:1rem">File Structure</div>', unsafe_allow_html=True)
        files = [
            (".env",                  "API keys — never share this file"),
            ("config.py",             "All settings: timeframes, indicator periods, paths"),
            ("auth.py",               "Upstox OAuth2 login + token save/load"),
            ("data_fetcher.py",       "Fetch OHLCV candles + watchlist DB management"),
            ("indicators.py",         "Calculate RSI, EMA, MACD, BB from candle data"),
            ("news_fetcher.py",       "Fetch global + Indian news via RSS feeds"),
            ("ai_analyst.py",         "Gemini analysis + stock recommendations from news"),
            ("trade_journal.py",      "Log trades, close trades, P&L tracking"),
            ("morning_brief.py",      "Format daily report + save to logs/"),
            ("strategy_rules.json",   "Editable trading rules — no code changes needed"),
            ("dashboard.py",          "Streamlit UI — all 4 tabs"),
            ("system_info.py",        "This tab — live system documentation"),
            ("db/trades.db",          "SQLite: watchlist + instrument_keys + trades"),
            ("db/upstox_token.json",  "Upstox auth token (auto-refreshed daily)"),
            ("logs/",                 "Saved morning briefs: morning_brief_YYYY-MM-DD.txt"),
        ]
        rows_html = ""
        for fname, desc in files:
            rows_html += f"""<tr>
                <td style="font-family:'JetBrains Mono',monospace;color:#38bdf8;font-size:0.72rem;white-space:nowrap">{fname}</td>
                <td style="font-size:0.75rem;color:#64748b">{desc}</td>
            </tr>"""
        st.markdown(f"""
        <table style="width:100%;border-collapse:collapse">
            <thead><tr>
                <th style="text-align:left;padding:8px;font-size:0.62rem;letter-spacing:1px;text-transform:uppercase;color:#475569;font-family:'JetBrains Mono',monospace;border-bottom:1px solid #1e2d4a;white-space:nowrap">File</th>
                <th style="text-align:left;padding:8px;font-size:0.62rem;letter-spacing:1px;text-transform:uppercase;color:#475569;font-family:'JetBrains Mono',monospace;border-bottom:1px solid #1e2d4a">Purpose</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
        """, unsafe_allow_html=True)

        # DB Schema
        st.markdown('<div class="section-label" style="margin-top:1rem">Database Schema (trades.db)</div>', unsafe_allow_html=True)
        st.code("""
-- Watchlist: which stocks to analyse
CREATE TABLE watchlist (
    symbol      TEXT PRIMARY KEY,
    added_on    TEXT,
    is_active   INTEGER DEFAULT 1   -- 0 = soft deleted
)

-- Instrument keys: NSE_EQ|ISIN for every stock
CREATE TABLE instrument_keys (
    symbol          TEXT PRIMARY KEY,
    instrument_key  TEXT NOT NULL,  -- e.g. NSE_EQ|INE002A01018
    added_on        TEXT
)

-- Trades: full journal with P&L
CREATE TABLE trades (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_date     TEXT,   -- when analysis was run
    analysis_time     TEXT,
    trade_date        TEXT,   -- when to place the trade
    trade_day         TEXT,   -- human readable e.g. "TOMORROW (Monday)"
    symbol            TEXT,
    signal            TEXT,   -- BUY / SELL / WAIT
    confidence        INTEGER,
    entry             REAL,
    target            REAL,
    stop_loss         REAL,
    risk_reward       TEXT,
    reasoning         TEXT,
    news_sentiment    TEXT,   -- BULLISH / BEARISH / NEUTRAL
    status            TEXT,   -- OPEN / CLOSED
    exit_price        REAL,
    pnl               REAL,   -- auto-calculated
    outcome           TEXT,   -- WIN / LOSS / BREAKEVEN
    notes             TEXT
)
        """, language="sql")