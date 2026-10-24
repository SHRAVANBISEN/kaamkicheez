# dashboard.py — StockTradingAlgo Dashboard
# Run: streamlit run dashboard.py

import streamlit as st
from datetime import datetime

st.set_page_config(page_title="StockTradingAlgo", page_icon="📈",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
html,body,[class*="css"]{font-family:'Segoe UI',Arial,sans-serif;background:#0a0e1a;color:#e2e8f0}
.stApp{background:#0a0e1a}
#MainMenu,footer,header{visibility:hidden}
.block-container{padding:1.2rem 2rem}
.stTabs [data-baseweb="tab-list"]{background:#111827;border-radius:10px;padding:4px;border:1px solid #1e2d4a;gap:4px;overflow-x:auto}
.stTabs [data-baseweb="tab"]{background:transparent;color:#64748b;border-radius:8px;font-family:'JetBrains Mono',monospace;font-size:0.75rem;font-weight:700;letter-spacing:1px;padding:8px 16px}
.stTabs [aria-selected="true"]{background:#1d4ed8!important;color:white!important}
.stTabs [data-baseweb="tab-panel"]{padding-top:1.2rem}
.dash-header{padding:1.3rem 1.5rem;background:linear-gradient(120deg,#14213b,#0f172a);border:1px solid #263958;border-radius:14px;margin-bottom:0.8rem}
.dash-title{font-size:1.5rem;font-weight:800;color:#f1f5f9}
.dash-subtitle{font-size:0.78rem;color:#a7b7d0;font-family:'Segoe UI',sans-serif;margin-top:5px}
.live-dot{width:8px;height:8px;background:#60a5fa;border-radius:50%;display:inline-block;margin-right:9px}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.3}}
.section-label{font-size:0.72rem;font-weight:600;letter-spacing:1px;color:#a7b7d0;text-transform:uppercase;margin-bottom:0.5rem;font-family:'Segoe UI',sans-serif}
.card{background:#111827;border:1px solid #1e2d4a;border-radius:10px;padding:1rem 1.2rem;margin-bottom:0.8rem}
.log-box{background:#070b14;border:1px solid #1e2d4a;border-radius:8px;padding:1rem;font-family:'JetBrains Mono',monospace;font-size:0.75rem;max-height:200px;overflow-y:auto;line-height:1.8}
.log-line{color:#94a3b8}.log-success{color:#22c55e}.log-info{color:#38bdf8}.log-warn{color:#f59e0b}.log-error{color:#ef4444}
.badge-buy{background:#052e16;color:#22c55e;border:1px solid #166534;padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:700;font-family:'JetBrains Mono',monospace}
.badge-sell{background:#2d0a0a;color:#ef4444;border:1px solid #7f1d1d;padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:700;font-family:'JetBrains Mono',monospace}
.badge-wait{background:#1c1a08;color:#eab308;border:1px solid #713f12;padding:3px 10px;border-radius:20px;font-size:0.72rem;font-weight:700;font-family:'JetBrains Mono',monospace}
.badge-open{background:#0c1a2e;color:#38bdf8;border:1px solid #0369a1;padding:3px 8px;border-radius:20px;font-size:0.7rem;font-family:'JetBrains Mono',monospace}
.badge-win{background:#052e16;color:#22c55e;border:1px solid #166534;padding:3px 8px;border-radius:20px;font-size:0.7rem;font-family:'JetBrains Mono',monospace}
.badge-loss{background:#2d0a0a;color:#ef4444;border:1px solid #7f1d1d;padding:3px 8px;border-radius:20px;font-size:0.7rem;font-family:'JetBrains Mono',monospace}
.metric-tile{background:#0f172a;border:1px solid #1e2d4a;border-radius:8px;padding:0.8rem 1rem;text-align:center}
.metric-label{font-size:0.68rem;color:#a7b7d0;letter-spacing:1px;text-transform:uppercase;font-family:'Segoe UI',sans-serif}
.metric-value{font-size:1.15rem;font-weight:700;color:#f1f5f9;font-family:'JetBrains Mono',monospace;margin-top:2px}
.metric-value.green{color:#22c55e}.metric-value.red{color:#ef4444}.metric-value.yellow{color:#eab308}.metric-value.blue{color:#38bdf8}
.results-table{width:100%;border-collapse:collapse;font-size:0.8rem}
.results-table th{text-align:left;padding:8px 12px;font-size:0.62rem;letter-spacing:1.5px;text-transform:uppercase;color:#475569;font-family:'JetBrains Mono',monospace;border-bottom:1px solid #1e2d4a}
.results-table td{padding:10px 12px;border-bottom:1px solid #111827;font-family:'JetBrains Mono',monospace;font-size:0.78rem;color:#cbd5e1}
.results-table tr:hover td{background:#111827}
.symbol-cell{font-weight:700;color:#f1f5f9}
.date-pill{display:inline-block;background:#0c1a2e;border:1px solid #1e4080;color:#60a5fa;padding:3px 10px;border-radius:20px;font-size:0.68rem;font-family:'JetBrains Mono',monospace}
.trade-date-pill{display:inline-block;background:#0d2010;border:1px solid #166534;color:#4ade80;padding:3px 10px;border-radius:20px;font-size:0.68rem;font-family:'JetBrains Mono',monospace}
.panel-signal{font-size:1.8rem;font-weight:800;font-family:'JetBrains Mono',monospace;margin:0.4rem 0}
.panel-signal.buy{color:#22c55e}.panel-signal.sell{color:#ef4444}.panel-signal.wait{color:#eab308}
.indicator-row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1e2d4a;font-size:0.75rem;font-family:'JetBrains Mono',monospace}
.indicator-row:last-child{border-bottom:none}
.ind-label{color:#64748b}.ind-value{color:#e2e8f0;font-weight:600}
.reasoning-box{background:#070b14;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;padding:0.8rem;font-size:0.78rem;color:#94a3b8;line-height:1.7}
.violation-box{background:#1a0a0a;border-left:3px solid #ef4444;border-radius:0 8px 8px 0;padding:0.8rem;font-size:0.75rem;color:#fca5a5;line-height:1.7;margin-top:6px}
.brief-box{background:#070b14;border:1px solid #1e2d4a;border-radius:8px;padding:1.2rem;font-family:'JetBrains Mono',monospace;font-size:0.75rem;color:#94a3b8;line-height:1.8;white-space:pre-wrap;max-height:600px;overflow-y:auto}
.stButton>button{background:linear-gradient(135deg,#1d4ed8,#3b82f6)!important;color:white!important;border:none!important;border-radius:8px!important;font-family:'JetBrains Mono',monospace!important;font-weight:700!important;font-size:0.8rem!important;letter-spacing:1px!important;transition:all 0.2s!important}
.stButton>button:hover{filter:brightness(1.1)}
button:focus-visible,a:focus-visible{outline:2px solid #93c5fd!important;outline-offset:3px}
[data-testid="stDataFrame"],[data-testid="stTable"]{border-radius:10px}
@media(max-width:850px){.block-container{padding:1rem}.dash-header{padding:1rem}.stTabs [data-baseweb="tab"]{padding:8px 10px;letter-spacing:0}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
.stTextInput>div>div>input{background:#111827!important;border:1px solid #1e2d4a!important;color:#f1f5f9!important;border-radius:8px!important;font-family:'JetBrains Mono',monospace!important}
.stSelectbox>div>div,.stNumberInput>div>div>input{background:#111827!important;border:1px solid #1e2d4a!important;border-radius:8px!important;color:#f1f5f9!important}
.stTextArea>div>textarea{background:#111827!important;border:1px solid #1e2d4a!important;color:#f1f5f9!important;border-radius:8px!important;font-family:'JetBrains Mono',monospace!important}
.wl-tag{display:inline-block;background:#0f172a;border:1px solid #1e2d4a;color:#94a3b8;padding:3px 10px;border-radius:20px;font-size:0.72rem;font-family:'JetBrains Mono',monospace;margin:2px}
hr{border-color:#1e2d4a}
.news-box{background:#070b14;border-left:3px solid #f59e0b;border-radius:0 8px 8px 0;padding:0.8rem;font-size:0.75rem;color:#94a3b8;line-height:1.8;margin-top:6px}
.rec-card{background:#0f172a;border:1px solid #1e2d4a;border-radius:10px;padding:1rem;margin-bottom:0.6rem}
.theme-tag{display:inline-block;background:#1e2d4a;color:#60a5fa;padding:2px 8px;border-radius:12px;font-size:0.68rem;font-family:'JetBrains Mono',monospace;margin:2px}
</style>
""", unsafe_allow_html=True)

# ── Imports ────────────────────────────────────────────────
try:
    from stocktrading.auth import get_access_token
    from stocktrading.data_fetcher import (
        fetch_candles, fetch_single_stock,
        init_watchlist_db, get_watchlist_from_db,
        add_stock_to_watchlist, remove_stock_from_watchlist,
        get_all_available_symbols, lookup_and_save_instrument_key,
        get_instrument_key
    )
    from stocktrading.indicators import calculate_indicators, calculate_all
    from stocktrading.intraday_engine import calculate_features
    from stocktrading.ai_analyst import analyze, analyze_all_at_once, recommend_stocks_from_news
    from stocktrading.trade_journal import (
        init_trade_journal, log_trade, close_trade,
        get_all_trades, get_open_trades, get_journal_summary,
        delete_trade, _get_trade_date_info
    )
    from stocktrading.morning_brief import generate_morning_brief
    from stocktrading.system_info import render_system_info_tab, render_indicator_snapshot, render_decision_trace
    from stocktrading.llm_provider import get_settings
    from stocktrading.config import DEFAULT_TIMEFRAME, LOG_DIR
    import os
    IMPORTS_OK = True
except Exception as e:
    IMPORTS_OK = False
    IMPORT_ERROR = str(e)

# ── Session state ──────────────────────────────────────────
for k, v in {
    "log_lines": [], "results": {}, "indicators_map": {},
    "selected_stock": None, "token": None,
    "search_result": None, "search_ind": None,
    "trade_date_info": None, "morning_brief_text": None,
    "morning_brief_path": None,
    "recommendations": None, "rec_error": None, "rec_sentiment": None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Helpers ────────────────────────────────────────────────

def log(msg, kind="line"):
    css = {"line":"log-line","success":"log-success","info":"log-info",
           "warn":"log-warn","error":"log-error"}.get(kind,"log-line")
    ts  = datetime.now().strftime("%H:%M:%S")
    st.session_state.log_lines.append(f'<span class="{css}">[{ts}] {msg}</span>')

def render_log(ph):
    html = "<br>".join(st.session_state.log_lines[-40:])
    ph.markdown(f'<div class="log-box">{html}</div>', unsafe_allow_html=True)

def signal_badge(s):
    s = str(s).upper()
    if "BUY"  in s: return '<span class="badge-buy">🟢 BUY</span>'
    if "SELL" in s: return '<span class="badge-sell">🔴 SELL</span>'
    return '<span class="badge-wait">🟡 WAIT</span>'

def outcome_badge(o):
    o = str(o).upper() if o else ""
    if o == "WIN":  return '<span class="badge-win">✅ WIN</span>'
    if o == "LOSS": return '<span class="badge-loss">❌ LOSS</span>'
    return '<span class="badge-open">🔵 OPEN</span>'

def news_sentiment_badge(s):
    s = str(s).upper() if s else ""
    if s == "BULLISH": return '<span style="background:#052e16;color:#22c55e;border:1px solid #166534;padding:2px 8px;border-radius:20px;font-size:0.68rem;font-family:\'JetBrains Mono\',monospace">📈 BULLISH</span>'
    if s == "BEARISH": return '<span style="background:#2d0a0a;color:#ef4444;border:1px solid #7f1d1d;padding:2px 8px;border-radius:20px;font-size:0.68rem;font-family:\'JetBrains Mono\',monospace">📉 BEARISH</span>'
    return '<span style="background:#1c1a08;color:#eab308;border:1px solid #713f12;padding:2px 8px;border-radius:20px;font-size:0.68rem;font-family:\'JetBrains Mono\',monospace">➡️ NEUTRAL</span>'

def conf_color(c):
    if not c: return "#64748b"
    if c >= 70: return "#22c55e"
    if c >= 50: return "#eab308"
    return "#ef4444"

def get_token():
    if st.session_state.token:
        return st.session_state.token
    try:
        log("🔐 Loading token...", "info")
        token = get_access_token()
        if token:
            st.session_state.token = token
            log("✅ Token loaded", "success")
            return token
        log("Token failed - run python -m stocktrading.auth first", "error")
        return None
    except Exception as e:
        log(f"❌ Auth error: {e}", "error")
        return None


# ── Full analysis pipeline ─────────────────────────────────

def run_pipeline(symbols_override=None, log_ph=None):
    """
    Runs full pipeline: fetch -> indicators -> selected LLM -> rule validation.
    Returns (all_indicators, all_results) dicts.
    symbols_override: if provided, analyse these instead of watchlist.
    """
    try:
        get_settings()
    except ValueError as exc:
        log(f"Invalid model configuration: {exc}", "error")
        if log_ph:
            render_log(log_ph)
        return {}, {}
    token = get_token()
    if log_ph: render_log(log_ph)
    if not token:
        return {}, {}

    watchlist = symbols_override or get_watchlist_from_db()

    # Phase 1 — Fetch
    if log_ph:
        log("── PHASE 1: FETCHING DATA ───────────", "line")
        render_log(log_ph)

    raw_data = {}
    for symbol in watchlist:
        if log_ph:
            log(f"📡 Fetching {symbol}...", "line")
            render_log(log_ph)
        df = fetch_candles(symbol, token, DEFAULT_TIMEFRAME, days_back=10)
        if df is not None:
            raw_data[symbol] = df
            if log_ph:
                log(f"✅ {symbol} — {len(df)} candles | ₹{df.iloc[-1]['close']:.2f}", "success")
                render_log(log_ph)
        else:
            if log_ph:
                log(f"❌ {symbol} — fetch failed", "error")
                render_log(log_ph)

    # Phase 2 — Indicators
    if log_ph:
        log("── PHASE 2: INDICATORS ──────────────", "line")
        render_log(log_ph)

    all_indicators = {}
    for symbol, df in raw_data.items():
        try:
            ind = calculate_features(df.copy())
            if ind:
                all_indicators[symbol] = ind
                if log_ph:
                    log(f"✅ {symbol} — RSI:{ind['rsi']} | {ind['ema_trend']} | {ind['preliminary_signal']}", "success")
                    render_log(log_ph)
        except Exception as e:
            if log_ph:
                log(f"❌ {symbol} — {e}", "error")
                render_log(log_ph)

    # Phase 3: selected model
    if log_ph:
        log(f"PHASE 3: {get_settings().provider.upper()} ({len(all_indicators)} stocks, one batch)", "info")
        render_log(log_ph)

    all_results = {}
    try:
        all_results = analyze_all_at_once(all_indicators, fetch_news=True)
        for symbol, result in all_results.items():
            if log_ph:
                signal = result.get("signal","?")
                conf   = result.get("confidence") or 0
                viols  = result.get("rule_violations",[])
                vstr   = f" ⚠️{len(viols)}" if viols else ""
                log(f"✅ {symbol} → {signal} | {conf}%{vstr}", "success")
                render_log(log_ph)
    except Exception as e:
        if log_ph:
            log(f"Model analysis error: {e}", "error")
            render_log(log_ph)

    return all_indicators, all_results


def run_full_analysis(log_ph):
    st.session_state.log_lines      = []
    st.session_state.results        = {}
    st.session_state.indicators_map = {}
    st.session_state.selected_stock = None

    date_info = _get_trade_date_info()
    st.session_state.trade_date_info = date_info

    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "line")
    log("  STOCKTRADINGALGO — ANALYSIS", "info")
    log(f"  {date_info['analysis_date']} {date_info['analysis_time']}", "info")
    log(f"  Trade: {date_info['trade_day']}", "info")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "line")
    render_log(log_ph)

    ind, res = run_pipeline(log_ph=log_ph)

    st.session_state.indicators_map = ind
    st.session_state.results        = res

    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "line")
    log(f"✅ DONE — {len(res)} stocks | Trade: {date_info['trade_day']}", "success")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "line")
    render_log(log_ph)


def run_single_analysis(symbol, log_ph):
    """On-demand single stock analysis."""
    st.session_state.search_result = None
    st.session_state.search_ind    = None
    st.session_state.log_lines     = []
    try:
        get_settings()
    except ValueError as exc:
        log(f"Invalid model configuration: {exc}", "error")
        render_log(log_ph)
        return

    date_info = _get_trade_date_info()
    st.session_state.trade_date_info = date_info

    log(f"── ON-DEMAND: {symbol} ─────────────", "info")
    render_log(log_ph)

    token = get_token()
    render_log(log_ph)
    if not token:
        return

    # Check/fetch instrument key
    key = get_instrument_key(symbol)
    if not key:
        log(f"🔍 Looking up {symbol} on NSE...", "info")
        render_log(log_ph)
        key = lookup_and_save_instrument_key(symbol)
        if not key:
            log(f"❌ {symbol} not found on NSE — check symbol", "error")
            render_log(log_ph)
            return
        log(f"✅ Instrument key found and saved", "success")
        render_log(log_ph)

    log(f"📡 Fetching {symbol}...", "line")
    render_log(log_ph)
    df = fetch_single_stock(symbol, token)
    if df is None:
        log(f"❌ Could not fetch {symbol}", "error")
        render_log(log_ph)
        return
    log(f"✅ {len(df)} candles | ₹{df.iloc[-1]['close']:.2f}", "success")
    render_log(log_ph)

    log("🔢 Calculating indicators...", "line")
    render_log(log_ph)
    try:
        ind = calculate_features(df.copy())
    except (ValueError, KeyError, TypeError) as exc:
        log(f"Candle analysis rejected: {exc}", "error")
        render_log(log_ph)
        return
    log(f"✅ RSI:{ind['rsi']} | {ind['preliminary_signal']}", "success")
    render_log(log_ph)

    log(f"{get_settings().provider} analysing {symbol}...", "info")
    render_log(log_ph)
    log(f"📰 Fetching news for {symbol}...", "info")
    render_log(log_ph)
    try:
        result = analyze(ind, fetch_news=True)
    except (ValueError, OSError, KeyError) as exc:
        log(f"Analysis could not be completed: {exc}", "error")
        render_log(log_ph)
        return
    st.session_state.search_result = result
    st.session_state.search_ind    = ind
    log(f"✅ {result.get('signal')} | {result.get('confidence')}%", "success")
    log(f"📅 Trade: {date_info['trade_day']}", "info")
    render_log(log_ph)


# ── Side panel ─────────────────────────────────────────────

def render_side_panel(symbol, analysis, indicators):
    signal       = str(analysis.get("signal","WAIT")).upper()
    signal_class = {"BUY":"buy","SELL":"sell"}.get(signal,"wait")
    conf         = analysis.get("confidence", 0) or 0
    violations   = analysis.get("rule_violations", [])
    date_info    = st.session_state.trade_date_info or _get_trade_date_info()

    st.markdown(f'<div style="font-size:1rem;font-weight:800;color:#f1f5f9">📊 {symbol}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div style="margin:6px 0"><span class="date-pill">📅 {date_info["analysis_date"]} {date_info["analysis_time"]}</span></div>'
        f'<div style="margin:4px 0 10px 0"><span class="trade-date-pill">🚀 {date_info["trade_day"]}</span></div>',
        unsafe_allow_html=True
    )

    # News sentiment
    news_sent = analysis.get("news_sentiment", "NEUTRAL")
    col_sig, col_news = st.columns([1, 1])
    with col_sig:
        st.markdown(f'<div class="panel-signal {signal_class}">{signal}</div>', unsafe_allow_html=True)
    with col_news:
        st.markdown(f'<div style="margin-top:0.5rem">{news_sentiment_badge(news_sent)}</div>', unsafe_allow_html=True)

    st.caption(f"Model confidence: {conf}% (not win probability)")
    st.progress(conf / 100)

    if violations:
        st.markdown(
            f'<div class="violation-box">{"<br>".join(["⚠️ " + v for v in violations])}</div>',
            unsafe_allow_html=True
        )

    if signal in ["BUY","SELL"] and not violations:
        c1, c2, c3 = st.columns(3)
        with c1: st.markdown(f'<div class="metric-tile"><div class="metric-label">Entry</div><div class="metric-value">₹{analysis.get("entry","—")}</div></div>', unsafe_allow_html=True)
        with c2: st.markdown(f'<div class="metric-tile"><div class="metric-label">Target</div><div class="metric-value green">₹{analysis.get("target","—")}</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-tile"><div class="metric-label">SL</div><div class="metric-value red">₹{analysis.get("stop_loss","—")}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-tile" style="margin-top:6px"><div class="metric-label">Risk / Reward</div><div class="metric-value yellow">{analysis.get("risk_reward","—")}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    if signal in ["BUY","SELL"] and not violations:
        st.markdown('<div class="section-label">Log This Trade</div>', unsafe_allow_html=True)
        notes_input = st.text_input("Notes", key=f"notes_{symbol}", placeholder="optional notes...")
        if st.button(f"📝 Log {symbol}", key=f"log_{symbol}", use_container_width=True):
            try:
                trade_id, trade_day = log_trade(analysis, indicators, notes=notes_input)
                st.success(f"✅ #{trade_id} logged — {trade_day}")
            except Exception as e:
                st.error(f"❌ {e}")

    st.markdown('<div class="section-label">AI Reasoning</div>', unsafe_allow_html=True)
    render_decision_trace(analysis)
    st.markdown(f'<div class="reasoning-box">{analysis.get("reasoning","—")}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="reasoning-box" style="border-color:#8b5cf6;margin-top:6px"><b style="color:#8b5cf6">Summary:</b> {analysis.get("indicators_summary","—")}</div>', unsafe_allow_html=True)

    # News headlines used in analysis
    news_headlines  = analysis.get("news_headlines", [])
    macro_headlines = analysis.get("macro_headlines", [])
    if news_headlines or macro_headlines:
        st.markdown('<div class="section-label" style="margin-top:1rem">News Used in Analysis</div>', unsafe_allow_html=True)
        news_html = ""
        if news_headlines:
            news_html += f"<b style='color:#f59e0b'>{symbol} News:</b><br>"
            for h in news_headlines[:4]:
                news_html += f"• {h[:90]}<br>"
        if macro_headlines:
            news_html += "<br><b style='color:#38bdf8'>Macro/Global:</b><br>"
            for h in macro_headlines[:3]:
                news_html += f"• {h[:90]}<br>"
        st.markdown(f'<div class="news-box">{news_html}</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">Indicators</div>', unsafe_allow_html=True)
    render_indicator_snapshot(indicators)
    rows = [
        ("Close",f"₹{indicators.get('close','—')}"),("RSI",f"{indicators.get('rsi','—')} — {indicators.get('rsi_zone','—')}"),
        ("EMA 9",f"₹{indicators.get('ema9','—')}"),("EMA 21",f"₹{indicators.get('ema21','—')}"),
        ("EMA Trend",indicators.get('ema_trend','—')),("EMA Cross",indicators.get('ema_crossover','—')),
        ("MACD",str(indicators.get('macd','—'))),("MACD Hist",str(indicators.get('macd_hist','—'))),
        ("MACD Mom",indicators.get('macd_momentum','—')),("MACD Cross",indicators.get('macd_crossover','—')),
        ("BB Upper",f"₹{indicators.get('bb_upper','—')}"),("BB Mid",f"₹{indicators.get('bb_mid','—')}"),
        ("BB Lower",f"₹{indicators.get('bb_lower','—')}"),("BB Pos",indicators.get('bb_position','—')),
        ("Pre-Signal",indicators.get('preliminary_signal','—')),
    ]
    rows_html = "".join([f'<div class="indicator-row"><span class="ind-label">{l}</span><span class="ind-value">{v}</span></div>' for l,v in rows])
    st.markdown(f'<div class="card" style="padding:0.4rem 1rem">{rows_html}</div>', unsafe_allow_html=True)


# ── Recommendations tab ────────────────────────────────────

def render_recommendations_tab():
    st.markdown('<div class="section-label">Stock Recommendations from Live News</div>', unsafe_allow_html=True)
    st.info("The selected model turns available Indian/global RSS headlines into watchlist ideas. "
            "These are news-only leads, not validated intraday entries; run full analysis before evaluating a trade.")

    if st.button("🌐 FIND STOCKS FROM LIVE NEWS", use_container_width=True):
        with st.spinner("Fetching available news and requesting model analysis..."):
            try:
                known  = get_all_available_symbols()
                result, error = recommend_stocks_from_news(known_symbols=known)
                st.session_state.recommendations = result
                st.session_state.rec_error       = error
                if result:
                    st.session_state.rec_sentiment = {
                        "sentiment": result.get("market_sentiment","MIXED"),
                        "reasoning": result.get("sentiment_reasoning",""),
                        "themes":    result.get("key_themes",[]),
                    }
            except Exception as e:
                st.session_state.rec_error = str(e)

    if st.session_state.rec_error:
        st.error(f"❌ {st.session_state.rec_error}")

    recs = st.session_state.recommendations
    if not recs:
        if not st.session_state.rec_error:
            st.markdown('<div class="card" style="text-align:center;color:#475569;padding:2rem"><div style="font-size:2rem">🌐</div><div style="font-size:0.8rem;font-family:\'JetBrains Mono\',monospace;margin-top:0.5rem">Click button to scan live news for tradeable stocks</div></div>', unsafe_allow_html=True)
        return

    # Market sentiment banner
    sent_data  = st.session_state.rec_sentiment or {}
    sentiment  = sent_data.get("sentiment","MIXED")
    sent_color = {"BULLISH":"#22c55e","BEARISH":"#ef4444","MIXED":"#eab308"}.get(sentiment,"#eab308")
    themes     = sent_data.get("themes",[])
    themes_html = " ".join([f'<span class="theme-tag">{t}</span>' for t in themes])

    st.markdown(f"""
    <div class="card" style="border-color:{sent_color}40">
        <div style="font-size:0.65rem;color:#475569;letter-spacing:2px;text-transform:uppercase;font-family:'JetBrains Mono',monospace">Market Sentiment</div>
        <div style="font-size:1.4rem;font-weight:800;color:{sent_color};font-family:'JetBrains Mono',monospace">{sentiment}</div>
        <div style="font-size:0.78rem;color:#94a3b8;margin-top:4px">{sent_data.get('reasoning','')}</div>
        <div style="margin-top:8px">{themes_html}</div>
    </div>
    """, unsafe_allow_html=True)

    recommendations = recs.get("recommendations",[])
    if not recommendations:
        st.info("No specific stock recommendations from current news.")
        return

    st.markdown(f'<div class="section-label">{len(recommendations)} Stocks Identified</div>', unsafe_allow_html=True)
    st.caption("News-based leads only. Go to Analysis tab for full technical + news analysis.")

    for rec in recommendations:
        symbol    = rec.get("symbol","?")
        company   = rec.get("company","")
        direction = rec.get("direction","NEUTRAL")
        conf      = rec.get("confidence",0)
        driver    = rec.get("news_driver","")
        reasoning = rec.get("reasoning","")
        sector    = rec.get("sector","")
        urgency   = rec.get("urgency","")
        dir_color = {"BULLISH":"#22c55e","BEARISH":"#ef4444"}.get(direction,"#eab308")
        urg_color = {"TODAY":"#ef4444","TOMORROW":"#f59e0b"}.get(urgency,"#94a3b8")
        cc        = conf_color(conf)

        st.markdown(f"""
        <div class="rec-card">
            <div style="display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                    <span style="font-size:1.1rem;font-weight:800;font-family:'JetBrains Mono',monospace;color:#f1f5f9">{symbol}</span>
                    <span style="font-size:0.75rem;color:#64748b;font-family:'JetBrains Mono',monospace"> — {company} · {sector}</span>
                </div>
                <div style="text-align:right">
                    <span style="color:{dir_color};font-weight:800;font-family:'JetBrains Mono',monospace">{direction}</span>
                    <span style="margin-left:8px;color:{cc};font-family:'JetBrains Mono',monospace">{conf}%</span>
                    <br><span style="color:{urg_color};font-size:0.68rem;font-family:'JetBrains Mono',monospace">{urgency}</span>
                </div>
            </div>
            <div style="font-size:0.75rem;color:#f59e0b;margin-top:4px;line-height:1.5">📰 {driver[:120]}</div>
            <div style="font-size:0.78rem;color:#94a3b8;margin-top:6px;line-height:1.6">{reasoning}</div>
        </div>
        """, unsafe_allow_html=True)
        st.caption(f"→ To analyse: go to Analysis tab → On-Demand → type {symbol}")


# ── Journal tab ────────────────────────────────────────────

def render_journal_tab():
    st.markdown('<div class="section-label">Trade Journal</div>', unsafe_allow_html=True)
    try:
        summary = get_journal_summary()
        cols    = st.columns(6)
        tiles   = [
            ("Total",    str(summary["total_trades"]),  ""),
            ("Open",     str(summary["open_trades"]),   "blue"),
            ("Win Rate", f"{summary['win_rate']}%",     "green" if summary["win_rate"] >= 50 else "red"),
            ("Wins",     str(summary["wins"]),          "green"),
            ("Losses",   str(summary["losses"]),        "red"),
            ("P&L",      f"₹{summary['total_pnl']}",   "green" if summary["total_pnl"] >= 0 else "red"),
        ]
        for col, (label, value, color) in zip(cols, tiles):
            with col:
                st.markdown(f'<div class="metric-tile"><div class="metric-label">{label}</div><div class="metric-value {color}">{value}</div></div>', unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"Summary error: {e}")

    st.markdown("<br>", unsafe_allow_html=True)

    open_trades = get_open_trades()
    if open_trades:
        st.markdown('<div class="section-label">Close a Trade</div>', unsafe_allow_html=True)
        c1,c2,c3,c4 = st.columns([2,1,1,1])
        with c1:
            opts     = {f"#{t['id']} {t['symbol']} {t['signal']} @ ₹{t['entry']}": t['id'] for t in open_trades}
            sel_lbl  = st.selectbox("Trade", list(opts.keys()), label_visibility="collapsed")
        with c2:
            exit_p = st.number_input("Exit", min_value=0.0, step=0.05, label_visibility="collapsed")
        with c3:
            cl_notes = st.text_input("Notes", placeholder="reason", label_visibility="collapsed")
        with c4:
            if st.button("✅ Close", use_container_width=True):
                ok, msg = close_trade(opts[sel_lbl], exit_p, cl_notes)
                st.success(msg) if ok else st.error(msg)
                st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)

    st.markdown('<div class="section-label">All Trades</div>', unsafe_allow_html=True)
    trades = get_all_trades()
    if not trades:
        st.markdown('<div class="card" style="text-align:center;color:#475569;padding:2rem">No trades yet. Run analysis and log a trade.</div>', unsafe_allow_html=True)
        return

    rows_html = ""
    for t in trades:
        pnl      = t.get("pnl")
        pnl_col  = "#22c55e" if pnl and pnl > 0 else "#ef4444" if pnl and pnl < 0 else "#94a3b8"
        pnl_str  = f'<span style="color:{pnl_col}">₹{pnl}</span>' if pnl is not None else "—"
        out      = outcome_badge(t.get("outcome") if t.get("status") == "CLOSED" else None)
        rows_html += f"""<tr>
            <td style="color:#64748b">#{t['id']}</td>
            <td><span class="date-pill">{t.get('analysis_date','—')}</span><br>
                <span class="trade-date-pill" style="margin-top:3px;display:inline-block">{t.get('trade_date','—')}</span></td>
            <td class="symbol-cell">{t['symbol']}</td>
            <td>{signal_badge(t.get('signal',''))}</td>
            <td style="color:#94a3b8">{t.get('confidence','—')}%</td>
            <td>{'₹'+str(t['entry']) if t.get('entry') else '—'}</td>
            <td style="color:#22c55e">{'₹'+str(t['target']) if t.get('target') else '—'}</td>
            <td style="color:#ef4444">{'₹'+str(t['stop_loss']) if t.get('stop_loss') else '—'}</td>
            <td>{'₹'+str(t['exit_price']) if t.get('exit_price') else '—'}</td>
            <td>{pnl_str}</td><td>{out}</td>
            <td style="color:#64748b;font-size:0.7rem">{t.get('notes','') or '—'}</td>
        </tr>"""

    st.markdown(f"""<table class="results-table"><thead><tr>
        <th>#</th><th>Dates</th><th>Stock</th><th>Signal</th><th>Conf</th>
        <th>Entry</th><th>Target</th><th>SL</th><th>Exit</th><th>P&L</th><th>Result</th><th>Notes</th>
    </tr></thead><tbody>{rows_html}</tbody></table>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    dc1, dc2 = st.columns([3, 1])
    with dc1:
        del_opts  = {f"#{t['id']} {t['symbol']} {t['signal']} {t['analysis_date']}": t['id'] for t in trades}
        del_label = st.selectbox("Delete", list(del_opts.keys()), label_visibility="collapsed")
    with dc2:
        if st.button("🗑️ Delete", use_container_width=True):
            delete_trade(del_opts[del_label])
            st.success("Deleted")
            st.rerun()


# ── Morning Brief tab ──────────────────────────────────────

def render_morning_brief_tab():
    st.markdown('<div class="section-label">Morning Brief</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="card">
        <div style="font-size:0.85rem;color:#94a3b8;line-height:1.7">
        One click runs the full analysis pipeline and generates a clean daily report.<br>
        Report is automatically saved to <span style="color:#38bdf8">logs/</span> folder.
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([2, 1])
    with col1:
        run_brief_btn = st.button("📋 GENERATE MORNING BRIEF", use_container_width=True)
    with col2:
        # Show saved briefs
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            saved = sorted([
                f for f in os.listdir(LOG_DIR)
                if f.startswith("morning_brief_") and f.endswith(".txt")
            ], reverse=True)
            if saved:
                load_file = st.selectbox("Load saved brief", ["— Select —"] + saved, label_visibility="collapsed")
                if load_file and load_file != "— Select —":
                    with open(os.path.join(LOG_DIR, load_file), "r") as f:
                        st.session_state.morning_brief_text = f.read()
                        st.session_state.morning_brief_path = load_file
        except Exception:
            pass

    # Log area for brief generation
    brief_log_ph = st.empty()

    if run_brief_btn:
        st.session_state.log_lines         = []
        st.session_state.morning_brief_text = None

        date_info = _get_trade_date_info()
        st.session_state.trade_date_info = date_info

        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "line")
        log("  GENERATING MORNING BRIEF", "info")
        log(f"  {date_info['analysis_date']} {date_info['analysis_time']}", "info")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "line")
        render_log(brief_log_ph)

        ind, res = run_pipeline(log_ph=brief_log_ph)

        if res:
            try:
                from stocktrading.trade_journal import get_journal_summary
                summary = get_journal_summary()
                report, path = generate_morning_brief(res, ind, summary)
                st.session_state.morning_brief_text = report
                st.session_state.morning_brief_path = path
                # Also update main analysis state
                st.session_state.results        = res
                st.session_state.indicators_map = ind
                log(f"✅ Brief saved to {path}", "success")
                render_log(brief_log_ph)
            except Exception as e:
                log(f"❌ Brief generation error: {e}", "error")
                render_log(brief_log_ph)

    # Display brief
    if st.session_state.morning_brief_text:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-label">Report</div>', unsafe_allow_html=True)
        if st.session_state.morning_brief_path:
            st.caption(f"📁 {st.session_state.morning_brief_path}")
        st.markdown(
            f'<div class="brief-box">{st.session_state.morning_brief_text}</div>',
            unsafe_allow_html=True
        )
    elif not run_brief_btn:
        brief_log_ph.markdown(
            '<div class="log-box"><span class="log-line">Click GENERATE MORNING BRIEF to run analysis and create report...</span></div>',
            unsafe_allow_html=True
        )


# ── MAIN ───────────────────────────────────────────────────

def main():
    if not IMPORTS_OK:
        st.error(f"❌ Import error: {IMPORT_ERROR}")
        return

    init_watchlist_db()
    init_trade_journal()

    st.markdown(f"""
    <div class="dash-header">
        <div class="dash-title"><span class="live-dot"></span>StockTradingAlgo</div>
        <div class="dash-subtitle">NSE EQUITY RESEARCH &nbsp; / &nbsp; EVIDENCE BEFORE ACTION &nbsp; / &nbsp; {datetime.now().strftime('%A, %d %b %Y')}</div>
    </div>
    """, unsafe_allow_html=True)
    try:
        model = get_settings()
        st.caption(f"Model: {model.provider} / {model.model} | {DEFAULT_TIMEFRAME} completed bars | Research only, no automatic orders")
    except ValueError as exc:
        st.error(f"Model configuration needs attention: {exc}. See System Info > Model setup.")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊  ANALYSIS", "🌐  NEWS PICKS", "📓  JOURNAL", "📋  MORNING BRIEF", "🔧  SYSTEM INFO"])


    # ── TAB 1: ANALYSIS ──────────────────────────────────
    with tab1:
        main_col, panel_col = st.columns([3, 1.2], gap="large")

        with main_col:
            # Watchlist manager
            st.markdown('<div class="section-label">Watchlist Manager</div>', unsafe_allow_html=True)
            current_wl = get_watchlist_from_db()

            wc1,wc2,wc3,wc4 = st.columns([2,1,2,1])
            with wc1:
                new_stock = st.text_input("Add any NSE stock", placeholder="e.g. TATAMOTORS, SUNPHARMA...", label_visibility="collapsed")
            with wc2:
                if st.button("＋ Add", use_container_width=True):
                    if new_stock.strip():
                        with st.spinner(f"Looking up {new_stock.upper()}..."):
                            ok, msg = add_stock_to_watchlist(new_stock.strip())
                        st.success(msg) if ok else st.error(msg)
                        if ok: st.rerun()
            with wc3:
                remove_sym = st.selectbox("Remove", ["— Remove —"] + current_wl, label_visibility="collapsed")
            with wc4:
                if st.button("✕ Remove", use_container_width=True):
                    if remove_sym != "— Remove —":
                        ok, msg = remove_stock_from_watchlist(remove_sym)
                        st.success(msg) if ok else st.error(msg)
                        if ok: st.rerun()

            tags = " ".join([f'<span class="wl-tag">{s}</span>' for s in get_watchlist_from_db()])
            st.markdown(f'<div style="margin:8px 0 12px 0">{tags}</div>', unsafe_allow_html=True)
            st.markdown("---")

            # On-demand search
            st.markdown('<div class="section-label">🔍 On-Demand Analysis (Any Stock)</div>', unsafe_allow_html=True)
            st.caption("Type any NSE symbol — even if not in watchlist. System looks up the instrument key automatically.")
            sc1,sc2 = st.columns([3,1])
            with sc1:
                search_input = st.text_input("Search", placeholder="e.g. TATAMOTORS, SUNPHARMA, ADANIENT...", label_visibility="collapsed")
            with sc2:
                search_btn = st.button("🔍 Analyse", use_container_width=True)
            st.markdown("---")

            # Run analysis button
            st.markdown('<div class="section-label">Full Watchlist Analysis</div>', unsafe_allow_html=True)
            run_btn = st.button("▶  RUN FULL ANALYSIS", use_container_width=True)

            st.markdown('<div class="section-label" style="margin-top:1rem">Live Progress</div>', unsafe_allow_html=True)
            log_ph = st.empty()

            if st.session_state.log_lines:
                render_log(log_ph)
            else:
                log_ph.markdown('<div class="log-box"><span class="log-line">Ready. Click ▶ RUN FULL ANALYSIS to start...</span></div>', unsafe_allow_html=True)

            if run_btn:
                run_full_analysis(log_ph)
                st.rerun()

            if search_btn and search_input.strip():
                sym = search_input.strip().upper()
                run_single_analysis(sym, log_ph)
                if st.session_state.search_result:
                    st.session_state.selected_stock = f"🔍 {sym}"

            # Results
            if st.session_state.results:
                st.markdown("---")
                st.markdown('<div class="section-label">Results</div>', unsafe_allow_html=True)

                date_info = st.session_state.trade_date_info or _get_trade_date_info()
                st.markdown(
                    f'<div class="card" style="padding:0.6rem 1rem;margin-bottom:0.8rem">'
                    f'<span class="date-pill">📅 {date_info["analysis_date"]} {date_info["analysis_time"]}</span>'
                    f'&nbsp;&nbsp;<span class="trade-date-pill">🚀 {date_info["trade_day"]}</span></div>',
                    unsafe_allow_html=True
                )

                total = len(st.session_state.results)
                buys  = sum(1 for r in st.session_state.results.values() if "BUY"  in str(r.get("signal","")))
                sells = sum(1 for r in st.session_state.results.values() if "SELL" in str(r.get("signal","")))
                waits = total - buys - sells
                ruled = sum(1 for r in st.session_state.results.values() if r.get("rule_violations"))

                for col, (label, val, color) in zip(st.columns(5), [
                    ("Analysed",total,""),("Buy",buys,"green"),
                    ("Sell",sells,"red"),("Wait",waits,"yellow"),("Rules ⚠️",ruled,"red" if ruled else ""),
                ]):
                    with col:
                        st.markdown(f'<div class="metric-tile"><div class="metric-label">{label}</div><div class="metric-value {color}">{val}</div></div>', unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)

                rows_html = ""
                for symbol, result in st.session_state.results.items():
                    signal = result.get("signal","WAIT")
                    conf   = result.get("confidence") or 0
                    entry  = result.get("entry","—")
                    target = result.get("target","—")
                    sl     = result.get("stop_loss","—")
                    rr     = result.get("risk_reward","—")
                    viols  = result.get("rule_violations",[])
                    badge  = signal_badge(signal)
                    cc     = conf_color(conf)
                    news_sent = result.get("news_sentiment","—")
                    nbadge    = news_sentiment_badge(news_sent)
                    vstr   = f'<br><span style="color:#f59e0b;font-size:0.65rem">⚠️ {len(viols)} rule(s)</span>' if viols else ""
                    rows_html += f"""<tr>
                        <td class="symbol-cell">{symbol}</td>
                        <td>{badge}{vstr}</td>
                        <td>{nbadge}</td>
                        <td><span style="color:{cc};font-weight:700">{conf}%</span>
                            <div style="height:3px;background:{cc};width:{conf}%;border-radius:2px;margin-top:3px"></div></td>
                        <td>{'₹'+str(entry) if entry and entry!='—' else '—'}</td>
                        <td style="color:#22c55e">{'₹'+str(target) if target and target!='—' else '—'}</td>
                        <td style="color:#ef4444">{'₹'+str(sl) if sl and sl!='—' else '—'}</td>
                        <td style="color:#94a3b8">{rr}</td>
                    </tr>"""

                st.markdown(f"""<table class="results-table"><thead><tr>
                    <th>Stock</th><th>Signal</th><th>News</th><th>Confidence</th>
                    <th>Entry</th><th>Target</th><th>SL</th><th>R:R</th>
                </tr></thead><tbody>{rows_html}</tbody></table>""", unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)
                st.markdown('<div class="section-label">Select for Detail →</div>', unsafe_allow_html=True)
                opts = list(st.session_state.results.keys())
                sel  = st.selectbox("Stock", ["— Select —"] + opts, label_visibility="collapsed")
                if sel and sel != "— Select —":
                    st.session_state.selected_stock = sel

        # Side panel
        with panel_col:
            st.markdown('<div class="section-label">Detail View</div>', unsafe_allow_html=True)
            sel = st.session_state.selected_stock

            if sel and str(sel).startswith("🔍"):
                sym = sel.replace("🔍 ","")
                if st.session_state.search_result and st.session_state.search_ind:
                    render_side_panel(sym, st.session_state.search_result, st.session_state.search_ind)
            elif sel and sel in st.session_state.results:
                render_side_panel(sel, st.session_state.results[sel], st.session_state.indicators_map.get(sel,{}))
            else:
                st.markdown('<div class="card" style="text-align:center;padding:2rem 1rem;color:#475569"><div style="font-size:2rem;margin-bottom:0.5rem">📊</div><div style="font-size:0.8rem;font-family:\'JetBrains Mono\',monospace">Run analysis then<br>select a stock</div></div>', unsafe_allow_html=True)

    # ── TAB 2: NEWS PICKS ─────────────────────────────────
    with tab2:
        render_recommendations_tab()

    # ── TAB 3: JOURNAL ────────────────────────────────────
    with tab3:
        render_journal_tab()

    # ── TAB 4: MORNING BRIEF ──────────────────────────────
    with tab4:
        render_morning_brief_tab()
        
    with tab5:
        render_system_info_tab()


if __name__ == "__main__":
    main()