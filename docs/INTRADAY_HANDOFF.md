# Intraday enhancement handoff - application methodology 3.0

Repository layout: `stocktrading\` contains implementation modules, `tests\`
contains automated coverage, `resources\` contains strategy rules/research JSON,
and `docs\` contains guides. `dashboard.py` remains the root launch script.
All commands below run from the repository root. Existing `.env`, `db\` and
`logs\` stay there; the reorganization does not relocate user data.

## What is implemented

| Part | Working implementation |
| --- | --- |
| Technical process | Completed-bar validation, normal-session/time/freshness gates, opening-range/VWAP/EMA/ADX/RSI/volume alignment; weak/ranging or conflicting data means WAIT |
| Indicators | Local EMA9/21, RSI14, ATR14, DI14/ADX14, session VWAP, same-slot RVOL (5 observed prior sessions), OR15, previous complete observed-session levels, MACD12/26/9 and BB20/2 context |
| Fundamentals | Timestamped sector-aware quality/context, matched cash-flow periods, accrual/FCF/liquidity/coverage ratios and sourced EPS expectations, explicit eligibility plus event review |
| Research | 13 paper references and 3 official disclosure references; findings, implemented implications, unimplemented methods and exact reading scope in research_catalog.json |
| News | Existing RSS stock/macro/global news remains connected; completeness and provenance are limited |
| Institutions | Manual public flows, ownership and named bulk/block observations; scope, provenance, freshness, revisions and missing coverage; no identity inference or extra trading votes |
| Market sentiment | News and manual market-flow context; breadth, sector/index strength, VIX and FX/yields remain unconnected |
| Evidence | Input-ID register, exact prompts/system instructions, model configuration/proposal, rule overrides, final conclusions and sources; persistent JSON download |
| Models | Gemini retained; NVIDIA hosted/OpenAI-compatible adapters added. Provider/model selection is in local .env, not analysis code |

Everything above is visible in **System Info**. Analysis also shows each stock's
calculated technical evidence and missing/blocking conditions. System Info's
Technical process section supports local CSV inspection without any API.
No automatic trades, no proven price targets, no profit guarantee.

## How a technical candidate is formed

Default bars are 5-minute, regular 09:15-15:30 IST sessions. History and today's
bars come from separate Upstox v3 endpoints. Unfinished bars are excluded.
Indicator state carries across observed sessions; VWAP and opening range reset.
Invalid inputs are rejected; missing session bars disable session VWAP/range.

BUY requires a completed close above the OR15 high and session VWAP, EMA9 above
EMA21, RSI between 50 and 75, ADX at least 20, same-slot RVOL at least 1.2, and
price no farther than 2 ATR from VWAP. SELL mirrors the direction with RSI20..50.
Default minimum warm-up is 100 bars; minimum calculation history is 35 bars.
RVOL requires 5 prior corresponding clock slots with a positive mean volume.
The volume baseline excludes today's session. No universal intraday volume
shape is assumed. VWAP uses typical-price OHLCV, not exact trade-level VWAP.

These values are transparent **starting choices, not optimal parameters**.
RSI is not an automatic oversold-buy rule. MACD/BB are not extra votes.
Opening-range breakout is a state, not an automatically de-duplicated trade event.
Previous observed-session levels are context only, not a support/resistance model.
No multi-timeframe/sector/index confirmation or range strategy has been added.

Default first/last 15-minute no-entry windows are enforced. Completed-bar age
must be within one bar interval plus 90 seconds, from the latest bar end.
The LLM cannot turn an unsupported setup into a trade candidate. Price fields
must be finite, positive and ordered correctly; R:R is recomputed from prices.
There is no executable-quote, fill, fee/slippage or account-risk validation yet.

## Fundamental workflow in simple language

1. Get the company's actual exchange filing/financial statement.
2. In System Info -> Fundamentals, download the JSON template.
3. Replace example source/dates with real values. Use the same monetary unit,
   reporting basis and comparable reporting periods for every amount.
4. Enter actual figures; leave unavailable figures null, not zero.
5. Manually review relevant company/macro events. Supply explicit event times,
   importance HIGH/NORMAL and a genuine `events_reviewed_at` time.
6. Paste the JSON and press Validate and save. A new snapshot is preserved.

Required fields: `symbol`, `source_url`, timezone-aware `published_at`,
`period_end`, `amount_unit`, `reporting_basis` (consolidated/standalone).
Optional figures: `revenue`, `revenue_previous`, `net_profit`,
`net_profit_previous`, `operating_cash_flow`, `total_debt`, `total_equity`.
Optional events: `events_reviewed_at`, `events` containing `title`, timezone-aware
`at`, and `importance`. A reviewed empty list is a human claim, not proof of safety.

Financial context is stale after 120 days from publication OR period end.
Financial missingness/staleness is displayed, not converted to a directional score.
Event reviews expire after 24 hours; missing/unreviewed/stale events block entry
by default. HIGH events block from 60 minutes before through 30 minutes after.
These windows are configurable policy, not research-proven optimal timings.
Fundamental/event and institutional evidence is sent to the selected model with technicals, so only enter
information you are authorized to send to that provider.

### New fundamental layers

For intraday research, the best fit is **new information and expectations first,
financial quality second**. A long-horizon valuation is not a minute-level price
target. There is no universally best fundamental method.

Set `entity_type` to NON_FINANCIAL, BANK, NBFC, INSURANCE or UNKNOWN.
Provide `period_start` and, for cash metrics, matching `cash_flow_period_start`
and `cash_flow_period_end`. Mark `comparisons_comparable` only when actually
comparable. Optional accounting inputs include `assets_begin`, `assets_end`,
`current_assets`, `current_liabilities`, `ebit`, `interest_expense`, `capex`.
They support average-asset ROA, a cash-based accrual proxy, FCF, current ratio and
interest coverage where sector/data eligibility permits. These are descriptive
ratios, not a score. Banking NPA/capital-adequacy fields are reported values, not
recalculated prudential compliance. Insurance-specific valuation/solvency analysis
is not implemented; generic nonfinancial ratios are deliberately suppressed.

The `earnings_expectation` template in System Info includes actual and consensus
EPS, announcement and consensus timestamps, period/currency/EPS basis, reporting
scope, reported/adjusted definition and split basis. Consensus must predate the
announcement. Missing optional comparability qualifiers make the result UNVERIFIED;
contradictory qualifiers are rejected. Surprise is actual minus consensus;
percentage divides by ABS(consensus), not signed consensus. The configurable
`min_abs_consensus_eps` defaults to 0.01 EPS currency units: a numerical policy,
not a research threshold. Below it, only the absolute difference is meaningful.
This is not standardized surprise, post-earnings drift or a Friday trading rule.

For eligible nonfinancial inputs, cash accruals =
`(net_profit - operating_cash_flow) / average_assets * 100`.
Matching periods/units/reporting scope are essential; do not combine quarterly
profit with annual cash flow or parent-attributable income with incompatible
consolidated CFO. A positive proxy is not fraud or proof of poor earnings quality.
No regression using unavailable future cash flows is used.

### Institutional workflow

In System Info -> Institutions, choose a template and paste one sourced observation:

- MARKET_FLOW: scope, participant FII_FPI/DII, observation_date, gross_buy_crore,
  gross_sell_crore. Net = buy minus sell. It is market-wide, not a stock's inflow.
- OWNERSHIP: symbol/category/date/ownership_pct; optionally previous date/percentage.
  Change is percentage points, not shares bought or the timing of trades.
- DEAL: symbol/date, BULK/BLOCK source classification, disclosed participant/side,
  quantity and price. Notional = quantity x price. Identity defaults UNVERIFIED.

All require a `record_id`, source URL and timezone-aware publication time.
Receipt time is recorded automatically. Reuse the source record ID for revisions.
Use `publication_status` when the source identifies PROVISIONAL/FINAL/REVISED;
otherwise UNKNOWN. Evidence is not aggregated across overlapping scopes/sources.
Default context-age limits are 7 days for flows/deals and 180 for ownership,
all **calendar-day engineering choices**, not publication deadlines.
Only observations known by both publication and receipt time enter a decision.
Missing observations are not evidence that institutions were inactive.

The existing OHLCV RVOL/VWAP features can describe participation, but cannot
reveal hidden orders, investor identity, coordinated activity or causal price
impact. No institution-following trade strategy has been claimed.

## Research used and its limits

- Lo, Mamaysky & Wang (2000): objective pattern definitions/statistical validation
  -> explicit versioned rules; we did NOT reproduce their kernel method.
- Mu, Chen, Kertesz & Zhou (2009/2010): volume has time-of-day structure
  -> same-slot RVOL, not an undifferentiated recent-bar average.
- Bailey, Borwein, Lopez de Prado & Zhu (2016 online): selection can overfit
  -> recorded settings and explicit unvalidated status; no PBO calculation yet.
- Andersen, Bollerslev, Diebold & Vega (2005 working paper): macro surprises have
  context-dependent effects -> timestamped events kept separate from direction.
- Cutler, Poterba & Summers (1988 working paper): recorded news explains only
  some price movements -> missing news is unknown, not an all-clear.
- Sloan (1996) and Dechow/Dichev (2002): earnings components and accrual-quality
  caveats -> matched-period cash context, no fraud claim or future-cash regression.
- DellaVigna/Pollet (2009): announcement timing/attention -> explicit event times,
  not a Friday strategy.
- Piotroski (2000) and Bernard/Thomas (1989): longer-horizon references retained
  with **bibliography-only** verification; no F-score or PEAD replication claimed.
- Kyle (1985), Chan/Lakonishok (1995), Lakonishok/Shleifer/Vishny (1992):
  liquidity, identified institutional trades and quarterly-holdings limitations
  -> separate public observations, no identities inferred from candles.
- SEBI bulk disclosure (2004), block-framework update (2025), LODR consolidated
  landing page (2026): source references only; operative PDF provisions were not
  read, so transaction thresholds/deadlines are not hard-coded as verified law.

Primary links and reading scope are in System Info -> Research papers and
`research_catalog.json`. Only the Mu paper's relevant full-text sections were
examined; other findings were verified against primary abstracts/metadata.
None of these studies validates this exact NSE intraday combination.
Vendor indicator documentation establishes conventions, not profitability.

## Run on your personal laptop

Use Python 3.11 or newer. Recreate the environment; do not copy a Windows venv.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 -m streamlit run dashboard.py
```

The old `venv` here points to a missing Python installation. `.venv` has been
restored in this checkout. No new system-wide tools or broker subscriptions
were installed. Live broker/provider access still needs your own credentials
and network permissions; offline/mocked operation is not proof of live access.
Use `-X utf8` for the application's legacy emoji console logs on Windows.

| Service | What to do |
| --- | --- |
| Upstox | Create an app at the official Developer portal; set redirect `http://127.0.0.1:5000/callback`; put `UPSTOX_API_KEY`, `UPSTOX_API_SECRET`, `UPSTOX_REDIRECT_URL` in local `.env`; run `.\.venv\Scripts\python.exe -X utf8 -m stocktrading.auth` and complete login. Confirm current v3 market-data permissions/limits/charges. |
| Gemini | Create a key in Google AI Studio; set `GEMINI_API_KEY` locally. Free-tier availability and limits vary. Current model is gemini-2.5-flash. |
| RSS | No key. Configured publisher domains must be reachable; they may fail or lag. |
| Fundamentals/events | No API/key required: manually import public/authorized filings and event reviews. An automated provider is not integrated. |
| NVIDIA / compatible server | Integrated transport. Follow MODEL_SETUP.md or System Info -> Model setup. Set LLM_PROVIDER, LLM_MODEL and the appropriate key/endpoint; restart. No automatic provider fallback. |
| Institutions | No new API subscription: manually import public/authorized dated observations. Current automated NSE access was not verified. |

Upstox endpoint references were read:
https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/
and https://upstox.com/developer/api-documentation/v3/get-intra-day-candle-data/.
NVIDIA references: https://build.nvidia.com/ and
https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-9B-v2.
NVIDIA's official model documentation was accessible in this later session.
The originally planned Nano 9B v2 was absent from the public hosted model list
checked on 2026-10-25; account entitlement and actual inference are not verified.
`MODEL_SETUP.md` explains local hosting vs selecting an available hosted model.
Do not bypass company network policy to make any service work.

## Resume next

Read `PROJECT_CONTEXT.md`. Next priorities are: raw-candle/event replay storage;
exchange calendar and explicit multi-timeframe/sector context; automated
timestamped filings/news; spread/cost/exposure/sizing limits; chronological
backtesting and paper observation. Test net expectancy/drawdown after costs,
not just accuracy. Record all parameter trials; reserve untouched evaluation data.
Automated institutional/market-sentiment adapters and model comparisons follow reliable data.
Do not add automatic orders without a separately agreed execution design.

## Local-data reminder

`.gitignore` does not untrack files already in Git. `.env` and the broker-token
file were tracked before this work; keep them local when sharing/pushing.
Existing journal DBs, logs and audit exports can contain private trading data.
