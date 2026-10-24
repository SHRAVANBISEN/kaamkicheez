# StockTradingAlgo - developer context

Read this and `docs\INTRADAY_HANDOFF.md` before changing the project.
The implementation is a local Streamlit NSE cash-equity intraday **research and
decision-support** application, not an order bot or a proven trading strategy.

## Repository layout

The Git root is the folder containing `dashboard.py`, `.git` and this file.
Business logic modules live in the `stocktrading\` Python package. Test modules
live in `tests\`, JSON rules and the research catalogue in `resources\`, and
guides in `docs\`. The module names below refer to files inside `stocktrading\`
unless explicitly stated otherwise. Imports use the `stocktrading.` prefix.
`dashboard.py` remains at the root as the Streamlit entry point.
`.env`, `db\`, `logs\`, `.venv\` and `.git` have NOT been moved.
Paths are anchored to `stocktrading.config.PROJECT_ROOT`, not the shell cwd.

## Current implementation (application methodology 3.0; technical engine 2.0)

1. Upstox OAuth remains in `auth.py`.
2. `data_fetcher.fetch_candles` requests Upstox **v3** historical candles through
   yesterday plus today's intraday candles. Default **5minute**; supported
   intervals: 1minute, 5minute, 15minute. Requests time out after 20 seconds.
3. `indicators.calculate_indicators` delegates to `intraday_engine.calculate_features`.
   It preserves existing output keys, but the old additive indicator score is
   replaced by an explicit trend-breakout setup. pandas-ta is no longer required.
4. The engine rejects malformed/timezone-less/duplicate/non-regular-session data,
   ignores unfinished bars, calculates indicators locally, and records readiness
   blockers and parameter snapshots.
5. `ai_analyst` attaches point-in-time manual fundamental/event and institutional
   context, adds an evidence-ID register to the prompt, calls the selected model, then applies deterministic
   rule filters. LLM errors produce explicit unavailable WAIT responses.
6. `analysis_evidence.save_evidence` persists exact prompts, indicators (including
   fundamentals/institutions), news, rules, research catalogue, model settings/system
   prompt and filtered outputs. A decision trace preserves the model proposal,
   deterministic overrides and optionally cited evidence IDs.
7. Dashboard Analysis displays technical evidence with the existing results,
   journal and morning-brief features. System Info contains process, indicator,
   fundamental, institutional, research, market-coverage, decision-rule, model-setup
   and evidence sections. Offline CSV inspection needs neither broker nor LLM API.
8. `llm_provider.py` supports Gemini, NVIDIA hosted and OpenAI-compatible servers.
   `.env` chooses provider/model; there is no silent fallback. `docs\MODEL_SETUP.md`
   explains setup and the original 9B model's current hosted-availability caveat.

## Files and ownership

| File | Responsibility |
| --- | --- |
| config.py | Environment variables, broker/watchlist paths, indicator lengths, default timeframe |
| resources\strategy_rules.json | Live-read thresholds, intraday feature gate, entry/event windows and legacy preferences |
| intraday_engine.py | Candle validation, session features, Wilder/EMA calculations, explicit setup |
| indicators.py | Compatibility facade: calculate_indicators and calculate_all |
| fundamentals.py | Validated manual snapshots, SQLite persistence, point-in-time context and import UI |
| institutions.py | Sourced market flows, ownership and named deal observations; manual import and point-in-time selection |
| decision_evidence.py | Bounded prompt evidence register and proposal/rule/final-decision trace |
| llm_provider.py | Configurable provider transports, limits, timeouts, response checks and safe metadata |
| .env.example / docs\MODEL_SETUP.md | Provider configuration template and personal-laptop setup |
| .streamlit/config.toml | Project-scoped dark theme; no restructuring or external font dependency |
| resources\research_catalog.json | Primary research links, findings, implemented implications and limitations |
| ai_analyst.py | Evidence prompts, selected-model calls, parsing, rule filtering and evidence persistence |
| analysis_evidence.py | Audit DB and history/download UI |
| system_info.py | Live methodology UI, research catalogue, offline CSV inspection |
| dashboard.py (repository root) | Existing orchestration, analysis/watchlist/search/journal/brief tabs |
| data_fetcher.py | Broker candles, instrument lookup, watchlist DB |
| news_fetcher.py | Existing RSS collection; no API key, coverage may be incomplete |
| auth.py | Existing OAuth callback and token loading |
| trade_journal.py | Manual journal only; no broker orders |
| morning_brief.py | Formats existing analysis into a saved report |
| requirements.txt | Portable runtime dependencies (Python 3.11+; .venv restored here) |
| tests\test_*.py | unittest, synthetic data, mocked transports and Streamlit UI coverage |

## Contracts

Existing indicator keys remain: symbol, timestamp, OHLCV, rsi/rsi_zone,
ema9/ema21/ema_trend/ema_crossover, macd/macd_signal/macd_hist/macd_momentum/
macd_crossover, bb_upper/bb_mid/bb_lower/bb_position/bb_width, preliminary_signal.
EMA output names are legacy aliases; keep their configured periods 9/21 unless
updating downstream labels too. New `intraday` contains source, receipt time,
bar end/age, settings and indicator parameter snapshots, VWAP, ATR, ADX, regime,
RVOL/sample count, opening range, previous complete observed-session levels,
setup, reasons, warnings and blockers.

DataFrames require timezone-aware `timestamp`, one `symbol`, and finite positive
OHLC plus nonnegative volume. Source `attrs` carry `timeframe_minutes`, `source`
and `received_at`. Manual CSV requires users to select its true timeframe.
At least 35 completed bars are needed for calculations; the default readiness
warm-up is 100. No missing indicator should be promoted to a neutral observation.

`fundamentals.save_snapshot(payload, db_path=..., now=None)` is append-only.
`load_context(symbol, now=None, ...)` excludes future receipts/publications,
derives safe ratios and returns financial/event statuses, source/timestamps,
missing fields, warnings, blockers and the source snapshot.
Financial age is context, not a universal direction gate. Event coverage gates
entry by default. Known high-impact event windows still block if event-review
requirement is disabled. No external fundamental API is connected.

Fundamental optional extensions cover entity_type, period_start, comparable
period declarations, matching cash-flow windows, sector-eligible ROA, cash accruals,
FCF/current/coverage ratios, reported banking ratios and sourced EPS expectations.
Every metric exposes its definition and eligibility. Missing sector/basis data
is UNVERIFIED, not proven suitable. Generic industrial ratios are suppressed for
financial entities. No Piotroski F-score, accrual strategy or PEAD model is claimed.

`institutions.save_observation` / `load_context` preserve sources, publication,
receipt and observation dates. Market flows remain scoped/category-specific,
ownership changes are percentage points, and named deals are not automatically
institutional. Sections have independent status; stale data is still explicitly
labelled context. Records are not additional directional gates.

`decision_evidence.evidence_packet` supplies stable IDs; at most 10 institutional
rows per section enter a prompt (full selected context is audited; deals themselves
are capped at 50 with a truncation warning). Invalid model-cited IDs force WAIT.
The evidence register shows supplied data, not proof that the model used it all.

Analysis keeps BUY/SELL/WAIT, confidence, entry, target, stop_loss, risk_reward,
news_sentiment, reasoning, indicators_summary and rule_violations. WAIT clears
price fields. R:R is calculated from finite, correctly ordered prices, **before
costs**. Freshness/time/event windows are rechecked after the LLM returns.
The intraday feature flag controls the new final setup gates, not raw calculations.
Do not describe confidence as profit probability.

## Storage and runtime

- `db/trades.db`: existing watchlist, instrument_keys and manual trades.
- `db/fundamentals.db`: new append-only fundamental_snapshots.
- `db/institutions.db`: append-only institutional_observations.
- `db/analysis_evidence.db`: analysis_runs; schema version 3 payloads, older records readable.
- `.env`, `db/upstox_token.json`: local credentials; never display contents.
- `logs/`: existing morning briefs. The old journal/debug script can write fake
  trades if run directly; do not run it against real user data.

Run from the project folder:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m streamlit run dashboard.py
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -t . -q
```

Provider clients are initialized only on requests; missing keys do not prevent System Info loading.
The old `venv` references a missing Python installation in this checkout.
Use `.venv` here; recreate it from requirements on another laptop.
`-X utf8` prevents legacy emoji console logs failing under Windows CP1252 output.

## Explicitly not implemented

Live WebSocket/order-book data, real execution or exit scheduling, spread checks,
fees/slippage, account sizing/exposure/daily loss or trade-count enforcement,
exchange holiday/special-session calendar, sector/index relative strength,
multi-timeframe confirmation, automated fundamentals/events/institutional feeds,
institutional identity inference, broad sentiment feeds, paper replication or backtesting.
NVIDIA transport is integrated but no weights/server were installed and no
authenticated NVIDIA inference was performed. The planned Nano 9B v2 ID was absent
from the public hosted listing checked 2026-10-25; configure an available account
model or a compatible server. Never silently switch models on a 404.
News Picks are news-only, not vetted intraday entries, and not in the audit DB.
Audit history omits raw candles/API responses and is not a complete replay system.
The journal still uses legacy machine-local/weekday-based dates; it is not an
exchange calendar. See the handoff for the next implementation priorities.
