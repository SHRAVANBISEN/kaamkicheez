# StockTradingAlgo — AI / Developer Context

Use this file as the source of truth when suggesting or making changes. Read it before editing. Prefer small, local changes in the correct file. Do not invent modules, APIs, or auto-trading that this repo does not have.

---

## 1. What this project is

A **local Python decision-support app for NSE (India) stocks**.

It:

1. Logs into **Upstox** (OAuth) and fetches **historical OHLCV candles**.
2. Computes **technical indicators** locally (`pandas-ta`).
3. Fetches **news via free RSS** (no news API key).
4. Sends indicators + news + strategy rules to **Google Gemini** (`gemini-2.5-flash`).
5. Shows **BUY / SELL / WAIT** with confidence, entry, target, stop-loss, R:R, reasoning.
6. Lets the user **manually journal** ideas in SQLite (open / close / P&L).
7. Can generate a **morning brief** text report under `logs/`.

UI: **Streamlit** (`dashboard.py`). Dark custom CSS. Five tabs: Analysis, News Picks, Journal, Morning Brief, System Info.

Python: **3.13** (venv present). Credentials in `.env` via `python-dotenv`.

---

## 2. What this project is NOT

- **Not a live order bot.** There is no `place_order`, no Upstox order API, no broker execution.
- **Not backtesting.** No historical strategy simulator.
- **Not paper-trading against a broker.** Journal P&L is computed from user-entered exit prices only.
- **Not multi-user / hosted.** Local app; Flask auth callback is `http://127.0.0.1:5000/callback`.
- **Not a package.** Flat folder of `.py` files. No `src/`, no tests, no `requirements.txt` (venv has deps installed).

If the user asks to “auto trade”, “execute orders”, or “connect broker orders”, that is **new work**, not an existing feature. Confirm before adding it.

---

## 3. How to run

```text
cd C:\Users\Lenovo\Desktop\StockTradingAlgo
venv\Scripts\activate
streamlit run dashboard.py
```

Module-level scripts (optional, for debugging one layer):

```text
python config.py          # prints whether env keys loaded
python auth.py            # login / refresh token
python data_fetcher.py    # fetch watchlist candles
python indicators.py      # fetch + compute indicators
python news_fetcher.py    # print sample RSS headlines
python ai_analyst.py      # full Gemini batch analysis
python trade_journal.py   # inserts a SAMPLE test trade — avoid in prod data
python morning_brief.py   # full pipeline + save brief
```

Required `.env` keys (never commit or paste real values):

```text
UPSTOX_API_KEY=
UPSTOX_API_SECRET=
UPSTOX_REDIRECT_URL=http://127.0.0.1:5000/callback
GEMINI_API_KEY=
```

Token file: `db/upstox_token.json` (expires ~23 hours; `auth.load_token()` rejects older).

---

## 4. Repo layout (edit these only)

Ignore `venv/`. Do not put logic there.

| Path | Role |
|------|------|
| `config.py` | Env, watchlist seed, timeframes, indicator periods, paths |
| `auth.py` | Upstox OAuth2; Flask `/callback`; token save/load |
| `data_fetcher.py` | Candles, instrument keys, SQLite watchlist |
| `indicators.py` | RSI / EMA / MACD / BB + preliminary signal score |
| `news_fetcher.py` | RSS parse, stock/macro/global news |
| `ai_analyst.py` | Gemini prompts, JSON parse, rule overrides, news recommendations |
| `strategy_rules.json` | User-editable filters (no Python change needed for rule tweaks) |
| `trade_journal.py` | SQLite trades table, P&L, summaries |
| `morning_brief.py` | Formats + saves daily report |
| `dashboard.py` | Streamlit UI + pipeline orchestration |
| `system_info.py` | Documentation tab (mostly static; reads rules JSON live) |
| `db/trades.db` | SQLite: watchlist, instrument_keys, trades |
| `db/upstox_token.json` | Secret — do not log or commit |
| `logs/morning_brief_YYYY-MM-DD.txt` | Generated briefs |
| `.env` | Secret — do not commit or dump |

There is **no** `main.py`, `engine.py`, `trader.py`, or `orders.py`.

---

## 5. Runtime data flow

```text
User clicks RUN FULL ANALYSIS (dashboard)
    → get_access_token()                    # auth.py
    → get_watchlist_from_db()               # data_fetcher.py
    → fetch_candles() per symbol            # Upstox v2 historical-candle
    → calculate_indicators()                # indicators.py
    → get_news_for_batch()                  # news_fetcher.py
    → analyze_all_at_once()                 # ONE Gemini call for all stocks
    → _apply_rule_filters()                 # can force WAIT
    → session_state.results + indicators_map
    → optional log_trade()                  # journal only
    → optional generate_morning_brief()     # logs/*.txt
```

On-demand single symbol: `fetch_single_stock` → `calculate_indicators` → `analyze()` (separate Gemini call).

News Picks tab: `fetch_news_for_recommendations` → `recommend_stocks_from_news()` — **news only**, no candles/indicators.

---

## 6. Key contracts (do not break silently)

### 6.1 Indicator dict (`indicators.calculate_indicators`)

Returned keys used downstream:

`symbol`, `timestamp`, `open`, `high`, `low`, `close`, `volume`,  
`rsi`, `rsi_zone`,  
`ema9`, `ema21`, `ema_trend` (`BULLISH`/`BEARISH`), `ema_crossover` (`GOLDEN_CROSS`/`DEATH_CROSS`/`NONE`),  
`macd`, `macd_signal`, `macd_hist`, `macd_momentum` (`BULLISH`/`BEARISH`), `macd_crossover` (`BULLISH_CROSS`/`BEARISH_CROSS`/`NONE`),  
`bb_upper`, `bb_mid`, `bb_lower`, `bb_position` (`ABOVE_UPPER`/`UPPER_HALF`/`LOWER_HALF`/`BELOW_LOWER`), `bb_width`,  
`preliminary_signal` (`STRONG_BUY`/`BUY`/`WAIT`/`SELL`/`STRONG_SELL`).

Needs **≥ 25 candles**; MACD often needs **~35+**. Fetch uses default **30minute**, **10 calendar days**.

Preliminary score (local, before AI):

- RSI ≤ 35 +1; RSI ≥ 65 −1
- EMA9 > EMA21 +1 else −1; golden +2; death −2
- MACD hist > 0 +1 else −1; bullish cross +2; bearish cross −2
- BB below lower +1; above upper −1
- ≥3 STRONG_BUY, ≥1 BUY, ≤−3 STRONG_SELL, ≤−1 SELL, else WAIT

Gemini **can override** this. Rules can then override Gemini to WAIT.

### 6.2 Analysis dict (`ai_analyst`)

Expected fields:

`symbol`, `signal` (`BUY`/`SELL`/`WAIT`; Gemini prompt does not list STRONG_* as required output but journal treats `STRONG_BUY`/`STRONG_SELL` as long/short),  
`confidence` (0–100), `entry`, `target`, `stop_loss`, `risk_reward` (string like `"1:2.5"`),  
`news_sentiment` (`BULLISH`/`BEARISH`/`NEUTRAL`), `reasoning`, `indicators_summary`,  
`rule_violations` (list; empty if OK),  
optional `news_headlines`, `macro_headlines`.

On parse/API failure: `_fallback_response` → WAIT, confidence 0.

### 6.3 Rule filter behavior (`_apply_rule_filters`)

If any violation: **signal forced to WAIT**; `entry`/`target`/`stop_loss`/`risk_reward` set **None**; reasoning prefixed with override text.

Current `strategy_rules.json` (v1.0):

- `min_risk_reward`: 1.5 (parsed from `"a:b"` as b/a)
- `min_confidence`: 60
- `avoid_rsi_above`: 75 (blocks BUY)
- `avoid_rsi_below`: 20 (blocks SELL)
- `require_macd_confirmation`: true (BUY needs `macd_momentum == BULLISH`)
- `max_loss_per_trade_pct`: 1.0 (prompted to Gemini; **not** numerically enforced in Python except via prompt)
- JSON also has `avoid_first_minutes`, `avoid_last_minutes`, `max_trades_per_day` — **not enforced in `_apply_rule_filters`**. Do not claim they are live unless you implement them.

### 6.4 SQLite (`db/trades.db`, `config.DB_PATH`)

**watchlist:** `symbol PK`, `added_on`, `is_active` (remove = set 0, not delete).

**instrument_keys:** `symbol PK`, `instrument_key`, `added_on`. Seeded from hardcoded `INSTRUMENT_KEYS` in `data_fetcher.py`.

**trades:** analysis/trade dates, symbol, signal, confidence, entry/target/SL/R:R, reasoning, indicator snapshot columns, `status` (`OPEN`/`CLOSED`), `exit_price`, `pnl`, `outcome` (`WIN`/`LOSS`/`BREAKEVEN`), notes.

P&L: BUY/STRONG_BUY → `exit - entry`; else treated as short → `entry - exit`.

Trade date: if weekday and before/during market (09:15–15:30 local machine time) → today; else next weekday. **Holidays not skipped.** Timezone constant `Asia/Kolkata` exists in config but journal uses `datetime.now()` (machine local time).

---

## 7. File-by-file: what to change where

### `config.py`

Change: default watchlist seed (only used if DB watchlist empty), timeframe, lookback, indicator periods, paths, extra env vars.

Do not put runtime UI logic here.

### `auth.py`

Change: OAuth URLs, token TTL (currently 23h), callback port 5000.

`get_access_token()` is the only entry the dashboard should use. Flask `app.run` **blocks** until login completes.

### `data_fetcher.py`

Change: Upstox endpoints, candle parsing, watchlist CRUD, NSE instrument lookup (`NSE.json.gz`, `trading_symbol` + `instrument_type == EQ`).

Hardcoded `INSTRUMENT_KEYS` is fallback + seed. New symbols: `lookup_and_save_instrument_key()`.

Public functions dashboard uses: `fetch_candles`, `fetch_single_stock`, `init_watchlist_db`, `get_watchlist_from_db`, `add_stock_to_watchlist`, `remove_stock_from_watchlist`, `get_all_available_symbols`, `lookup_and_save_instrument_key`, `get_instrument_key`.

### `indicators.py`

Change: indicator math, scoring, zones. Keep return dict keys stable or update `ai_analyst` prompts + dashboard side panel + `system_info.py` together.

### `news_fetcher.py`

Change: RSS URLs, company name map (`COMPANY_NAMES`), recency windows, batch delays (`time.sleep` — keep polite).

Public: `get_news_for_analysis`, `get_news_for_batch`, `fetch_news_for_recommendations`, `fetch_stock_news`, `fetch_macro_news`, `fetch_global_market_news`.

Failed RSS → empty list, never crash the pipeline.

### `ai_analyst.py`

Change: Gemini model name, prompts, JSON schema, retries (429 wait 65s, 3 attempts), Claude swap comments at bottom (reference only).

`client = genai.Client(api_key=...)` at import time — missing key fails import of dashboard (`IMPORTS_OK` path).

Prefer **one batch call** `analyze_all_at_once` for watchlist (cost/rate limits).

### `strategy_rules.json`

Preferred place for risk/filter tweaks **if the field is actually read**. After adding a new JSON field, you **must** teach `_apply_rule_filters` and/or the prompt formatter `_format_rules_for_prompt`, or the setting is dead.

### `trade_journal.py`

Change: schema (migrations are DIY — `CREATE TABLE IF NOT EXISTS` will **not** add new columns to existing DBs), P&L formula, summaries.

`python trade_journal.py` writes a fake RELIANCE trade — do not run against a journal the user cares about.

### `morning_brief.py`

Change: report layout/text. Input is already-computed `all_analysis` + `all_indicators`. Overwrites `logs/morning_brief_{date}.txt` for that calendar day.

### `dashboard.py`

Change: layout, tabs, CSS (large `<style>` block at top), buttons, session_state keys.

Orchestration: `run_pipeline`, `run_full_analysis`, `run_single_analysis`, `render_side_panel`, `render_recommendations_tab`, `render_journal_tab`, `render_morning_brief_tab`.

Session keys: `log_lines`, `results`, `indicators_map`, `selected_stock`, `token`, `search_result`, `search_ind`, `trade_date_info`, `morning_brief_text`, `morning_brief_path`, `recommendations`, `rec_error`, `rec_sentiment`.

Logging a trade is a **button** in the side panel, not automatic after analysis.

### `system_info.py`

Docs UI. If you add an indicator, news source, or pipeline step, **update this tab** or it will lie to the user. Sub-tabs: Indicators, News Sources, Strategy Rules, AI Config, Data Pipeline.

---

## 8. External APIs

| Service | Used for | Code |
|---------|----------|------|
| Upstox OAuth | Login | `https://api.upstox.com/v2/login/authorization/dialog` + `/token` |
| Upstox candles | OHLCV | `GET https://api.upstox.com/v2/historical-candle/{instrument_key}/{timeframe}/{to}/{from}` |
| Upstox instruments | Symbol → key | `https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz` |
| Gemini | Signals + news picks | `google.genai` `client.models.generate_content` model `gemini-2.5-flash` |
| RSS | News | Reuters, CNBC, Yahoo, ET, Mint, Business Standard, Google News queries |

No Yahoo/AlphaVantage/NSE official Python SDK. No websocket LTP stream (except `get_latest_price` which is 1-minute historical candles, unused by dashboard).

---

## 9. Coding conventions in this repo

- Flat modules, functions (almost no classes except Flask `app`).
- Print + emoji logs in backend; dashboard also appends HTML log lines.
- Symbols always `.upper().strip()`.
- Fail soft: fetch/news/Gemini errors → skip stock or WAIT fallback, don’t crash the whole run if possible.
- Dashboard wraps imports in try/except and shows `Import error` if deps/keys blow up.
- CSS/HTML injected with `st.markdown(..., unsafe_allow_html=True)`.
- Currency displayed as `₹`.
- Comments like `# <<< SWAP >>>` mark Gemini vs Claude client lines.

When adding a feature:

1. Put domain logic in the matching module, not in `dashboard.py` except UI glue.
2. Keep dict keys backward compatible or update all consumers.
3. Do not add order placement unless explicitly requested.
4. Do not rewrite the UI theme unless asked.
5. Do not create `requirements.txt` / README unless asked (this context file is the intended AI brief).
6. Never commit `.env` or `db/upstox_token.json` or dump secrets in chat.

---

## 10. Common change requests → correct place

| User wants | Edit |
|------------|------|
| Different default stocks | `config.WATCHLIST` (seed only) and/or UI watchlist / DB |
| 5-minute or daily candles | `config.DEFAULT_TIMEFRAME` (Upstox: `1minute`, `5minute`, `15minute`, `30minute`, `1day`) |
| RSI length / EMA periods | `config.py` + mention in `system_info.py` |
| Stricter confidence / R:R | `strategy_rules.json` (already enforced) |
| Enforce max 3 trades/day | **New code** in `_apply_rule_filters` + journal count — JSON field is unused |
| Add Supertrend / VWAP | `indicators.py` return dict + prompts + dashboard panel + system_info |
| Switch Gemini → Claude | `ai_analyst.py` (comments already describe the swap) + env key in `config.py` |
| New news source | `GLOBAL_MARKET_FEEDS` in `news_fetcher.py` + system_info list |
| New dashboard tab | `dashboard.main()` tabs + new `render_*` |
| Persist more journal fields | `trade_journal` schema **and** migration for existing `trades.db` |
| Auto-log every BUY | `run_full_analysis` after results — currently manual button |
| Place real orders | **Does not exist** — design new module; keep it separate from analysis |
| Holidays / IST correctness | `trade_journal._next_trading_day` / `_get_trade_date_info` |

---

## 11. Known gaps / pitfalls (do not “fix” unless asked)

- No `requirements.txt` / README.
- `CANDLE_LOOKBACK` in config is unused; fetch uses `days_back=10`.
- `avoid_first_minutes`, `avoid_last_minutes`, `max_trades_per_day`, `require_ema_confirmation`, `trailing_sl` in JSON are largely unused in Python.
- `system_info.py` contains unused/import-time references to genai/anthropic around line 410 — docs file, not the live client (`ai_analyst.py` owns the client).
- Journal P&L is rupees per share, not position-size weighted (no quantity column).
- Streamlit + Flask auth: first-run login may need a free terminal/browser; token then reused.
- Batch Gemini JSON must be valid; `_clean_json` strips markdown fences.
- `recommend_stocks_from_news` may suggest symbols not in `instrument_keys`; user must analyse via on-demand lookup.
- Windows paths; timezone depends on OS clock.

---

## 12. Suggested reply style when changing this project

- Name the **file and function** you will touch.
- State whether the change is **UI-only**, **rule-only** (`strategy_rules.json`), or **pipeline**.
- If a JSON rule is unused, say so instead of pretending it works.
- Do not claim the app executes trades.
- Keep diffs small; match existing style (functions, prints, emoji logs, Streamlit HTML).
- After adding fields to indicator/analysis dicts, grep for the old keys in `dashboard.py`, `ai_analyst.py`, `morning_brief.py`, `trade_journal.py`, `system_info.py`.

---

## 13. One-paragraph summary (paste if context is tight)

StockTradingAlgo is a local Streamlit NSE analysis app: Upstox OAuth + historical candles (`data_fetcher.py`), pandas-ta indicators (`indicators.py`), RSS news (`news_fetcher.py`), Gemini 2.5 Flash signals with JSON strategy filters (`ai_analyst.py` + `strategy_rules.json`), manual SQLite journal (`trade_journal.py`), and a morning brief file. It does not place broker orders. Entry point: `streamlit run dashboard.py`. Config/secrets: `config.py` + `.env`. Change rules in `strategy_rules.json` only if `_apply_rule_filters` or the prompt already reads that field.
