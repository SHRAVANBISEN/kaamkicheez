"""Offline public-observation context; never a stock signal or identity inference."""

import json
import math
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "db" / "institutions.db"
_IST = timezone(timedelta(hours=5, minutes=30))
_KINDS = ("MARKET_FLOW", "OWNERSHIP", "DEAL")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS institutional_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    source_url TEXT NOT NULL,
    record_id TEXT NOT NULL,
    received_at TEXT NOT NULL,
    published_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
)
"""
_DEAL_WARNING = (
    "A large deal is not necessarily institutional activity. Every trade has a "
    "counterparty; disclosed rows are not summed or treated as market-wide net flows."
)


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string.")
    return value.strip()


def _symbol(value):
    value = _text(value, "symbol").upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9&-]{0,19}", value, flags=re.ASCII):
        raise ValueError("symbol must contain 1-20 NSE symbol characters: A-Z, 0-9, & or -.")
    return value


def _timestamp(value, field):
    if not isinstance(value, str) or "T" not in value:
        raise ValueError(f"{field} must be a timezone-aware ISO timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Timezone missing")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a valid timezone-aware ISO timestamp.") from exc


def _now(value):
    if value is None:
        return datetime.now(timezone.utc)
    return _timestamp(value.isoformat() if isinstance(value, datetime) else value, "now")


def _iso(value):
    return value.isoformat(timespec="microseconds")


def _date(value, field):
    try:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("Invalid date")
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD).") from exc


def _url(value, field):
    value = _text(value, field)
    try:
        parts = urlsplit(value)
        if (parts.scheme not in ("http", "https") or not parts.hostname
                or parts.username is not None or parts.password is not None
                or "\\" in value or any(c.isspace() or ord(c) < 32 for c in value)):
            raise ValueError("Invalid URL")
        parts.port
    except ValueError as exc:
        raise ValueError(f"{field} must be an HTTP(S) URL without credentials.") from exc
    return value


def _number(value, field, minimum=0, maximum=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number, not a boolean.")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if (not finite or value < minimum or (positive and value == minimum)
            or (maximum is not None and value > maximum)):
        raise ValueError(f"{field} is outside its finite permitted range.")
    return value


def _choice(payload, field, choices):
    value = payload.get(field)
    if value not in choices:
        raise ValueError(f"{field} must be one of: {', '.join(choices)}.")
    return value


def _validate(payload, received_at):
    if not isinstance(payload, dict):
        raise ValueError("Observation must be a JSON object.")
    result = {
        "kind": _choice(payload, "kind", _KINDS),
        "source_url": _url(payload.get("source_url"), "source_url"),
        "record_id": _text(payload.get("record_id"), "record_id"),
        "publication_status": _choice(
            {"publication_status": payload.get("publication_status", "UNKNOWN")},
            "publication_status", ("UNKNOWN", "PROVISIONAL", "FINAL", "REVISED"),
        ),
    }
    published = _timestamp(payload.get("published_at"), "published_at")
    if published > received_at:
        raise ValueError("published_at cannot be in the future.")
    observed = _date(payload.get("observation_date"), "observation_date")
    if observed > min(received_at.astimezone(_IST).date(), published.astimezone(_IST).date()):
        raise ValueError("observation_date cannot be future or after publication's Asia/Kolkata date.")
    result.update(published_at=_iso(published), observation_date=observed.isoformat())
    if payload.get("source_note") is not None:
        result["source_note"] = _text(payload["source_note"], "source_note")
    if result["kind"] == "MARKET_FLOW":
        result["scope"] = _text(payload.get("scope"), "scope")
        result["participant"] = _choice(payload, "participant", ("FII_FPI", "DII"))
        for field in ("gross_buy_crore", "gross_sell_crore"):
            result[field] = _number(payload.get(field), field)
        net = result["gross_buy_crore"] - result["gross_sell_crore"]
        result["net_crore"] = net
        result["flow_description"] = "NET_BUYING" if net > 0 else "NET_SELLING" if net < 0 else "BALANCED"
    else:
        result["symbol"] = _symbol(payload.get("symbol"))
        if result["kind"] == "OWNERSHIP":
            result["category"] = _text(payload.get("category"), "category")
            result["ownership_pct"] = _number(payload.get("ownership_pct"), "ownership_pct", maximum=100)
            previous_date = payload.get("previous_observation_date")
            previous_pct = payload.get("previous_ownership_pct")
            if (previous_date is None) != (previous_pct is None):
                raise ValueError("Previous observation date and ownership percentage must be supplied together.")
            result["change_percentage_points"] = None
            if previous_date is not None:
                if _date(previous_date, "previous_observation_date") >= observed:
                    raise ValueError("previous_observation_date must be strictly earlier.")
                result["previous_observation_date"] = previous_date
                result["previous_ownership_pct"] = _number(previous_pct, "previous_ownership_pct", maximum=100)
                result["change_percentage_points"] = result["ownership_pct"] - previous_pct
        else:
            result["deal_type"] = _choice(payload, "deal_type", ("BULK", "BLOCK"))
            result["participant_name"] = _text(payload.get("participant_name"), "participant_name")
            result["side"] = _choice(payload, "side", ("BUY", "SELL"))
            quantity = payload.get("quantity")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
                raise ValueError("quantity must be a positive integer, not a boolean.")
            result["quantity"] = _number(quantity, "quantity", positive=True)
            result["price"] = _number(payload.get("price"), "price", positive=True)
            try:
                notional = quantity * result["price"]
            except OverflowError as exc:
                raise ValueError("notional_inr must be finite.") from exc
            result["notional_inr"] = _number(notional, "notional_inr", positive=True)
            identity = payload.get("institutional_identity", "UNVERIFIED")
            if identity not in ("UNVERIFIED", "SOURCE_IDENTIFIED"):
                raise ValueError("institutional_identity must be UNVERIFIED or SOURCE_IDENTIFIED.")
            result["institutional_identity"] = identity
            if identity == "SOURCE_IDENTIFIED":
                result["identity_source_url"] = _url(payload.get("identity_source_url"), "identity_source_url")
            elif payload.get("identity_source_url") is not None:
                result["identity_source_url"] = _url(payload["identity_source_url"], "identity_source_url")
    return result


def save_observation(payload, db_path=DEFAULT_DB_PATH, now=None):
    """Validate then append; source record IDs identify revisions, not database rows.

    Caller-supplied receipt times/derived values in payload are ignored. ``now``
    is a server-clock injection for tests; production callers should omit it.
    """
    received_at = _now(now)
    observation = _validate(payload, received_at)
    serialized = json.dumps(observation, allow_nan=False)
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(path))) as connection:
        with connection:
            connection.execute(_SCHEMA)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS institutional_available "
                "ON institutional_observations(received_at, published_at)"
            )
            cursor = connection.execute(
                "INSERT INTO institutional_observations "
                "(kind, source_url, record_id, received_at, published_at, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (observation["kind"], observation["source_url"], observation["record_id"],
                 _iso(received_at), observation["published_at"], serialized),
            )
            return cursor.lastrowid


def _available_rows(path, current):
    if not path.exists():
        return []
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        if not connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='institutional_observations'"
        ).fetchone():
            return []
        # Rank source revisions before filtering symbol: a correction can change it.
        rows = connection.execute(
            "SELECT id, received_at, payload_json FROM ("
            "SELECT *, ROW_NUMBER() OVER (PARTITION BY kind, source_url, record_id "
            "ORDER BY published_at DESC, received_at DESC, id DESC) AS revision_rank "
            "FROM institutional_observations WHERE received_at<=? AND published_at<=?"
            ") WHERE revision_rank=1",
            (_iso(current), _iso(current)),
        ).fetchall()
    result = []
    for row_id, received, serialized in rows:
        row = json.loads(serialized)
        row.setdefault("publication_status", "UNKNOWN")
        row.update(id=row_id, evidence_id=f"institutional:{row_id}", received_at=received)
        result.append(row)
    return result


def _latest(rows, fields):
    groups = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        rank = (row["observation_date"], row["published_at"], row["received_at"], row["id"])
        if key not in groups or rank > groups[key][0]:
            groups[key] = (rank, row)
    return [entry[1] for _, entry in sorted(groups.items())]


def _section(rows, max_age, current):
    for row in rows:
        row["age_days"] = (current.astimezone(_IST).date() - date.fromisoformat(row["observation_date"])).days
        row["status"] = "STALE" if row["age_days"] > max_age else "FRESH"
        row["as_of"] = _iso(current)
        row["max_age_days"] = max_age
    statuses = {row["status"] for row in rows}
    status = "MISSING" if not rows else next(iter(statuses)) if len(statuses) == 1 else "PARTIAL"
    return {
        "status": status, "rows": rows, "max_age_days": max_age,
        "missing": [] if rows else ["No eligible manually imported observations known at analysis time."],
        "warnings": [], "as_of": _iso(current),
        "evidence_ids": [row["evidence_id"] for row in rows],
    }


def load_context(symbol, now=None, db_path=DEFAULT_DB_PATH, flow_max_age_days=7,
                 ownership_max_age_days=180, deal_max_age_days=7):
    """Return JSON-safe, independent sections with FRESH/STALE/PARTIAL/MISSING.

    Age is calendar days in Asia/Kolkata; the threshold is inclusive. Latest
    publication wins source revisions (receipt and ID break ties). Flows select
    latest dates separately per scope/participant/source; ownership separately
    per symbol/category/source. No aggregation across potentially overlapping rows.
    AVAILABLE means all three sections are fresh, not complete market coverage.
    """
    symbol, current = _symbol(symbol), _now(now)
    for name, value in (
        ("flow_max_age_days", flow_max_age_days),
        ("ownership_max_age_days", ownership_max_age_days),
        ("deal_max_age_days", deal_max_age_days),
    ):
        _number(value, name)
    rows = _available_rows(Path(db_path), current)
    flows = _latest([r for r in rows if r["kind"] == "MARKET_FLOW"],
                    ("scope", "participant", "source_url"))
    ownership = _latest([r for r in rows if r["kind"] == "OWNERSHIP" and r["symbol"] == symbol],
                        ("symbol", "category", "source_url"))
    deals = sorted(
        [r for r in rows if r["kind"] == "DEAL" and r["symbol"] == symbol],
        key=lambda r: (r["observation_date"], r["published_at"], r["received_at"], r["id"]),
        reverse=True,
    )
    context = {
        "symbol": symbol, "as_of": _iso(current), "status": "MISSING",
        "market_flows": _section(flows, flow_max_age_days, current),
        "ownership": _section(ownership, ownership_max_age_days, current),
        "deals": _section(deals[:50], deal_max_age_days, current),
        "warnings": [
            "Available evidence is not predictive, a buy/sell vote, or assurance of complete coverage.",
            "Manual public imports are not independently verified. No external data is fetched.",
            "Market flows describe their stated market scope, not this stock; overlapping scopes, "
            "sources and dates are not summed.",
            "Ownership changes are percentage-point differences, not net purchasing: denominators "
            "and corporate actions can change.",
            _DEAL_WARNING,
        ],
        "evidence_ids": [],
    }
    flow_section = context["market_flows"]
    for scope, source in sorted({(r["scope"], r["source_url"]) for r in flows}):
        group = [r for r in flows if r["scope"] == scope and r["source_url"] == source]
        latest_date = max(r["observation_date"] for r in group)
        participants = {r["participant"] for r in group if r["observation_date"] == latest_date}
        for participant in sorted({"FII_FPI", "DII"} - participants):
            flow_section["missing"].append(f"{scope} | {source}: {participant} missing for {latest_date}.")
    if flows and flow_section["missing"]:
        flow_section["status"] = "PARTIAL"
    context["deals"].update(total_available=len(deals), truncated=len(deals) > 50)
    if len(deals) > 50:
        context["deals"]["warnings"].append(
            f"Truncated: showing latest 50 of {len(deals)} eligible disclosed deals; no totals calculated."
        )
        context["deals"]["status"] = "PARTIAL"
    sections = [context[name] for name in ("market_flows", "ownership", "deals")]
    if any(section["rows"] for section in sections):
        context["status"] = "AVAILABLE" if all(s["status"] == "FRESH" for s in sections) else "PARTIAL"
    for name in ("market_flows", "ownership", "deals"):
        section = context[name]
        context["evidence_ids"].extend(section["evidence_ids"])
        context["warnings"].extend(f"{name}: {message}" for message in section["missing"] + section["warnings"])
        if any(row["status"] == "STALE" for row in section["rows"]):
            context["warnings"].append(f"{name}: stale observations exceed {section['max_age_days']} calendar days.")
    return context


def render_institutions_panel(symbols=None, settings=None):
    """Render explicit manual import and independent evidence sections."""
    import streamlit as st

    st.subheader("Institutional public observations")
    st.caption("Offline manual evidence only. No identity inference, market-control claims, or stock signals.")
    choices = sorted({_symbol(item) for item in (symbols or [])})
    selected = st.selectbox("Watchlist symbol", ["Type a symbol"] + choices, key="institutions_selection")
    typed = st.text_input("NSE symbol (overrides selection)", key="institutions_symbol")
    symbol = typed.strip() or (selected if selected != "Type a symbol" else "")
    with st.expander("Observation schemas and JSON templates"):
        st.write(
            "Each import is one object. Use the source's record_id again for a revision; "
            "give separate disclosed deals separate source record IDs. Source URLs must be HTTP(S). "
            "Publication must have a timezone; observation dates cannot exceed publication's "
            "Asia/Kolkata date or today. Receipt timestamps are supplied by the server. "
            "Gross flows must be nonnegative; ownership percentages must be 0-100. "
            "Previous ownership date/percentage are optional but required together; the date must be earlier. "
            "Deal quantity must be a positive integer and price positive. Identity defaults to UNVERIFIED; "
            "SOURCE_IDENTIFIED requires identity_source_url and explicit source identification. "
            "Optional publication_status is UNKNOWN (default), PROVISIONAL, FINAL or REVISED, "
            "as stated by the source; it is never inferred from dates or thresholds. "
            "Use source_note for additional source qualifiers."
        )
        common = {
            "source_url": "https://example.com/REPLACE-WITH-PUBLIC-SOURCE",
            "record_id": "REPLACE-WITH-SOURCE-RECORD-ID",
            "published_at": "2026-01-02T18:00:00+05:30",
            "observation_date": "2026-01-02",
            "publication_status": "UNKNOWN",
            "source_note": "REPLACE-WITH-SOURCE-QUALIFIERS-OR-REMOVE",
        }
        templates = [
            dict(common, kind="MARKET_FLOW", scope="NSE+BSE+MSEI cash equity",
                 participant="FII_FPI", gross_buy_crore=None, gross_sell_crore=None),
            dict(common, kind="OWNERSHIP", symbol=symbol or "RELIANCE", category="FII/FPI",
                 ownership_pct=None, previous_observation_date=None, previous_ownership_pct=None),
            dict(common, kind="DEAL", symbol=symbol or "RELIANCE", deal_type="BULK",
                 participant_name="REPLACE-WITH-DISCLOSED-NAME", side="BUY", quantity=None,
                 price=None, institutional_identity="UNVERIFIED"),
        ]
        st.caption("Replace all placeholders, dates and null amounts with actual public observations. Nothing is auto-saved.")
        for template in templates:
            st.download_button(
                f"Download {template['kind']} template", json.dumps(template, indent=2),
                file_name=f"institutions_{template['kind'].lower()}.json", mime="application/json",
                key=f"institutions_template_{template['kind']}",
            )
            st.json(template)
    with st.form("institutions_import"):
        raw = st.text_area("Paste observation JSON", key="institutions_payload")
        submitted = st.form_submit_button("Validate and save observation")
    if submitted:
        try:
            payload = json.loads(raw)
            row_id = save_observation(payload)
        except (ValueError, sqlite3.Error, OSError) as exc:
            st.error(f"Observation was not saved: {exc}")
        else:
            st.success(f"Saved institutional:{row_id}.")
            if not symbol:
                symbol = payload.get("symbol", "")
    if not symbol:
        st.info("Select or enter a symbol to see stock evidence alongside market-wide flows.")
        return
    try:
        arguments = {key: settings[key] for key in (
            "flow_max_age_days", "ownership_max_age_days", "deal_max_age_days"
        ) if settings is not None and key in settings}
        context = load_context(symbol, **arguments)
    except (ValueError, sqlite3.Error, OSError) as exc:
        st.error(f"Could not load observations: {exc}")
        return
    st.write(f"Context: {context['status']} | Analysis as of: {context['as_of']}")
    for warning in context["warnings"]:
        st.caption(warning)
    for key, title in (("market_flows", "Market-wide flows (INR crore)"),
                       ("ownership", "Stock ownership (%)"),
                       ("deals", "Disclosed deals (price and notional in INR)")):
        section = context[key]
        st.write(f"{title}: {section['status']} | Maximum age: {section['max_age_days']} calendar days")
        for message in section["missing"]:
            st.info(message)
        if section["rows"]:
            primary_fields = {
                "market_flows": ("scope", "participant", "net_crore"),
                "ownership": ("category", "ownership_pct", "change_percentage_points"),
                "deals": ("deal_type", "participant_name", "side", "institutional_identity", "notional_inr"),
            }[key]
            fields = (
                "evidence_id", "observation_date", "status", "publication_status",
                *primary_fields, "source_url",
            )
            st.table([{field: row.get(field) for field in fields} for row in section["rows"]])
    with st.expander("Raw selected evidence and provenance"):
        st.json(context)
