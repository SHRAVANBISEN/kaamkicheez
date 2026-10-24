"""Live methodology, parameter, source, context and audit documentation."""

import json

import pandas as pd
import streamlit as st

from stocktrading.analysis_evidence import render_evidence_panel
from stocktrading.config import (
    DEFAULT_TIMEFRAME, RSI_PERIOD, EMA_SHORT, EMA_LONG, MACD_FAST, MACD_SLOW,
    MACD_SIGNAL, BB_PERIOD, BB_STD, ATR_PERIOD, ADX_PERIOD,
    RESOURCE_DIR, DOCS_DIR,
)
from stocktrading.fundamentals import render_fundamentals_panel
from stocktrading.institutions import render_institutions_panel
from stocktrading.llm_provider import provider_status, list_models
from stocktrading.intraday_engine import calculate_features, load_rules


def render_decision_trace(result):
    trace = result.get("decision_trace")
    if not trace:
        st.caption("No decision trace recorded for this older result.")
        return
    with st.expander("Why this conclusion? Inputs, model proposal and rule overrides"):
        st.write("Technical setup:", trace["technical_setup"])
        proposal = trace.get("model_proposal") or {}
        st.write("Model proposed:", proposal.get("signal", "Unavailable"), "| Final:", trace["final_signal"])
        if trace["rule_overrides"]:
            st.write("Rules that overrode the proposal:", trace["rule_overrides"])
        if trace["technical_reasons"]:
            st.write("Technical conditions:", trace["technical_reasons"])
        st.caption(trace["interpretation"])
        st.write("Evidence IDs cited by the model:", trace["model_cited_ids"] or "Not supplied")
        st.dataframe([
            {"ID": row["id"], "Part": row["part"], "Observation": row["observation"],
             "Value": json.dumps(row["value"], ensure_ascii=True), "Source": row["source"],
             "As of": row["as_of"], "Role": row["role"]}
            for row in trace["input_evidence"]
        ], hide_index=True)
        st.json(trace)


def render_indicator_snapshot(indicators):
    context = indicators.get("intraday", {})
    st.caption("Completed-bar technical evidence (research setup, not an executable order)")
    st.table([
        {"Feature": label, "Value": str(context.get(key)) if context.get(key) is not None else "Unavailable"}
        for label, key in (
            ("Bar end (IST)", "completed_bar_end"), ("Regime", "regime"),
            ("Session VWAP approximation", "vwap"), ("ATR", "atr"), ("ADX", "adx"),
            ("Same-slot relative volume", "relative_volume"), ("RVOL prior sessions", "rvol_samples"),
            ("Opening range high", "opening_range_high"), ("Opening range low", "opening_range_low"),
            ("Technical setup", "setup"),
        )
    ])
    for reason in dict.fromkeys(context.get("blockers", []) + context.get("setup_reasons", [])):
        st.warning(reason)
    for warning in context.get("warnings", []):
        st.caption(warning)
    with st.expander("Full technical, financial and institutional evidence"):
        st.json({key: indicators.get(key) for key in ("intraday", "fundamentals", "institutions")})


def render_system_info_tab():
    st.subheader("How this intraday research system works")
    st.warning("No guaranteed price prediction. BUY/SELL are research candidates, not orders. "
               "The exact strategy has not been backtested or shown profitable after costs.")
    try:
        rules = load_rules()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(f"Invalid strategy configuration: {exc}")
        return
    settings = rules["intraday"]
    technical, indicators, fundamentals, institutions, research, news, risk, model_setup, history = st.tabs([
        "Technical process", "Indicators & settings", "Fundamentals",
        "Institutions", "Research papers", "News & market coverage", "Decision rules", "Model setup", "Evidence & setup",
    ])
    with technical:
        st.markdown("""
1. **Validate data first:** Upstox v3 history plus today's intraday candles; default 5-minute bars. Reject invalid OHLC, duplicates, unsupported sessions and timestamps. Exclude unfinished bars.
2. **Check readiness:** minimum warm-up, continuous session from 09:15 IST, fresh candles and permitted entry hours. Old data remains useful for inspection but cannot justify a live entry.
3. **Describe structure:** the first 15 minutes form the opening range. Session VWAP uses typical price `(high + low + close)/3` weighted by volume. Previous complete observed-session levels are descriptive context.
4. **Identify a trend:** EMA alignment provides direction; ADX provides strength, not direction. Weak/ranging conditions mean WAIT for this trend-breakout strategy; there is no implemented mean-reversion strategy.
5. **Require participation and avoid chasing:** same-slot relative volume, RSI direction and distance from VWAP in ATR units must meet the displayed thresholds.
6. **Form a candidate:** BUY only above the opening-range high and VWAP with bullish EMA/RSI; SELL uses the inverse. All conditions must align. A breakout state is not a fresh crossover event or a new order.
7. **Check event risk, then ask the LLM to explain:** missing/stale event review blocks entries by default. The LLM cannot promote an unsupported setup. Validate price ordering and compute R:R from prices, not from the model's claimed ratio.
""")
        st.info("Indicators carry historical state across sessions; only VWAP and the opening range reset daily. "
                "This is single-timeframe screening, not multi-timeframe, sector-relative or order-book analysis.")
        maps = dict(st.session_state.get("indicators_map", {}))
        for key in ("search_ind", "offline_indicators"):
            value = st.session_state.get(key)
            if value:
                maps[f"{value['symbol']} ({key})"] = value
        if maps:
            selected = st.selectbox("Inspect calculated evidence", list(maps), key="methodology_stock")
            render_indicator_snapshot(maps[selected])
        else:
            st.info("Run analysis or upload candles below to populate calculated evidence.")
        with st.expander("Offline candle inspection - no broker or LLM API"):
            st.caption("CSV columns: timestamp (with timezone), symbol, open, high, low, close, volume. "
                       "Supply at least 100 bars and 5 prior same-slot sessions for full readiness. "
                       "Use actual data, not confidential company data. No trades are generated here.")
            upload = st.file_uploader("OHLCV CSV", type=["csv"], key="offline_csv")
            minutes = st.selectbox("CSV candle interval (minutes)", [5, 1, 15], key="offline_minutes")
            if st.button("Calculate offline evidence", disabled=upload is None):
                try:
                    frame = pd.read_csv(upload)
                    frame.attrs.update(timeframe_minutes=minutes, source="User-provided CSV (unverified)")
                    st.session_state.offline_indicators = calculate_features(frame)
                    st.rerun()
                except (ValueError, TypeError, OSError, KeyError) as exc:
                    st.error(f"CSV could not be analysed: {exc}")
    with indicators:
        st.caption(f"Active interval: {DEFAULT_TIMEFRAME}. These are starting conventions, not optimal settings.")
        st.table([
            {"Indicator": "VWAP", "Configuration": "09:15 IST session reset, typical-price x volume", "Role": "Price location; OHLCV approximation, not trade-level VWAP"},
            {"Indicator": "EMA", "Configuration": f"{EMA_SHORT}/{EMA_LONG}, close, SMA-seeded recursive EMA", "Role": "Trend direction; not independent of MACD"},
            {"Indicator": "RSI", "Configuration": f"{RSI_PERIOD}, Wilder smoothing; flat=50", "Role": f"BUY 50..{rules['filters']['avoid_rsi_above']}; SELL {rules['filters']['avoid_rsi_below']}..50; not automatic oversold buys"},
            {"Indicator": "ATR", "Configuration": f"{ATR_PERIOD}, Wilder-smoothed true range", "Role": f"Volatility; maximum VWAP distance {settings['max_vwap_distance_atr']} ATR"},
            {"Indicator": "ADX", "Configuration": f"DI {ADX_PERIOD}, ADX smoothing {ADX_PERIOD}, Wilder", "Role": f"Trend strength >= {settings['min_adx']}; no direction"},
            {"Indicator": "Relative volume", "Configuration": f"Same completed time slot, prior {settings['rvol_sessions']} observed sessions", "Role": f"Require >= {settings['min_relative_volume']}x; missing/zero baseline is unknown"},
            {"Indicator": "Opening range", "Configuration": f"First {settings['opening_range_minutes']} minutes of regular session", "Role": "Completed range breakout reference"},
            {"Indicator": "MACD", "Configuration": f"{MACD_FAST}/{MACD_SLOW}/{MACD_SIGNAL}", "Role": "Context only by default; optional confirmation in rules"},
            {"Indicator": "Bollinger Bands", "Configuration": f"{BB_PERIOD}, {BB_STD} population standard deviations", "Role": "Volatility context, not an extra vote or automatic reversal"},
        ])
        st.write("Warm-up bars:", settings["min_history_bars"])
        st.caption("Change indicator lengths in stocktrading\\config.py and thresholds in resources\\strategy_rules.json; restart after "
                   "changing config.py. Keep EMA9/EMA21 legacy output labels aligned with the configured lengths. "
                   "Record and validate every experiment; do not keep tuning until historical results look good.")
        st.markdown("""
**Calculation references (documentation, not profitability research):**
[VWAP](https://www.sierrachart.com/index.php?page=doc/StudiesReference.php&ID=108&Name=Volume_Weighted_Average_Price_-_VWAP_-_with_Standard_Deviation_Lines),
[ATR](https://www.tradingview.com/support/solutions/43000501823-average-true-range-atr/),
[RSI](https://www.tradingview.com/support/solutions/43000502338-relative-strength-index-rsi/),
[DMI/ADX](https://www.tradingview.com/support/solutions/43000502250-directional-movement-dmi/),
[Relative volume at time](https://www.tradingview.com/support/solutions/43000635874-how-do-we-calculate-relative-volume-and-relative-volume-at-time/).
""")
    with fundamentals:
        st.markdown("**Best fit for this intraday system: event-driven, point-in-time fundamental context.** "
                    "Start with what new information became public, what was expected beforehand and whether "
                    "the accounting inputs are comparable. Use financial quality as context, not a minute-by-minute "
                    "valuation model. There is no universally best fundamental strategy.")
        st.table([
            {"Layer": "Catalyst / expectations", "What is considered": "Actual vs pre-release consensus EPS, announcement time, same period/currency/EPS basis", "Effect": "Descriptive surprise + event risk; never an automatic buy"},
            {"Layer": "Earnings quality", "What is considered": "Aligned profit and operating cash flow, cash-based accrual proxy, free cash flow", "Effect": "Explains profit/cash mismatch; no claim to reproduce an accruals strategy"},
            {"Layer": "Balance sheet / liquidity", "What is considered": "Average-asset ROA, debt/equity, current ratio, interest coverage when applicable", "Effect": "Company context; no universal pass/fail thresholds"},
            {"Layer": "Sector suitability", "What is considered": "Non-financial vs bank/NBFC/insurance; reported asset-quality and capital ratios", "Effect": "Inapplicable ratios suppressed; missing ratios remain unknown"},
            {"Layer": "Information quality", "What is considered": "Publication and receipt timestamps, reporting windows, units, basis, source URL", "Effect": "No future-known snapshots; unmatched periods do not produce advanced cash metrics"},
        ])
        st.caption("Long-horizon DCF, P/E ranking, Piotroski F-score and post-earnings drift strategies are not "
                   "implemented as intraday signals. The research section explains why these ideas cannot "
                   "be transferred into an intraday prediction without separate evidence.")
        render_fundamentals_panel(list(st.session_state.get("indicators_map", {})), settings=settings)
    with institutions:
        st.markdown("**Process:** collect public disclosures -> preserve their scope and publication time -> "
                    "separate market-wide flows, stock ownership and named deals -> calculate descriptive changes -> "
                    "show freshness and missing coverage. These are context for the model, not additional BUY/SELL votes.")
        st.info("An institution can affect price through its orders, but these disclosures cannot reveal all live "
                "orders, hidden inventory or intent. RVOL/VWAP describe participation, not who traded.")
        st.table([
            {"Evidence": "FII/FPI and DII cash flows", "Calculation": "Gross purchases minus gross sales, in INR crore", "Limit": "Market scope and date stay explicit; not stock-specific or live flows"},
            {"Evidence": "Disclosed ownership", "Calculation": "Current percentage minus previous percentage (percentage points)", "Limit": "Not net purchasing; share count/corporate actions may change"},
            {"Evidence": "Bulk / block disclosures", "Calculation": "Disclosed quantity x price; named side and source", "Limit": "Each trade has a counterparty; large does not automatically mean institutional"},
            {"Evidence": "OHLCV participation", "Calculation": "Existing same-slot relative volume and VWAP location", "Limit": "A proxy for participation, not institution identification or proof of control"},
        ])
        render_institutions_panel(list(st.session_state.get("indicators_map", {})),
                                  settings=rules.get("institutions", {}))
    with research:
        st.info("These papers informed engineering choices. None validates this exact NSE strategy. "
                "We have not reproduced their experiments; verification scope is stated for every source.")
        papers = json.loads((RESOURCE_DIR / "research_catalog.json").read_text(encoding="utf-8"))
        areas = sorted({paper.get("category", "Earlier technical/news methodology") for paper in papers})
        area = st.selectbox("Filter research and official references", ["All sources"] + areas, key="research_area")
        for paper in papers:
            if area != "All sources" and paper.get("category", "Earlier technical/news methodology") != area:
                continue
            with st.expander(f"{paper['authors_year']} - {paper['title']}"):
                st.caption(f"Evidence reference ID: {paper['id']}")
                st.markdown(f"[Primary source]({paper['url']})")
                for label, key in (("What we learned", "learned"), ("What we coded", "implemented"),
                                   ("Not implemented", "not_implemented"), ("Limitations", "limitations"),
                                   ("What was actually read", "verification")):
                    st.write(f"**{label}:** {paper[key]}")
    with news:
        from stocktrading.news_fetcher import GLOBAL_MARKET_FEEDS, STOCK_NEWS_TEMPLATES

        st.write("Existing configured RSS sources (availability is not verified by opening this screen):")
        st.json(GLOBAL_MARKET_FEEDS)
        st.json(STOCK_NEWS_TEMPLATES)
        st.warning("RSS can be delayed, unavailable or incomplete. Empty headlines are not neutral evidence. "
                   "The current adapter still lacks structured source/publication/first-seen provenance per headline.")
        st.table([
            {"Part": "Technical + indicators", "Status": "Implemented: completed-bar, single-timeframe setup"},
            {"Part": "Fundamentals/events", "Status": "Implemented: manual timestamped snapshots and event gates"},
            {"Part": "Research", "Status": "Source catalogue + engineering implications; no empirical replication"},
            {"Part": "News", "Status": "Existing RSS + LLM interpretation; not a comprehensive live feed"},
            {"Part": "Institutions", "Status": "Manual sourced flow/ownership/deal imports; delayed context, not live tracking"},
            {"Part": "Market sentiment", "Status": "News + manual flows; breadth, sector/index strength, VIX, FX/yields and automated flows not connected"},
        ])
    with risk:
        st.json(rules)
        st.markdown("**Enforced:** data/setup alignment, current entry window and freshness, optional MACD confirmation, "
                    "RSI/confidence limits, manual event-review freshness and known high-impact event blackout, "
                    "finite positive prices, long/short ordering and gross price-derived R:R. WAIT has no price levels.")
        st.warning("Not implemented: position sizing, account exposure, daily loss/trade-count enforcement, "
                   "fees/slippage-adjusted R:R, spread/liquidity checks, live order execution, automatic exits, "
                   "exchange holiday/special-session calendar, multi-timeframe confirmation and backtesting.")
        st.write("The chosen LLM explains supplied evidence; deterministic rules can override it. "
                 "Model confidence is not a calibrated probability. Financial and institutional evidence remains "
                 "context, except explicit event-risk gates. No paper-derived price forecast is assumed.")
        results = dict(st.session_state.get("results", {}))
        single = st.session_state.get("search_result")
        if single:
            results[f"{single.get('symbol', 'Search')} (search)"] = single
        if results:
            symbol = st.selectbox("Inspect a decision trace", list(results), key="decision_trace_symbol")
            render_decision_trace(results[symbol])
    with model_setup:
        st.subheader("Choose the model without changing analysis code")
        try:
            status = provider_status()
            st.json(status)
            if status["provider"] != "gemini" and st.button("List models available to this endpoint"):
                models = list_models()
                st.session_state.available_llm_models = (status["endpoint"], models)
            cached = st.session_state.get("available_llm_models")
            if cached and cached[0] == status["endpoint"]:
                models = cached[1]
                st.write("Configured model listed:", status["model"] in models)
                st.dataframe({"Model ID": models}, hide_index=True)
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))
        st.warning("Nano 9B v2 remains documented, but was absent from NVIDIA's public hosted list checked on "
                   "2026-10-25. Confirm your account's model ID or use a compatible local deployment. "
                   "No provider is silently substituted and hosted inference is not guaranteed free.")
        st.markdown((DOCS_DIR / "MODEL_SETUP.md").read_text(encoding="utf-8"))
    with history:
        render_evidence_panel()
