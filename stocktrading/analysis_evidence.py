"""Local audit history; does not fetch data or place orders."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from stocktrading.llm_provider import get_settings
from stocktrading.config import PROJECT_ROOT, RESOURCE_DIR, DOCS_DIR

AUDIT_DB = PROJECT_ROOT / "db" / "analysis_evidence.db"
GUIDE = DOCS_DIR / "INTRADAY_HANDOFF.md"


def _connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE IF NOT EXISTS analysis_runs "
        "(id TEXT PRIMARY KEY, recorded_at TEXT NOT NULL, payload TEXT NOT NULL)"
    )
    return connection


def save_evidence(indicators, news, rules, prompt, results, db_path=AUDIT_DB):
    run_id = uuid4().hex
    recorded_at = datetime.now(timezone.utc).isoformat()
    model = get_settings().metadata()
    payload = {
        "schema_version": 3,
        "run_id": run_id,
        "recorded_at_utc": recorded_at,
        "provider": model["provider"],
        "model": model["model"],
        "model_configuration": model,
        "scope": "Technical/news decision support, not validated intraday execution",
        "indicators": indicators,
        "news": news,
        "rules": rules,
        "prompt": prompt,
        "results": results,
        "research_basis": json.loads((RESOURCE_DIR / "research_catalog.json").read_text(encoding="utf-8")),
        "limitations": [
            "Candle timestamps are source times; recording time is not data freshness.",
            "Freshness/regular-session gates exist; spread, exchange holidays and executable prices are unverified.",
            "Empty news means unavailable or no headlines, not neutral sentiment.",
            "Financial/event and institutional inputs are manually supplied; broad live sentiment feeds are not connected.",
            "Research sources inform the design; no paper replication or net-of-cost backtest has been performed.",
            "LLM confidence is not a calibrated probability of profit.",
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=True, default=str, allow_nan=False)
    connection = _connect(db_path)
    try:
        with connection:
            connection.execute(
                "INSERT INTO analysis_runs VALUES (?, ?, ?)",
                (run_id, recorded_at, encoded),
            )
    finally:
        connection.close()
    return run_id


def list_runs(db_path=AUDIT_DB):
    connection = _connect(db_path)
    try:
        return connection.execute(
            "SELECT id, recorded_at FROM analysis_runs ORDER BY recorded_at DESC LIMIT 50"
        ).fetchall()
    finally:
        connection.close()


def load_run(run_id, db_path=AUDIT_DB):
    connection = _connect(db_path)
    try:
        row = connection.execute(
            "SELECT payload FROM analysis_runs WHERE id = ?", (run_id,)
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ValueError(f"Analysis run not found: {run_id}")
    return json.loads(row[0])


def render_evidence_panel():
    import streamlit as st

    st.subheader("Intraday roadmap and evidence history")
    st.warning(
        "Research only: current signals are not validated for live intraday trading. "
        "Missing data is unknown, not confirmation. No orders are placed."
    )
    with st.expander("Eight-part design and personal-laptop setup"):
        st.markdown(GUIDE.read_text(encoding="utf-8"))
    try:
        runs = list_runs()
        if not runs:
            st.info("No recorded analysis yet. Batch and single-stock analysis will save evidence here.")
            return
        labels = {run_id: f"{recorded_at} | {run_id[:8]}" for run_id, recorded_at in runs}
        selected = st.selectbox("Recent runs (UTC, newest 50)", list(labels), format_func=labels.get)
        payload = load_run(selected)
        from stocktrading.system_info import render_decision_trace

        st.caption(f"Recorded {payload['recorded_at_utc']} | {payload['provider']} / {payload['model']}")
        results = payload.get("results", {})
        if results:
            symbol = st.selectbox("Recorded decision", list(results), key="recorded_decision")
            render_decision_trace(results[symbol])
        with st.expander("Complete recorded inputs, prompt, rules and outputs"):
            st.json(payload)
        st.download_button(
            "Download evidence JSON",
            json.dumps(payload, indent=2),
            file_name=f"analysis_{selected}.json",
            mime="application/json",
        )
    except (sqlite3.Error, OSError, ValueError) as exc:
        st.error(f"Evidence history unavailable: {exc}")
