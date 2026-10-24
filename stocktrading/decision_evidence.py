"""Compact input register and proposal-to-rule trace, not model chain-of-thought."""

import math

MAX_INSTITUTIONAL_ROWS_PER_SECTION = 10


def evidence_packet(indicators):
    symbol = indicators.get("symbol", "UNKNOWN")
    technical = indicators.get("intraday", {})
    stamp = technical.get("completed_bar_end", indicators.get("timestamp", "unknown"))
    rows = []
    for key in ("setup", "vwap", "atr", "adx", "relative_volume", "opening_range_high", "opening_range_low"):
        rows.append({
            "id": f"technical:{symbol}:{stamp}:{key}", "part": "Technical",
            "observation": key, "value": technical.get(key),
            "source": technical.get("source", "Candle input"), "as_of": stamp,
            "role": "Setup input; not independently validated profitability",
        })
    for key in ("rsi", "ema9", "ema21", "macd_hist", "bb_width"):
        rows.append({
            "id": f"indicator:{symbol}:{stamp}:{key}", "part": "Indicators",
            "observation": key, "value": indicators.get(key), "source": "Local candle calculation",
            "as_of": stamp, "role": "Momentum/trend/context; correlated features are not extra votes",
        })
    fundamental = indicators.get("fundamentals", {})
    fid = fundamental.get("snapshot_id")
    rows.append({
        "id": f"fundamental:{fid if fid is not None else symbol + ':missing'}",
        "part": "Fundamentals", "observation": "Financial/event snapshot",
        "value": {"financial_status": fundamental.get("status", "MISSING"),
                  "event_status": fundamental.get("event_status", "MISSING"),
                  "entity_type": fundamental.get("entity_type", "UNKNOWN"),
                  "metrics": fundamental.get("metrics", {}),
                  "metric_eligibility": fundamental.get("metric_eligibility", {}),
                  "financial_assessment": fundamental.get("financial_assessment", []),
                  "blockers": fundamental.get("blockers", [])},
        "source": fundamental.get("source_url"), "as_of": fundamental.get("published_at"),
        "role": "Financial context and manual event-risk gate; not an intraday valuation",
    })
    institutional = indicators.get("institutions", {})
    for section in ("market_flows", "ownership", "deals"):
        for record in institutional.get(section, {}).get("rows", [])[:MAX_INSTITUTIONAL_ROWS_PER_SECTION]:
            rows.append({
                "id": record["evidence_id"], "part": "Institutions", "observation": section,
                "value": record, "source": record.get("source_url"),
                "as_of": record.get("published_at"),
                "role": "Delayed public/manual context only; not a directional gate or live order identity",
            })
    if not any(row["part"] == "Institutions" for row in rows):
        rows.append({
            "id": f"institutional:{symbol}:missing", "part": "Institutions",
            "observation": "Disclosure coverage", "value": "MISSING", "source": None,
            "as_of": None, "role": "Unknown, not evidence of no institutional activity",
        })
    return rows


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def attach_decision_trace(result, indicators, proposal=None):
    result["decision_trace"] = {
        "technical_setup": indicators.get("intraday", {}).get("setup", "UNAVAILABLE"),
        "technical_reasons": indicators.get("intraday", {}).get("setup_reasons", []),
        "model_proposal": _json_safe(proposal) if proposal is not None else None,
        "final_signal": result.get("signal", "WAIT"),
        "rule_overrides": result.get("rule_violations", []),
        "input_evidence": evidence_packet(indicators),
        "model_cited_ids": result.get("evidence_refs", []),
        "interpretation": "The register lists supplied inputs, not proof the model used every input. "
                          "Citations are model-reported; rule overrides are deterministic. "
                          "Research papers justify design choices, not a forecast for this stock.",
    }
