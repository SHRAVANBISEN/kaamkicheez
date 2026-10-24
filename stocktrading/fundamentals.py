"""Offline, append-only financial and manually reviewed event context.

Amounts must share amount_unit and reporting_basis, including prior-period
comparatives. Unconfirmed comparisons are descriptive and explicitly unverified.
No external data, valuation model, universal score, or trade recommendation.
Research IDs identify motivating ideas, not paper replications or NSE/intraday
profitability claims. All accounting periods and dates are user-supplied.
"""

import json
import math
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "db" / "fundamentals.db"
METHOD_VERSION = "fundamentals-context-2"
LEGACY_NUMERIC_FIELDS = (
    "revenue", "revenue_previous", "net_profit", "net_profit_previous",
    "operating_cash_flow", "total_debt", "total_equity",
)
ADVANCED_NUMERIC_FIELDS = (
    "assets_begin", "assets_end", "current_assets", "current_liabilities",
    "ebit", "interest_expense", "capex",
)
REPORTED_RATIO_FIELDS = ("gross_npa_pct", "net_npa_pct", "capital_adequacy_pct")
NUMERIC_FIELDS = LEGACY_NUMERIC_FIELDS + ADVANCED_NUMERIC_FIELDS + REPORTED_RATIO_FIELDS
RATIO_FIELDS = (
    "revenue_growth_pct", "net_profit_margin_pct",
    "debt_to_equity", "operating_cash_flow_to_profit",
)
ADVANCED_RATIO_FIELDS = (
    "roa_pct", "cash_accruals_pct", "free_cash_flow", "current_ratio",
    "interest_coverage", "eps_surprise_absolute", "eps_surprise_pct",
)
ENTITY_TYPES = ("UNKNOWN", "NON_FINANCIAL", "BANK", "NBFC", "INSURANCE")
EXPECTATION_QUALIFIERS = (
    "reporting_basis", "consensus_reporting_basis",
    "earnings_definition", "consensus_earnings_definition",
    "split_basis", "consensus_split_basis",
)
METRIC_DEFINITIONS = {
    "revenue_growth_pct": "(revenue / revenue_previous - 1) * 100; positive prior revenue; "
                          "comparisons_comparable confirms like-for-like reporting windows.",
    "net_profit_margin_pct": "net_profit / revenue * 100; positive revenue; not annualized.",
    "debt_to_equity": "total_debt / total_equity; positive equity; not for financial entities.",
    "operating_cash_flow_to_profit": "CFO / net_profit; positive profit; matching financial/CFO "
                                     "windows. Legacy undated values are UNVERIFIED.",
    "roa_pct": "net_profit / ((assets_begin + assets_end) / 2) * 100; positive average assets; "
               "NON_FINANCIAL, period_start required. Assets bracket that period; not annualized.",
    "cash_accruals_pct": "(net_profit - CFO) / average_assets * 100; NON_FINANCIAL, positive "
                         "average assets, matching windows. Simplified cash-based proxy, not "
                         "Sloan's exact accrual construction or a universal quality threshold. "
                         "Positive accruals alone imply neither fraud nor poor quality. "
                         "No Dechow-Dichev future-cash-flow regression is used.",
    "free_cash_flow": "CFO - capex; NON_FINANCIAL, matching windows; capex is a nonnegative "
                      "cash outflow in the same window. Descriptive, not firm valuation.",
    "current_ratio": "current_assets / current_liabilities; NON_FINANCIAL, positive liabilities; "
                     "both balances at period_end. No universal pass/fail threshold.",
    "interest_coverage": "EBIT / interest_expense; NON_FINANCIAL, positive interest expense; "
                         "both for the financial period. Not a solvency guarantee.",
    "eps_surprise_absolute": "actual_eps - consensus_eps in the stated currency per share; "
                             "same BASIC/DILUTED basis and period, strictly pre-release consensus. "
                             "Verified comparability additionally requires matching reporting_basis "
                             "(snapshot basis), REPORTED/ADJUSTED earnings_definition, and split_basis "
                             "for actual and consensus; absent qualifiers mean UNVERIFIED.",
    "eps_surprise_pct": "(actual_eps - consensus_eps) / abs(consensus_eps) * 100 only when "
                        "abs(consensus_eps) >= min_abs_consensus_eps (default 0.01). "
                        "This configurable numerical policy is in EPS currency units, not a paper "
                        "threshold. Requires the same verified qualifiers as absolute surprise. "
                        "Not standardized unexpected earnings (no historical variance), not an "
                        "event-drift forecast; near-zero consensus can magnify this percentage.",
    **{name: "User-reported percentage (0..100), BANK/NBFC only; never recomputed. "
              "Definitions and regulatory scope must be checked against the filing. "
              "Missing is unknown, not a failed prudential test."
       for name in REPORTED_RATIO_FIELDS},
}
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9&-]{0,19}", re.ASCII)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS fundamental_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    received_at TEXT NOT NULL,
    published_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
)
"""


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
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("now must be timezone-aware.")
        return _timestamp(value.isoformat(), "now")
    return _timestamp(value, "now")


def _iso(value):
    return value.isoformat(timespec="microseconds")


def _symbol(value):
    if not isinstance(value, str):
        raise ValueError("symbol must be an NSE trading symbol.")
    normalized = value.strip().upper()
    if not _SYMBOL.fullmatch(normalized):
        raise ValueError("symbol must be 1-20 NSE symbol characters: A-Z, 0-9, & or -.")
    return normalized


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string.")
    return value.strip()


def _number(value, field, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number, not a boolean.")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or (nonnegative and value < 0):
        raise ValueError(f"{field} must be finite" + (" and nonnegative." if nonnegative else "."))
    return value


def _url(value, field):
    url = _text(value, field)
    try:
        parts = urlsplit(url)
        if (
            parts.scheme not in ("http", "https") or not parts.hostname
            or parts.username is not None or parts.password is not None
            or any(char.isspace() or ord(char) < 32 for char in url)
            or "\\" in url
        ):
            raise ValueError("Invalid URL")
        parts.port
    except ValueError as exc:
        raise ValueError(f"{field} must be an HTTP(S) URL without credentials.") from exc
    return url


def _date(value, field):
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Invalid date")
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD).") from exc


def _expectation(value, snapshot, published):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("earnings_expectation must be an object.")
    result = {field: _number(value.get(field), field)
              for field in ("actual_eps", "consensus_eps")}
    for field in ("eps_basis", "consensus_eps_basis"):
        if value.get(field) not in ("BASIC", "DILUTED"):
            raise ValueError(f"{field} must be BASIC or DILUTED.")
        result[field] = value[field]
    if result["eps_basis"] != result["consensus_eps_basis"]:
        raise ValueError("Actual and consensus EPS bases must match.")
    result["currency"] = _text(value.get("currency"), "currency")
    threshold = _number(value.get("min_abs_consensus_eps", 0.01), "min_abs_consensus_eps")
    if threshold <= 0:
        raise ValueError("min_abs_consensus_eps must be strictly positive.")
    result["min_abs_consensus_eps"] = threshold
    for actual_field, consensus_field, choices in (
        ("reporting_basis", "consensus_reporting_basis", ("consolidated", "standalone")),
        ("earnings_definition", "consensus_earnings_definition", ("REPORTED", "ADJUSTED")),
        ("split_basis", "consensus_split_basis", None),
    ):
        for field in (actual_field, consensus_field):
            if field not in value:
                continue
            normalized = _text(value[field], field)
            if choices is not None and normalized not in choices:
                raise ValueError(f"{field} must be one of {', '.join(choices)}.")
            if actual_field == "reporting_basis" and normalized != snapshot["reporting_basis"]:
                raise ValueError(f"{field} must match snapshot reporting_basis.")
            result[field] = normalized
        if (actual_field in result and consensus_field in result
                and result[actual_field] != result[consensus_field]):
            raise ValueError(f"{actual_field} and {consensus_field} must match.")
    for field in ("period_start", "period_end"):
        _date(value.get(field), "earnings_expectation." + field)
        if value[field] != snapshot.get(field):
            raise ValueError("EPS expectation period must match the complete snapshot window.")
        result[field] = value[field]
    result["consensus_source_url"] = _url(value.get("consensus_source_url"), "consensus_source_url")
    consensus = _timestamp(value.get("consensus_as_of"), "consensus_as_of")
    announced = _timestamp(value.get("announced_at"), "announced_at")
    if not consensus < announced <= published:
        raise ValueError("Require consensus_as_of < announced_at <= published_at (and receipt).")
    result.update(consensus_as_of=_iso(consensus), announced_at=_iso(announced))
    return result


def _validate(payload, received_at):
    if not isinstance(payload, dict):
        raise ValueError("Snapshot must be a JSON object.")
    result = {"symbol": _symbol(payload.get("symbol")),
              "source_url": _url(payload.get("source_url"), "source_url")}
    published = _timestamp(payload.get("published_at"), "published_at")
    if published > received_at:
        raise ValueError("published_at cannot be in the future.")
    result["published_at"] = _iso(published)
    period = payload.get("period_end")
    period_date = _date(period, "period_end")
    if period_date > received_at.date():
        raise ValueError("period_end cannot be in the future.")
    if period_date > published.date():
        raise ValueError("period_end cannot be later than the publication date (UTC).")
    result["period_end"] = period
    entity = payload.get("entity_type", "UNKNOWN")
    if entity not in ENTITY_TYPES:
        raise ValueError("entity_type must be UNKNOWN, NON_FINANCIAL, BANK, NBFC or INSURANCE.")
    result["entity_type"] = entity
    comparable = payload.get("comparisons_comparable", False)
    if not isinstance(comparable, bool):
        raise ValueError("comparisons_comparable must be a boolean.")
    result["comparisons_comparable"] = comparable
    for field in ("period_start", "cash_flow_period_start", "cash_flow_period_end"):
        value = payload.get(field)
        if value is not None and _date(value, field) > published.date():
            raise ValueError(f"{field} cannot exceed publication's UTC date.")
        result[field] = value
    if result["period_start"] is not None and result["period_start"] > period:
        raise ValueError("period_start cannot exceed period_end.")
    cf_start, cf_end = result["cash_flow_period_start"], result["cash_flow_period_end"]
    if (cf_start is None) != (cf_end is None):
        raise ValueError("Supply both cash_flow_period_start and cash_flow_period_end, or neither.")
    if cf_start is not None and cf_start > cf_end:
        raise ValueError("cash_flow_period_start cannot exceed cash_flow_period_end.")
    result["amount_unit"] = _text(payload.get("amount_unit"), "amount_unit")
    basis = payload.get("reporting_basis")
    if basis not in ("consolidated", "standalone"):
        raise ValueError("reporting_basis must be consolidated or standalone.")
    result["reporting_basis"] = basis
    for field in NUMERIC_FIELDS:
        value = payload.get(field)
        result[field] = None if value is None else _number(
            value, field, field in (
                "revenue", "revenue_previous", "total_debt", "assets_begin", "assets_end",
                "current_assets", "current_liabilities", "interest_expense", "capex",
            ) + REPORTED_RATIO_FIELDS
        )
        if field in ("gross_npa_pct", "net_npa_pct") and value is not None and value > 100:
            raise ValueError(f"{field} must be between 0 and 100.")
    result["earnings_expectation"] = _expectation(payload.get("earnings_expectation"), result, published)
    reviewed = payload.get("events_reviewed_at")
    if reviewed is not None:
        reviewed = _timestamp(reviewed, "events_reviewed_at")
        if reviewed > received_at:
            raise ValueError("events_reviewed_at cannot be in the future.")
    result["events_reviewed_at"] = _iso(reviewed) if reviewed is not None else None
    events = payload.get("events")
    if "events" in payload and not isinstance(events, list):
        raise ValueError("events must be a list; use [] for an explicitly empty list.")
    result["events"] = None
    if events is not None:
        result["events"] = []
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("Every event must be an object.")
            title = _text(event.get("title"), "event.title")
            at = _timestamp(event.get("at"), "event.at")
            importance = event.get("importance")
            if importance not in ("HIGH", "NORMAL"):
                raise ValueError("event.importance must be HIGH or NORMAL.")
            result["events"].append(
                {"title": title, "at": _iso(at), "importance": importance}
            )
    return result


def save_snapshot(payload, db_path=DEFAULT_DB_PATH, now=None):
    """Validate and append a snapshot, returning its integer ID.

    Validation precedes all writes. Receipt time is UTC; old imports remain
    available for point-in-time queries. Explicit null financials are permitted.
    Reporting period end must not exceed the publication date normalized to UTC.
    """
    received_at = _now(now)
    snapshot = _validate(payload, received_at)
    serialized = json.dumps(snapshot, allow_nan=False)
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(path))) as connection:
        with connection:
            connection.execute(_SCHEMA)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS fundamental_snapshot_lookup "
                "ON fundamental_snapshots(symbol, received_at, id)"
            )
            cursor = connection.execute(
                "INSERT INTO fundamental_snapshots "
                "(symbol, received_at, published_at, payload_json) VALUES (?, ?, ?, ?)",
                (snapshot["symbol"], _iso(received_at), snapshot["published_at"], serialized),
            )
            return cursor.lastrowid


def _financial_details(snapshot, warnings, evidence_id):
    metrics = {field: snapshot.get(field) for field in NUMERIC_FIELDS}
    metrics.update(dict.fromkeys(RATIO_FIELDS + ADVANCED_RATIO_FIELDS))
    eligibility = {
        name: {"status": "UNAVAILABLE", "reason": "Required inputs not supplied."}
        for name in METRIC_DEFINITIONS
    }
    findings = []
    entity = snapshot.get("entity_type", "UNKNOWN")
    financial = entity in ("BANK", "NBFC", "INSURANCE")
    nonfinancial = entity == "NON_FINANCIAL"
    period_start = snapshot.get("period_start")
    cf_start, cf_end = snapshot.get("cash_flow_period_start"), snapshot.get("cash_flow_period_end")
    aligned = (
        period_start is not None and cf_start == period_start
        and cf_end == snapshot.get("period_end")
    )
    legacy_undated = period_start is None and cf_start is None and cf_end is None
    if entity == "UNKNOWN":
        warnings.append("entity_type UNKNOWN: sector eligibility is unconfirmed. Advanced "
                        "non-financial metrics are unavailable; legacy leverage/CFO ratios "
                        "are descriptive UNVERIFIED values, not sector conclusions.")
    elif financial:
        warnings.append(f"{entity}: generic debt/equity, current, accrual, CFO, ROA and interest "
                        "coverage metrics are suppressed. Use sector-specific reported "
                        "definitions; absent prudential ratios are unknown, not a fail.")

    def unavailable(name, reason):
        metrics[name] = None
        eligibility[name] = {"status": "UNAVAILABLE", "reason": reason}

    def calculate(name, operation, status="AVAILABLE", reason="Required inputs supplied."):
        try:
            value = operation()
            if not math.isfinite(value):
                raise OverflowError
        except (OverflowError, ZeroDivisionError):
            unavailable(name, "Calculation exceeds finite numeric range or has zero denominator.")
        else:
            metrics[name] = value
            eligibility[name] = {"status": status, "reason": reason}
            if status == "UNVERIFIED":
                warnings.append(f"{name} UNVERIFIED: {reason}")

    def finding(text, basis, role, research_ids):
        findings.append({
            "finding": text, "basis": basis, "role": role,
            "research_ids": research_ids, "evidence_id": evidence_id,
        })

    ratios = (
        ("revenue_growth_pct", "revenue", "revenue_previous", True),
        ("net_profit_margin_pct", "net_profit", "revenue", False),
        ("debt_to_equity", "total_debt", "total_equity", False),
        ("operating_cash_flow_to_profit", "operating_cash_flow", "net_profit", False),
    )
    for name, numerator, denominator, growth in ratios:
        top, bottom = metrics[numerator], metrics[denominator]
        if financial and name in ("debt_to_equity", "operating_cash_flow_to_profit"):
            unavailable(name, f"Generic ratio is not eligible for {entity}.")
            continue
        if top is None or bottom is None or bottom <= 0:
            unavailable(name, f"Requires {numerator} and positive {denominator}.")
            warnings.append(f"{name} unavailable: {eligibility[name]['reason']}")
            continue
        status, reason = "AVAILABLE", "Required inputs supplied; see metric definition."
        if name == "revenue_growth_pct" and not snapshot.get("comparisons_comparable", False):
            status, reason = "UNVERIFIED", "Prior-period comparability was not confirmed."
        if name == "debt_to_equity" and entity == "UNKNOWN":
            status, reason = "UNVERIFIED", "Entity type UNKNOWN; sector suitability not confirmed."
        if name == "operating_cash_flow_to_profit":
            if not aligned and not legacy_undated:
                unavailable(name, "CFO window must exactly match the financial period.")
                continue
            if not aligned or entity == "UNKNOWN":
                status = "UNVERIFIED"
                reason = ("CFO/financial window alignment is unverified for legacy undated inputs."
                          if not aligned else "Entity type UNKNOWN; sector suitability not confirmed.")
        calculate(name, lambda: ((top / bottom - 1) * 100 if growth else
                                top / bottom * (100 if name.endswith("_pct") else 1)),
                  status, reason)

    for name in REPORTED_RATIO_FIELDS:
        if entity not in ("BANK", "NBFC"):
            unavailable(name, f"Reported BANK/NBFC ratio is not applicable to {entity}.")
        elif snapshot.get(name) is None:
            unavailable(name, f"{entity}: reported value missing; unknown, not a failed test.")
        else:
            eligibility[name] = {"status": "REPORTED", "reason": "User-reported only; not recomputed."}

    average_assets = None
    if metrics["assets_begin"] is not None and metrics["assets_end"] is not None:
        average_assets = metrics["assets_begin"] / 2 + metrics["assets_end"] / 2
    profit, cfo = metrics["net_profit"], metrics["operating_cash_flow"]
    advanced = (
        ("roa_pct", ("net_profit", "assets_begin", "assets_end"),
         lambda: profit / average_assets * 100),
        ("cash_accruals_pct", ("net_profit", "operating_cash_flow", "assets_begin", "assets_end"),
         lambda: (profit - cfo) / average_assets * 100),
        ("free_cash_flow", ("operating_cash_flow", "capex"),
         lambda: cfo - metrics["capex"]),
        ("current_ratio", ("current_assets", "current_liabilities"),
         lambda: metrics["current_assets"] / metrics["current_liabilities"]),
        ("interest_coverage", ("ebit", "interest_expense"),
         lambda: metrics["ebit"] / metrics["interest_expense"]),
    )
    for name, inputs, operation in advanced:
        missing = [field for field in inputs if metrics[field] is None]
        if not nonfinancial:
            unavailable(name, f"Requires NON_FINANCIAL; entity_type is {entity}.")
        elif missing:
            unavailable(name, "Missing inputs: " + ", ".join(missing))
        elif name in ("cash_accruals_pct", "free_cash_flow") and not aligned:
            unavailable(name, "CFO window must exactly match the complete financial period.")
        elif name in ("roa_pct", "cash_accruals_pct") and (
                period_start is None or average_assets is None or average_assets <= 0):
            unavailable(name, "Requires period_start and positive average assets bracketing the period.")
        elif name == "current_ratio" and metrics["current_liabilities"] <= 0:
            unavailable(name, "Requires positive current_liabilities.")
        elif name == "interest_coverage" and metrics["interest_expense"] <= 0:
            unavailable(name, "Requires positive interest_expense.")
        else:
            calculate(name, operation)

    expectation = snapshot.get("earnings_expectation")
    if expectation is not None:
        # Recheck derived evidence on read as well, including legacy imported JSON.
        try:
            expectation = _expectation(
                expectation, snapshot, _timestamp(snapshot["published_at"], "published_at")
            )
        except ValueError as exc:
            for name in ("eps_surprise_absolute", "eps_surprise_pct"):
                unavailable(name, f"Ineligible earnings expectation: {exc}")
        else:
            actual, consensus = expectation["actual_eps"], expectation["consensus_eps"]
            missing_qualifiers = [field for field in EXPECTATION_QUALIFIERS if field not in expectation]
            status = "UNVERIFIED" if missing_qualifiers else "AVAILABLE"
            reason = (
                "EPS comparability qualifiers missing: " + ", ".join(missing_qualifiers)
                if missing_qualifiers else "Matching period, EPS/reporting/earnings/split bases "
                "and pre-release consensus provenance supplied."
            )
            threshold = expectation["min_abs_consensus_eps"]
            calculate("eps_surprise_absolute", lambda: actual - consensus, status, reason)
            if abs(consensus) >= threshold:
                calculate("eps_surprise_pct", lambda: (actual - consensus) / abs(consensus) * 100,
                          status, reason)
            else:
                unavailable("eps_surprise_pct", f"Absolute consensus EPS below configured minimum "
                            f"{threshold} {expectation['currency']} per share; numerical policy, "
                            "not a research threshold.")
            if metrics["eps_surprise_absolute"] is not None:
                finding(
                    "Reported EPS compared with the documented pre-release consensus.",
                    {"actual_eps": actual, "consensus_eps": consensus,
                     "surprise_absolute": metrics["eps_surprise_absolute"],
                     "currency": expectation["currency"], "eps_basis": expectation["eps_basis"],
                     "comparability_status": status, "comparability_reason": reason,
                     "min_abs_consensus_eps": threshold,
                     **{field: expectation.get(field) for field in EXPECTATION_QUALIFIERS},
                     "period_start": expectation["period_start"], "period_end": expectation["period_end"],
                     "consensus_source_url": expectation["consensus_source_url"],
                     "consensus_as_of": expectation["consensus_as_of"],
                     "announced_at": expectation["announced_at"]},
                    "DESCRIPTIVE_EVENT_CONTEXT", ["bernard-thomas-1989"],
                )
    if nonfinancial and aligned and profit is not None and cfo is not None and profit > 0 and cfo < 0:
        finding(
            "Positive reported profit is not accompanied by positive operating cash flow.",
            {"net_profit": profit, "operating_cash_flow": cfo, "period_start": period_start,
             "period_end": snapshot["period_end"], "amount_unit": snapshot["amount_unit"]},
            "ACCOUNTING_RISK_CONTEXT", ["sloan-1996", "piotroski-2000"],
        )
    if nonfinancial and metrics["total_equity"] is not None and metrics["total_equity"] <= 0:
        finding("Nonpositive reported equity makes conventional debt/equity interpretation invalid.",
                {"total_equity": metrics["total_equity"], "amount_unit": snapshot["amount_unit"]},
                "BALANCE_SHEET_RISK_CONTEXT", [])
    if metrics["cash_accruals_pct"] is not None:
        finding("Cash-based accrual proxy is available; magnitude needs company and sector context. "
                "A positive proxy alone does not establish fraud or poor earnings quality. "
                "No Dechow-Dichev future-cash-flow regression is used.",
                {"cash_accruals_pct": metrics["cash_accruals_pct"], "average_assets": average_assets,
                 "period_start": period_start, "period_end": snapshot["period_end"]},
                "DESCRIPTIVE_ACCOUNTING_CONTEXT", ["sloan-1996", "dechow-dichev-2002"])
    return {
        "metrics": metrics, "metric_eligibility": eligibility,
        "financial_assessment": findings, "cash_flow_periods_aligned": aligned,
    }


def load_context(symbol, now=None, db_path=DEFAULT_DB_PATH, max_age_days=120,
                 event_review_hours=24, blackout_before_minutes=60,
                 blackout_after_minutes=30):
    """Return JSON-safe context, never a buy/sell signal or fair value.

    Latest receipt (ID breaks ties) known at ``now`` wins; future receipts and
    publications are excluded. Financials are stale if publication OR period end
    exceeds max_age_days. Event review is independently assessed. Age thresholds
    are inclusive; HIGH-event blackout endpoints are included.
    """
    symbol, current = _symbol(symbol), _now(now)
    durations = {}
    for name, value, unit in (
        ("max_age_days", max_age_days, "days"),
        ("event_review_hours", event_review_hours, "hours"),
        ("blackout_before_minutes", blackout_before_minutes, "minutes"),
        ("blackout_after_minutes", blackout_after_minutes, "minutes"),
    ):
        _number(value, name, True)
        try:
            durations[name] = timedelta(**{unit: value})
        except OverflowError as exc:
            raise ValueError(f"{name} is too large.") from exc
    context = {
        "method_version": METHOD_VERSION, "evidence_id": None,
        "entity_type": "UNKNOWN", "comparisons_comparable": False,
        "period_start": None, "cash_flow_period_start": None, "cash_flow_period_end": None,
        "cash_flow_periods_aligned": False, "earnings_expectation": None,
        "financial_assessment": [], "metric_definitions": dict(METRIC_DEFINITIONS),
        "metric_eligibility": {
            name: {"status": "UNAVAILABLE", "reason": "No snapshot known at this time."}
            for name in METRIC_DEFINITIONS
        },
        "symbol": symbol, "as_of": _iso(current), "status": "MISSING",
        "source_url": None, "published_at": None, "period_end": None,
        "received_at": None, "events_reviewed_at": None,
        "amount_unit": None, "reporting_basis": None,
        "snapshot_id": None, "snapshot": None,
        "metrics": dict.fromkeys(NUMERIC_FIELDS + RATIO_FIELDS + ADVANCED_RATIO_FIELDS),
        "missing_fields": list(NUMERIC_FIELDS),
        "events": None, "event_status": "MISSING",
        "warnings": [
            "Context only: not intraday fair value, a buy/sell signal, or an automated verification.",
            "All amounts and comparatives must use the same unit and reporting basis; "
            "prior revenue must cover a comparable period.",
            "Debt/equity is not comparable across banks/financials and other sectors.",
            "Research links motivate accounting-quality and earnings-event context only: "
            "not Sloan replication, Piotroski F-score, standardized earnings surprise, "
            "event-drift forecast or evidence of NSE intraday profitability.",
            "Flow metrics are not annualized. Average assets assumes beginning/end balances "
            "bracket the stated financial period; current balances are at period_end. "
            "Capex must cover the same cash-flow window. All are manual assertions, not verified facts.",
        ],
        "blockers": [],
    }
    path = Path(db_path)
    row = None
    if path.exists():
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fundamental_snapshots'"
            ).fetchone()
            if table:
                row = connection.execute(
                    "SELECT id, received_at, payload_json FROM fundamental_snapshots "
                    "WHERE symbol=? AND received_at<=? AND published_at<=? "
                    "ORDER BY received_at DESC, id DESC LIMIT 1",
                    (symbol, _iso(current), _iso(current)),
                ).fetchone()
    if row is None:
        context["blockers"] = [
            "FINANCIALS_MISSING: no snapshot known at this time.",
            "EVENTS_MISSING: no event list or manual review known at this time.",
        ]
        return context

    snapshot = json.loads(row[2])
    evidence_id = f"fundamental:{row[0]}"
    context.update(
        snapshot_id=row[0], received_at=row[1], snapshot=snapshot,
        evidence_id=evidence_id,
        entity_type=snapshot.get("entity_type", "UNKNOWN"),
        comparisons_comparable=snapshot.get("comparisons_comparable", False),
        missing_fields=[field for field in NUMERIC_FIELDS if snapshot.get(field) is None],
    )
    context.update(_financial_details(snapshot, context["warnings"], evidence_id))
    for field in (
        "source_url", "published_at", "period_end", "events_reviewed_at",
        "amount_unit", "reporting_basis", "events",
        "period_start", "cash_flow_period_start", "cash_flow_period_end", "earnings_expectation",
    ):
        context[field] = snapshot.get(field)
    has_earnings = context["metric_eligibility"]["eps_surprise_absolute"]["status"] in ("AVAILABLE", "UNVERIFIED")
    if len(context["missing_fields"]) == len(NUMERIC_FIELDS) and not has_earnings:
        context["blockers"].append("FINANCIALS_MISSING: snapshot contains no financial amounts.")
    else:
        publication_age = current - _timestamp(snapshot["published_at"], "published_at")
        period_age = current.date() - date.fromisoformat(snapshot["period_end"])
        if max(publication_age, period_age) > durations["max_age_days"]:
            context["status"] = "STALE"
            context["blockers"].append("FINANCIALS_STALE: publication or reporting period is too old.")
        else:
            context["status"] = "AVAILABLE"
    if context["missing_fields"]:
        context["warnings"].append("Missing financial amounts: " + ", ".join(context["missing_fields"]))

    reviewed = snapshot.get("events_reviewed_at")
    events = snapshot.get("events")
    if events is None:
        context["blockers"].append("EVENTS_MISSING: no explicit event list supplied.")
    elif reviewed is None:
        context["event_status"] = "UNREVIEWED"
        context["blockers"].append("EVENTS_UNREVIEWED: event list has no manual review timestamp.")
    else:
        review_time = _timestamp(reviewed, "events_reviewed_at")
        if review_time > current:
            context["event_status"] = "UNREVIEWED"
            context["blockers"].append("EVENTS_UNREVIEWED: review was not known at this time.")
        elif current - review_time > durations["event_review_hours"]:
            context["event_status"] = "STALE"
            context["blockers"].append("EVENTS_STALE: manual event review is too old.")
        else:
            context["event_status"] = "REVIEWED"
        context["warnings"].append(
            "Event list is a user-supplied manual review, not automated verification "
            "or assurance that no other events exist."
        )
    for event in events or []:
        at = _timestamp(event["at"], "event.at")
        # Compare differences instead of adding windows near datetime limits.
        if (event["importance"] == "HIGH"
                and -durations["blackout_before_minutes"] <= current - at
                <= durations["blackout_after_minutes"]):
            context["blockers"].append(
                f"EVENT_BLACKOUT: {event['title']} at {event['at']} (inclusive HIGH-impact window)."
            )
    return context


def render_fundamentals_panel(symbols=None, settings=None):
    """Render using intraday settings; absent settings retain load_context defaults.

    Importing this module never imports Streamlit.
    """
    import streamlit as st

    st.subheader("Fundamental & event context")
    st.caption("Offline manual imports only. Not intraday fair value or a buy/sell recommendation.")
    choices = sorted({_symbol(item) for item in (symbols or [])})
    selected = st.selectbox(
        "Watchlist symbol", ["Type a symbol"] + choices, key="fundamentals_selection"
    )
    typed = st.text_input("NSE trading symbol (overrides selection)", key="fundamentals_symbol")
    symbol = typed.strip() or (selected if selected != "Type a symbol" else "")
    with st.expander("JSON schema and import template"):
        st.write(
            "Required: symbol, source_url (HTTP/S, no credentials), published_at "
            "(timezone-aware ISO), period_end (YYYY-MM-DD, no later than publication's "
            "UTC date), amount_unit, reporting_basis "
            "(consolidated/standalone). Optional amounts may be null. All amounts, including "
            "prior comparatives, must share the unit, reporting basis and comparable period. "
            "Optional events contain title, at (timezone-aware ISO), importance (HIGH/NORMAL). "
            "Only set events_reviewed_at after manually reviewing the explicit events list; "
            "[] means a manually reviewed empty list, not automated verification."
        )
        st.write(
            "Optional entity_type: UNKNOWN (default), NON_FINANCIAL, BANK, NBFC, INSURANCE. "
            "Unknown is not assumed non-financial. comparisons_comparable defaults to false; "
            "confirm it only for like-for-like prior revenue. period_start enables a complete "
            "financial window. cash_flow_period_start/end must both be supplied and match it "
            "for accruals, free cash flow and verified CFO/profit. Undated legacy CFO/profit "
            "is descriptive UNVERIFIED only."
        )
        st.write(
            "NON_FINANCIAL inputs: assets_begin/end (bracketing financial window), current_assets/"
            "current_liabilities (at period_end), ebit, interest_expense (financial window), "
            "capex (positive cash outflow in the matching CFO window). No annualization. "
            "BANK/NBFC reported percentages: gross_npa_pct, net_npa_pct, capital_adequacy_pct "
            "(0..100). These are not recomputed, regulatory adequacy tests or insurance ratios. "
            "Missing inputs are unknown, not a failed score."
        )
        st.write(
            "Optional earnings_expectation object requires actual_eps, consensus_eps, matching "
            "eps_basis/consensus_eps_basis (BASIC/DILUTED), one shared currency (e.g. INR, per "
            "share, not amount_unit), period_start/end matching the snapshot, consensus_source_url, "
            "consensus_as_of and announced_at. Require consensus_as_of < announced_at <= "
            "published_at <= receipt. Signed/zero EPS is allowed. min_abs_consensus_eps defaults "
            "to 0.01 and must be finite and positive; percentage surprise requires absolute consensus "
            "at least this value. This is a configurable numerical policy in EPS currency units, "
            "not a paper threshold. Absolute surprise is retained. This is not standardized "
            "unexpected earnings or a trading forecast."
        )
        st.write(
            "Required for VERIFIED EPS comparability: reporting_basis and consensus_reporting_basis "
            "must both match the snapshot; earnings_definition and consensus_earnings_definition "
            "must both be REPORTED or both ADJUSTED; split_basis and consensus_split_basis must "
            "be matching nonempty descriptions of the same share/split adjustment reference. "
            "Missing qualifiers retain descriptive UNVERIFIED surprises; supplied mismatches "
            "are rejected. Matching labels remain manual assertions, not external verification."
        )
        template = {
            "symbol": symbol or "RELIANCE",
            "source_url": "https://example.com/REPLACE-WITH-ACTUAL-FILING",
            "published_at": _iso(datetime.now(timezone.utc)),
            "period_end": datetime.now(timezone.utc).date().isoformat(),
            "amount_unit": "INR crore", "reporting_basis": "consolidated",
            "entity_type": "UNKNOWN", "comparisons_comparable": False,
            "period_start": None, "cash_flow_period_start": None, "cash_flow_period_end": None,
            **dict.fromkeys(NUMERIC_FIELDS),
            "earnings_expectation": None,
            "events_reviewed_at": None, "events": [],
        }
        st.caption(
            "Template dates use current UTC for format only. Replace them and the source URL "
            "with actual filing details. No sample financial data is saved automatically."
        )
        st.download_button(
            "Download JSON template", json.dumps(template, indent=2),
            file_name="fundamentals_template.json", mime="application/json",
            key="fundamentals_template",
        )
        st.caption("earnings_expectation object shape (replace every null with sourced data; "
                   "otherwise leave the entire object null):")
        st.json({
            "actual_eps": None, "consensus_eps": None, "eps_basis": "DILUTED",
            "consensus_eps_basis": "DILUTED", "currency": "INR",
            "min_abs_consensus_eps": 0.01,
            "reporting_basis": "consolidated", "consensus_reporting_basis": "consolidated",
            "earnings_definition": "REPORTED", "consensus_earnings_definition": "REPORTED",
            "split_basis": None, "consensus_split_basis": None,
            "period_start": None, "period_end": None,
            "consensus_source_url": "https://example.com/REPLACE-WITH-CONSENSUS-SOURCE",
            "consensus_as_of": None, "announced_at": None,
        })
    with st.form("fundamentals_import"):
        raw = st.text_area("Paste snapshot JSON", key="fundamentals_payload")
        submitted = st.form_submit_button("Validate and save snapshot")
    if submitted:
        try:
            payload = json.loads(raw)
            snapshot_id = save_snapshot(payload)
        except (ValueError, sqlite3.Error, OSError) as exc:
            st.error(f"Snapshot was not saved: {exc}")
        else:
            st.success(f"Saved snapshot #{snapshot_id} for {payload['symbol']}.")
            if not symbol:
                symbol = payload["symbol"]
    if not symbol:
        st.info("Select or enter an NSE symbol to view its context.")
        return
    try:
        context_settings = {
            argument: settings[key]
            for key, argument in (
                ("fundamental_max_age_days", "max_age_days"),
                ("event_review_hours", "event_review_hours"),
                ("event_blackout_before_minutes", "blackout_before_minutes"),
                ("event_blackout_after_minutes", "blackout_after_minutes"),
            )
            if settings is not None and key in settings
        }
        context = load_context(symbol, **context_settings)
    except (ValueError, sqlite3.Error, OSError) as exc:
        st.error(f"Could not load context: {exc}")
        return
    st.write(f"Financials: {context['status']} | Event review: {context['event_status']}")
    for blocker in context["blockers"]:
        st.warning(blocker)
    for warning in context["warnings"]:
        st.caption(warning)
    st.write("Amounts:", context["amount_unit"], "| Reporting basis:", context["reporting_basis"])
    st.write("Entity:", context["entity_type"], "| Method:", context["method_version"],
             "| Evidence:", context["evidence_id"])
    st.table([
        {"Metric": name,
         "Value": "Missing / undefined" if context["metrics"][name] is None else str(context["metrics"][name]),
         "Eligibility": context["metric_eligibility"].get(name, {}).get("status", "REPORTED INPUT")}
        for name in LEGACY_NUMERIC_FIELDS + RATIO_FIELDS
    ])
    with st.expander("Advanced metrics, sector eligibility and assumptions"):
        st.table([
            {"Metric": name,
             "Value": "Missing / undefined" if context["metrics"][name] is None else str(context["metrics"][name]),
             "Status": details["status"], "Reason": details["reason"]}
            for name, details in context["metric_eligibility"].items()
        ])
        st.json(context["metric_definitions"])
        st.json(context["financial_assessment"])
    with st.expander("Full snapshot and provenance"):
        st.json(context)
