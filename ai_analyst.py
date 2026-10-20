# ai_analyst.py — AI analysis with news + technical indicators
# Gemini gets: indicators + stock news + macro news
# New: recommend_stocks_from_news() for news-based picks

import json
import time
from google import genai
from config import GEMINI_API_KEY, STRATEGY_FILE

# <<< SWAP >>> Line 1 of 3 — configure client
client = genai.Client(api_key=GEMINI_API_KEY)


# ── Strategy rules ─────────────────────────────────────────

def load_strategy_rules():
    try:
        with open(STRATEGY_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Strategy rules not loaded: {e}")
        return {}


def _format_rules_for_prompt(rules):
    if not rules:
        return "No strategy rules defined."
    filters = rules.get("filters", {})
    prefs   = rules.get("preferences", {})
    risk    = rules.get("risk_management", {})
    return f"""
STRATEGY RULES (override signal to WAIT if violated):
- Min R:R ratio       : {filters.get('min_risk_reward', 1.5)}
- Min confidence      : {filters.get('min_confidence', 60)}%
- Avoid RSI above     : {filters.get('avoid_rsi_above', 75)} for BUY
- Avoid RSI below     : {filters.get('avoid_rsi_below', 20)} for SELL
- Require MACD conf   : {prefs.get('require_macd_confirmation', True)}
- Max loss/trade      : {risk.get('max_loss_per_trade_pct', 1.0)}%
"""


# ── Rule filter ────────────────────────────────────────────

def _apply_rule_filters(result, indicators, rules):
    violations    = []
    filters       = rules.get("filters", {})
    signal        = result.get("signal", "WAIT")
    rsi           = indicators.get("rsi", 50) or 50
    macd_momentum = indicators.get("macd_momentum", "")
    confidence    = result.get("confidence") or 0
    rr_str        = result.get("risk_reward") or ""

    if signal in ["BUY","STRONG_BUY"] and rsi > filters.get("avoid_rsi_above", 75):
        violations.append(f"RSI {rsi} too high for BUY (limit: {filters.get('avoid_rsi_above',75)})")
    if signal in ["SELL","STRONG_SELL"] and rsi < filters.get("avoid_rsi_below", 20):
        violations.append(f"RSI {rsi} too low for SELL (limit: {filters.get('avoid_rsi_below',20)})")
    if signal not in ["WAIT"] and confidence < filters.get("min_confidence", 60):
        violations.append(f"Confidence {confidence}% below minimum {filters.get('min_confidence',60)}%")
    if rules.get("preferences",{}).get("require_macd_confirmation", False):
        if signal in ["BUY","STRONG_BUY"] and macd_momentum != "BULLISH":
            violations.append("MACD not bullish — required for BUY")
        if signal in ["SELL","STRONG_SELL"] and macd_momentum != "BEARISH":
            violations.append("MACD not bearish — required for SELL")
    if rr_str and ":" in str(rr_str):
        try:
            parts = str(rr_str).split(":")
            if float(parts[1])/float(parts[0]) < filters.get("min_risk_reward",1.5):
                violations.append(f"R:R {rr_str} below minimum {filters.get('min_risk_reward',1.5)}")
        except Exception:
            pass

    if violations:
        result["signal"]          = "WAIT"
        result["entry"]           = None
        result["target"]          = None
        result["stop_loss"]       = None
        result["risk_reward"]     = None
        result["reasoning"]       = f"⚠️ Overridden to WAIT — {' | '.join(violations)}. Original: {result.get('reasoning','')}"
        result["rule_violations"] = violations
    else:
        result["rule_violations"] = []
    return result


# ── Prompt builders ────────────────────────────────────────

def _build_batch_prompt(all_indicators, rules, batch_news=None):
    """Build batch prompt for all stocks including news."""
    rules_section  = _format_rules_for_prompt(rules)
    stocks_section = ""

    for symbol, ind in all_indicators.items():
        news_data = batch_news.get(symbol, {}) if batch_news else {}
        stock_headlines = news_data.get("stock_news", [])
        macro_headlines = news_data.get("macro_news", [])

        news_section = ""
        if stock_headlines:
            news_section += f"\n  Recent News ({symbol}):\n"
            for h in stock_headlines[:4]:
                news_section += f"    • {h}\n"
        if macro_headlines:
            news_section += f"\n  Macro/Global News:\n"
            for h in macro_headlines[:3]:
                news_section += f"    • {h}\n"

        stocks_section += f"""
--- {symbol} ---
Close:{ind['close']} Open:{ind['open']} High:{ind['high']} Low:{ind['low']} Vol:{ind['volume']}
RSI:{ind['rsi']} ({ind['rsi_zone']}) | EMA:{ind['ema_trend']} EMA9:{ind['ema9']} EMA21:{ind['ema21']} Cross:{ind['ema_crossover']}
MACD:{ind['macd']} Sig:{ind['macd_signal']} Hist:{ind['macd_hist']} Mom:{ind['macd_momentum']} Cross:{ind['macd_crossover']}
BB Upper:{ind['bb_upper']} Mid:{ind['bb_mid']} Lower:{ind['bb_lower']} Pos:{ind['bb_position']} W:{ind['bb_width']}
Pre-Signal:{ind['preliminary_signal']}{news_section}"""

    symbols_list = ", ".join(all_indicators.keys())

    return f"""You are an expert Indian NSE trader. Analyse ALL stocks below using BOTH technical indicators AND news sentiment.

{rules_section}

STOCKS:
{stocks_section}

INSTRUCTIONS:
1. Analyse technicals + news together for each stock.
2. If news is bullish but technicals are bearish (or vice versa) — note the conflict and lean toward WAIT.
3. If both technicals and news align → higher confidence signal.
4. Apply strategy rules — override to WAIT if violated.
5. entry/target/stop_loss/risk_reward = null for WAIT.
6. news_sentiment field: "BULLISH", "BEARISH", or "NEUTRAL".
7. Reasoning must mention both technical and news factors.

CRITICAL: Valid JSON only. No markdown, no backticks.

{{
  "SYMBOL1": {{
    "symbol": "SYMBOL1",
    "signal": "BUY"/"SELL"/"WAIT",
    "confidence": <0-100>,
    "entry": <price or null>,
    "target": <price or null>,
    "stop_loss": <price or null>,
    "risk_reward": <"1:2.5" or null>,
    "news_sentiment": "BULLISH"/"BEARISH"/"NEUTRAL",
    "reasoning": "<2-3 sentences covering technicals AND news>",
    "indicators_summary": "<one line>"
  }}
}}

Analyse: {symbols_list}"""


def _build_single_prompt(ind, rules, news_data=None):
    """Single stock prompt with news."""
    rules_section = _format_rules_for_prompt(rules)
    news_section  = ""

    if news_data:
        stock_headlines = news_data.get("stock_news", [])
        macro_headlines = news_data.get("macro_news", [])
        if stock_headlines:
            news_section += f"\nRECENT NEWS — {ind['symbol']} (last 72h):\n"
            for h in stock_headlines[:5]:
                news_section += f"  • {h}\n"
        if macro_headlines:
            news_section += "\nMACRO/GLOBAL NEWS (last 48h):\n"
            for h in macro_headlines[:4]:
                news_section += f"  • {h}\n"

    return f"""You are an expert Indian NSE trader. Analyse {ind['symbol']} using BOTH technicals AND news.

MARKET DATA:
Close:{ind['close']} Open:{ind['open']} High:{ind['high']} Low:{ind['low']} Vol:{ind['volume']}

TECHNICALS:
RSI:{ind['rsi']} ({ind['rsi_zone']}) | EMA:{ind['ema_trend']} EMA9:{ind['ema9']} EMA21:{ind['ema21']} Cross:{ind['ema_crossover']}
MACD:{ind['macd']} Sig:{ind['macd_signal']} Hist:{ind['macd_hist']} Mom:{ind['macd_momentum']} Cross:{ind['macd_crossover']}
BB Upper:{ind['bb_upper']} Mid:{ind['bb_mid']} Lower:{ind['bb_lower']} Pos:{ind['bb_position']}
Pre-Signal:{ind['preliminary_signal']}
{news_section}
{rules_section}

Give: signal, confidence, entry, target, stop_loss, risk_reward, news_sentiment, reasoning (mention both tech+news), indicators_summary.

CRITICAL: Valid JSON only.
{{
  "symbol":"{ind['symbol']}","signal":"BUY"/"SELL"/"WAIT",
  "confidence":<0-100>,"entry":<price or null>,"target":<price or null>,
  "stop_loss":<price or null>,"risk_reward":<"1:2.5" or null>,
  "news_sentiment":"BULLISH"/"BEARISH"/"NEUTRAL",
  "reasoning":"<2-3 sentences>","indicators_summary":"<one line>"
}}"""


# ── Response parsers ───────────────────────────────────────

def _clean_json(raw_text):
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return cleaned.strip()


def _parse_batch_response(raw_text, all_indicators):
    try:
        result = json.loads(_clean_json(raw_text))
        required = ["symbol","signal","confidence","entry","target",
                    "stop_loss","risk_reward","news_sentiment","reasoning","indicators_summary"]
        results = {}
        for symbol, ind in all_indicators.items():
            if symbol in result:
                r = result[symbol]
                for key in required:
                    if key not in r:
                        r[key] = None
                results[symbol] = r
            else:
                results[symbol] = _fallback_response(ind, "Missing from response")
        return results
    except json.JSONDecodeError as e:
        print(f"⚠️  Batch parse error: {e} | Raw: {raw_text[:300]}")
        return {sym: _fallback_response(ind, "Parse error") for sym, ind in all_indicators.items()}


def _parse_single_response(raw_text, indicators):
    try:
        result   = json.loads(_clean_json(raw_text))
        required = ["symbol","signal","confidence","entry","target",
                    "stop_loss","risk_reward","news_sentiment","reasoning","indicators_summary"]
        for key in required:
            if key not in result:
                result[key] = None
        return result
    except json.JSONDecodeError as e:
        return _fallback_response(indicators, f"Parse error: {e}")


def _fallback_response(indicators, error):
    return {
        "symbol":             indicators.get("symbol","UNKNOWN"),
        "signal":             "WAIT",
        "confidence":         0,
        "entry":              None,
        "target":             None,
        "stop_loss":          None,
        "risk_reward":        None,
        "news_sentiment":     "NEUTRAL",
        "reasoning":          f"Analysis unavailable: {error}",
        "indicators_summary": f"Preliminary: {indicators.get('preliminary_signal','N/A')}",
        "rule_violations":    []
    }


# ── API call with retry ────────────────────────────────────

def _call_gemini(prompt, attempt_label=""):
    for attempt in range(3):
        try:
            # <<< SWAP >>> Lines 2+3 of 3
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            return response.text
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                wait = 65
                print(f"⏳ Rate limit {attempt_label} — waiting {wait}s (attempt {attempt+1}/3)...")
                time.sleep(wait)
            else:
                raise e
    raise Exception("Max retries exceeded")


# ── MAIN: Batch analysis ───────────────────────────────────

def analyze_all_at_once(all_indicators, fetch_news=True):
    """
    ONE Gemini call for ALL stocks.
    Includes news if fetch_news=True.
    """
    if not all_indicators:
        return {}

    rules      = load_strategy_rules()
    batch_news = None

    if fetch_news:
        try:
            from news_fetcher import get_news_for_batch
            print("📰 Fetching news for all stocks...")
            batch_news = get_news_for_batch(list(all_indicators.keys()))
            print(f"   ✅ News fetched for {len(batch_news)} stocks")
        except Exception as e:
            print(f"   ⚠️  News fetch failed: {e} — continuing without news")

    prompt = _build_batch_prompt(all_indicators, rules, batch_news)
    print(f"\n🤖 Sending {len(all_indicators)} stocks to Gemini (1 call, with news)...")

    try:
        raw_text = _call_gemini(prompt, "batch")
        results  = _parse_batch_response(raw_text, all_indicators)

        for symbol in list(results.keys()):
            ind             = all_indicators.get(symbol, {})
            results[symbol] = _apply_rule_filters(results[symbol], ind, rules)
            signal          = results[symbol].get("signal","?")
            conf            = results[symbol].get("confidence") or 0
            news_sent       = results[symbol].get("news_sentiment","—")
            viols           = results[symbol].get("rule_violations",[])
            vstr            = f" ⚠️{len(viols)}" if viols else " ✅"
            print(f"  ✅ {symbol:12} → {signal:5} | {conf}% | News:{news_sent}{vstr}")

        # Attach news to results for dashboard display
        if batch_news:
            for symbol, result in results.items():
                result["news_headlines"] = batch_news.get(symbol,{}).get("stock_news",[])
                result["macro_headlines"] = batch_news.get(symbol,{}).get("macro_news",[])

        return results

    except Exception as e:
        print(f"❌ Gemini batch error: {e}")
        return {sym: _fallback_response(ind, str(e)) for sym, ind in all_indicators.items()}


# ── Single stock analysis ──────────────────────────────────

def analyze(indicators, fetch_news=True):
    """Single stock — for on-demand search."""
    rules     = load_strategy_rules()
    news_data = None

    if fetch_news:
        try:
            from news_fetcher import get_news_for_analysis
            news_data = get_news_for_analysis(indicators.get("symbol",""))
            print(f"   📰 News fetched for {indicators.get('symbol')}")
        except Exception as e:
            print(f"   ⚠️  News fetch failed: {e}")

    prompt = _build_single_prompt(indicators, rules, news_data)

    try:
        raw_text = _call_gemini(prompt, indicators.get("symbol",""))
        result   = _parse_single_response(raw_text, indicators)
        result   = _apply_rule_filters(result, indicators, rules)
        if news_data:
            result["news_headlines"]  = news_data.get("stock_news",[])
            result["macro_headlines"] = news_data.get("macro_news",[])
        return result
    except Exception as e:
        print(f"❌ Gemini error: {e}")
        return _fallback_response(indicators, str(e))


# ── Stock recommendations from news ───────────────────────

def recommend_stocks_from_news(known_symbols=None):
    """
    Analyses global + Indian news and recommends NSE stocks to watch.
    Returns list of recommendations with reasons.
    known_symbols: list of stocks in our instrument key DB (optional filter)
    """
    try:
        from news_fetcher import fetch_news_for_recommendations
        news_text = fetch_news_for_recommendations(max_headlines=25)
    except Exception as e:
        return [], f"News fetch failed: {e}"

    symbols_hint = ""
    if known_symbols:
        symbols_hint = f"""
Known stocks in our system: {', '.join(known_symbols[:30])}
Prefer recommending from this list if relevant, but can suggest others too.
"""

    prompt = f"""You are an expert Indian NSE stock market analyst.

Based on the following global and Indian market news, identify NSE-listed stocks
that are likely to show significant price movement in the NEXT 1-2 trading days.

{news_text}

{symbols_hint}

TASK:
1. Identify 3-8 NSE stocks worth watching based on this news.
2. For each stock explain WHY this news makes it a potential trade.
3. Mention if it's likely bullish or bearish.
4. Be specific — link the news to the stock directly.
5. Only recommend stocks where the news-stock link is clear and strong.
6. Include sector plays too (e.g. "if RBI cuts rates, banking stocks benefit").

CRITICAL: Return ONLY valid JSON, no markdown, no backticks.

{{
  "recommendations": [
    {{
      "symbol": "NSE_SYMBOL",
      "company": "Company Name",
      "direction": "BULLISH" or "BEARISH",
      "confidence": <50-95>,
      "news_driver": "<which specific news headline is driving this>",
      "reasoning": "<2-3 sentences why this stock will move>",
      "sector": "<sector name>",
      "urgency": "TODAY" or "TOMORROW" or "THIS_WEEK"
    }}
  ],
  "market_sentiment": "BULLISH" or "BEARISH" or "MIXED",
  "sentiment_reasoning": "<1-2 sentences on overall market mood>",
  "key_themes": ["theme1", "theme2", "theme3"]
}}"""

    try:
        print("🤖 Asking Gemini to recommend stocks from news...")
        raw_text = _call_gemini(prompt, "recommendations")
        cleaned  = _clean_json(raw_text)
        result   = json.loads(cleaned)

        recs = result.get("recommendations", [])
        print(f"   ✅ {len(recs)} stocks recommended")
        return result, None

    except Exception as e:
        print(f"❌ Recommendation error: {e}")
        return {}, str(e)


# ── Alias ──────────────────────────────────────────────────

def analyze_watchlist(all_indicators):
    return analyze_all_at_once(all_indicators)


def print_analysis(analysis):
    violations = analysis.get("rule_violations", [])
    print(f"""
{'─'*55}
📊 {analysis['symbol']} — {analysis['signal']} | News: {analysis.get('news_sentiment','—')}
{'─'*55}
Confidence : {analysis['confidence']}%
Entry      : {analysis['entry']}
Target     : {analysis['target']}
Stop Loss  : {analysis['stop_loss']}
R:R        : {analysis['risk_reward']}
Summary    : {analysis['indicators_summary']}
Reasoning  : {analysis['reasoning']}
{'⚠️ Rules: ' + str(violations) if violations else '✅ Rules OK'}
{'─'*55}
""")


# ── Claude swap reference ──────────────────────────────────
# REMOVE: from google import genai / client = genai.Client(...)
#         response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
#         raw_text = response.text
# ADD:    import anthropic
#         client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
#         response = client.messages.create(model="claude-opus-4-5", max_tokens=4096,
#                    messages=[{"role":"user","content":prompt}])
#         raw_text = response.content[0].text
# ──────────────────────────────────────────────────────────


if __name__ == "__main__":
    from auth import get_access_token
    from data_fetcher import fetch_watchlist, init_watchlist_db
    from indicators import calculate_all

    init_watchlist_db()
    token = get_access_token()

    if token:
        raw_data       = fetch_watchlist(token)
        all_indicators = calculate_all(raw_data)
        all_analysis   = analyze_all_at_once(all_indicators)

        print("\n" + "="*55)
        for symbol, analysis in all_analysis.items():
            print_analysis(analysis)