# StockTradingAlgo

NSE equity intraday research dashboard. A fixed data/analysis pipeline supplies
evidence to a configurable LLM; deterministic rules validate its proposal.
It is not an autonomous trading agent and does not place orders.

## Repository map

```text
StockTradingAlgo\             <- main folder / Git root
  dashboard.py               <- Streamlit entry point
  stocktrading\              <- application Python package
    config.py                <- paths and indicator settings
    data_fetcher.py          <- broker candles and watchlist
    auth.py                  <- broker authentication
    indicators.py
    intraday_engine.py       <- deterministic technical calculations
    fundamentals.py          <- financial/event evidence
    institutions.py          <- public institutional observations
    news_fetcher.py          <- RSS news
    ai_analyst.py            <- combined evidence and final model analysis
    llm_provider.py          <- Gemini / NVIDIA / compatible server
    decision_evidence.py     <- conclusion trace
    analysis_evidence.py     <- saved analysis history
    trade_journal.py
    morning_brief.py
    system_info.py           <- dashboard methodology screens
  resources\                 <- strategy_rules.json, research_catalog.json
  tests\                     <- offline tests
  docs\                      <- model setup and implementation handoff
  .streamlit\                <- dashboard theme
  requirements.txt
  .env.example
  PROJECT_CONTEXT.md
  db\                        <- existing local databases/tokens; unchanged
  logs\                      <- existing local reports; unchanged
```

## Run from this folder

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 -m streamlit run dashboard.py
```

Use your existing `.env` or configure it from `.env.example`.
Model setup: [docs\MODEL_SETUP.md](docs/MODEL_SETUP.md).
Implementation notes: [docs\INTRADAY_HANDOFF.md](docs/INTRADAY_HANDOFF.md).

```powershell
# Broker login (when needed)
.\.venv\Scripts\python.exe -X utf8 -m stocktrading.auth

# Offline test suite
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -t . -q
```

Indicators/news are collected programmatically; fundamental and institutional
observations currently use manual imports. No model's profitability or exact
price accuracy has been established. See System Info for evidence and limitations.
