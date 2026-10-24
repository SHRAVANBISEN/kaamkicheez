"""Run from the repository root: python -m unittest tests.test_fundamentals -v."""

import copy
import json
import sqlite3
import unittest
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from stocktrading import fundamentals as f


class FundamentalsTests(unittest.TestCase):
    def setUp(self):
        self.db = Path(__file__).resolve().parent / ("fundamentals_test_" + uuid.uuid4().hex + ".db")
        self.now = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)
        self.payload = {
            "symbol": " reliance ", "source_url": "https://www.nseindia.com/filing",
            "published_at": "2026-10-20T15:30:00+05:30",
            "period_end": "2026-09-30", "amount_unit": "INR crore",
            "reporting_basis": "consolidated",
            "revenue": 120, "revenue_previous": 100,
            "net_profit": 12, "net_profit_previous": 10,
            "operating_cash_flow": 18, "total_debt": 40, "total_equity": 80,
            "events_reviewed_at": self.now.isoformat(), "events": [],
        }

    def tearDown(self):
        for suffix in ("", "-journal", "-wal", "-shm"):
            path = Path(str(self.db) + suffix)
            if path.exists():
                path.unlink()

    def save(self, payload=None, now=None):
        return f.save_snapshot(
            self.payload if payload is None else payload, db_path=self.db,
            now=self.now if now is None else now,
        )

    def load(self, now=None, **kwargs):
        return f.load_context("reliance", db_path=self.db, now=self.now if now is None else now, **kwargs)

    def has_blocker(self, context, code):
        return any(item.startswith(code + ":") for item in context["blockers"])

    def test_persistence_normalization_ratios_and_provenance(self):
        original = copy.deepcopy(self.payload)
        snapshot_id = self.save()
        context = self.load()
        self.assertEqual(self.payload, original)
        self.assertEqual(context["status"], "AVAILABLE")
        self.assertEqual(context["symbol"], "RELIANCE")
        self.assertEqual(context["snapshot_id"], snapshot_id)
        self.assertEqual(context["snapshot"]["amount_unit"], "INR crore")
        self.assertEqual(context["published_at"], "2026-10-20T10:00:00.000000+00:00")
        self.assertEqual(context["received_at"], "2026-10-24T10:00:00.000000+00:00")
        self.assertAlmostEqual(context["metrics"]["revenue_growth_pct"], 20)
        self.assertEqual(context["metrics"]["net_profit_margin_pct"], 10)
        self.assertEqual(context["metrics"]["debt_to_equity"], 0.5)
        self.assertEqual(context["metrics"]["operating_cash_flow_to_profit"], 1.5)
        self.assertEqual(context["event_status"], "REVIEWED")
        self.assertEqual(context["blockers"], [])
        self.assertTrue(any("manual review" in warning for warning in context["warnings"]))
        json.dumps(context, allow_nan=False)

    def test_missing_does_not_create_database(self):
        context = self.load()
        self.assertFalse(self.db.exists())
        self.assertEqual(context["status"], "MISSING")
        self.assertIsNone(context["snapshot"])
        self.assertTrue(self.has_blocker(context, "FINANCIALS_MISSING"))
        self.assertTrue(self.has_blocker(context, "EVENTS_MISSING"))

    def test_append_and_point_in_time(self):
        first = self.save()
        self.payload["revenue"] = 240
        second = self.save(now=self.now + timedelta(days=1))
        self.assertGreater(second, first)
        self.assertEqual(self.load()["snapshot_id"], first)
        self.assertEqual(self.load(self.now + timedelta(days=1))["snapshot_id"], second)
        self.assertEqual(self.load(self.now - timedelta(microseconds=1))["status"], "MISSING")
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM fundamental_snapshots").fetchone()[0], 2)

    def test_same_receipt_latest_id_wins_and_symbols_are_isolated(self):
        self.save()
        self.payload["revenue"] = 321
        latest = self.save()
        self.assertEqual(self.load()["snapshot_id"], latest)
        self.assertEqual(f.load_context("TCS", now=self.now, db_path=self.db)["status"], "MISSING")

    def test_future_publication_excluded_even_in_legacy_row(self):
        first = self.save()
        second = self.save()
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:
                connection.execute(
                    "UPDATE fundamental_snapshots SET published_at=? WHERE id=?",
                    ((self.now + timedelta(days=1)).isoformat(), second),
                )
        self.assertEqual(self.load()["snapshot_id"], first)

    def test_missing_unreviewed_and_stale_events_distinct(self):
        for fields, expected, blocker in (
            ({"events": None, "events_reviewed_at": None}, "MISSING", "EVENTS_MISSING"),
            ({"events": []}, "UNREVIEWED", "EVENTS_UNREVIEWED"),
            ({"events": [], "events_reviewed_at": (self.now - timedelta(hours=25)).isoformat()},
             "STALE", "EVENTS_STALE"),
            ({"events_reviewed_at": self.now.isoformat()}, "MISSING", "EVENTS_MISSING"),
        ):
            with self.subTest(expected=expected, fields=fields):
                payload = {k: v for k, v in self.payload.items() if k not in ("events", "events_reviewed_at")}
                payload.update({k: v for k, v in fields.items() if v is not None})
                self.save(payload)
                context = self.load()
                self.assertEqual(context["status"], "AVAILABLE")
                self.assertEqual(context["event_status"], expected)
                self.assertTrue(self.has_blocker(context, blocker))

    def test_review_freshness_boundary(self):
        self.payload["events_reviewed_at"] = (self.now - timedelta(hours=24)).isoformat()
        self.save()
        self.assertEqual(self.load()["event_status"], "REVIEWED")
        self.assertEqual(self.load(self.now + timedelta(microseconds=1))["event_status"], "STALE")

    def test_high_impact_blackout_inclusive_edges(self):
        self.payload["events"] = [
            {"title": "Results", "at": (self.now + timedelta(hours=2)).isoformat(), "importance": "HIGH"}
        ]
        self.save()
        for offset, blocked in (
            (timedelta(hours=1) - timedelta(microseconds=1), False),
            (timedelta(hours=1), True),
            (timedelta(hours=2), True),
            (timedelta(hours=2, minutes=30), True),
            (timedelta(hours=2, minutes=30, microseconds=1), False),
        ):
            with self.subTest(offset=offset):
                self.assertEqual(self.has_blocker(self.load(self.now + offset), "EVENT_BLACKOUT"), blocked)

    def test_custom_blackout_normal_events_and_unreviewed_high(self):
        self.payload.pop("events_reviewed_at")
        self.payload["events"] = [{"title": "News", "at": self.now.isoformat(), "importance": "NORMAL"}]
        self.save()
        self.assertFalse(self.has_blocker(self.load(), "EVENT_BLACKOUT"))
        self.payload["events"][0]["importance"] = "HIGH"
        self.save()
        context = self.load(blackout_before_minutes=0, blackout_after_minutes=0)
        self.assertTrue(self.has_blocker(context, "EVENT_BLACKOUT"))
        self.assertTrue(self.has_blocker(context, "EVENTS_UNREVIEWED"))
        self.assertFalse(self.has_blocker(self.load(self.now + timedelta(microseconds=1),
                                                  blackout_after_minutes=0), "EVENT_BLACKOUT"))

    def test_stale_financials_do_not_imply_stale_event_review(self):
        self.payload["period_end"] = "2026-01-01"
        self.save()
        context = self.load()
        self.assertEqual(context["status"], "STALE")
        self.assertEqual(context["event_status"], "REVIEWED")
        self.assertTrue(self.has_blocker(context, "FINANCIALS_STALE"))
        self.assertFalse(self.has_blocker(context, "EVENTS_STALE"))

    def test_financial_age_boundary_and_old_publication(self):
        self.payload["period_end"] = self.now.date().isoformat()
        self.payload["published_at"] = self.now.isoformat()
        self.save()
        self.assertEqual(self.load(self.now + timedelta(days=120))["status"], "AVAILABLE")
        self.assertEqual(self.load(self.now + timedelta(days=120, microseconds=1))["status"], "STALE")
        self.payload["published_at"] = (self.now - timedelta(days=121)).isoformat()
        self.payload["period_end"] = (self.now - timedelta(days=121)).date().isoformat()
        self.save()
        self.assertEqual(self.load()["status"], "STALE")

    def test_period_end_cannot_follow_publication_utc_date(self):
        self.payload["published_at"] = "2026-10-01T00:30:00+05:30"
        self.payload["period_end"] = "2026-10-01"
        with self.assertRaisesRegex(ValueError, "publication date \\(UTC\\)"):
            self.save()
        self.assertFalse(self.db.exists())
        self.payload["period_end"] = "2026-09-30"
        self.save()
        self.assertEqual(self.load()["period_end"], "2026-09-30")

    def test_panel_forwards_configured_thresholds_and_preserves_defaults(self):
        context = self.load()
        cases = (
            (None, {}),
            ({}, {}),
            ({"event_review_hours": 12}, {"event_review_hours": 12}),
            ({
                "fundamental_max_age_days": 90,
                "event_review_hours": 6,
                "event_blackout_before_minutes": 45,
                "event_blackout_after_minutes": 0,
                "unrelated_setting": True,
            }, {
                "max_age_days": 90,
                "event_review_hours": 6,
                "blackout_before_minutes": 45,
                "blackout_after_minutes": 0,
            }),
        )
        for settings, expected in cases:
            with self.subTest(settings=settings):
                streamlit = MagicMock()
                streamlit.selectbox.return_value = "Type a symbol"
                streamlit.text_input.return_value = "RELIANCE"
                streamlit.form_submit_button.return_value = False
                with patch.dict("sys.modules", {"streamlit": streamlit}):
                    with patch.object(f, "load_context", return_value=context) as load:
                        f.render_fundamentals_panel(settings=settings)
                        load.assert_called_once_with("RELIANCE", **expected)
                streamlit.error.assert_not_called()
        self.assertFalse(self.db.exists())

    def test_null_financials_have_missing_status_and_no_ratios(self):
        self.payload.update(dict.fromkeys(f.NUMERIC_FIELDS))
        self.save()
        context = self.load()
        self.assertEqual(context["status"], "MISSING")
        self.assertIsNotNone(context["snapshot"])
        self.assertTrue(all(value is None for value in context["metrics"].values()))
        self.assertEqual(context["missing_fields"], list(f.NUMERIC_FIELDS))
        self.assertTrue(self.has_blocker(context, "FINANCIALS_MISSING"))

    def test_bad_denominators_and_losses(self):
        self.payload.update(revenue=0, revenue_previous=0, total_equity=-1, net_profit=-10)
        self.save()
        context = self.load()
        self.assertTrue(all(context["metrics"][key] is None for key in f.RATIO_FIELDS))
        self.payload.update(revenue=100, revenue_previous=50, net_profit=-10)
        self.save()
        self.assertEqual(self.load()["metrics"]["net_profit_margin_pct"], -10)

    def test_overflowing_ratios_are_json_safe(self):
        self.payload.update(revenue=1e308, revenue_previous=1e-308)
        self.save()
        context = self.load()
        self.assertIsNone(context["metrics"]["revenue_growth_pct"])
        json.dumps(context, allow_nan=False)

    def test_invalid_numbers_rejected_without_writes(self):
        for field in f.NUMERIC_FIELDS:
            for value in (True, False, float("nan"), float("inf"), -float("inf"), "12", [], 10 ** 400):
                with self.subTest(field=field, value=repr(value)):
                    payload = dict(self.payload, **{field: value})
                    with self.assertRaises(ValueError):
                        self.save(payload)
        for field in ("revenue", "revenue_previous", "total_debt"):
            with self.assertRaises(ValueError):
                self.save(dict(self.payload, **{field: -1}))
        self.assertFalse(self.db.exists())

    def test_invalid_schema_source_and_times(self):
        invalid = {
            "symbol": ("", "NSE:RELIANCE", "../TCS", "a b", None, "X" * 21),
            "source_url": ("", "file:///report", "ftp://example.com", "https://",
                           "https://user:secret@example.com", "https://a b.com", "https://x:bad"),
            "published_at": ("2026-10-20", "2026-10-20T10:00:00", "nonsense",
                             "2026-10-25T00:00:00Z", "2026-02-30T10:00:00Z", None),
            "period_end": ("2026-10-25", "2026-02-30", "20260930", "2026-09-30T00:00:00Z", None),
            "amount_unit": ("", None, 123),
            "reporting_basis": ("", "mixed", None),
            "events_reviewed_at": ("2026-10-25T00:00:00Z", "2026-10-24", "2026-10-24T10:00:00"),
            "events": (None, {}, [{"title": "x", "at": self.now.isoformat(), "importance": "LOW"}],
                       [{"title": "", "at": self.now.isoformat(), "importance": "HIGH"}],
                       [{"title": "x", "at": "2026-10-24", "importance": "HIGH"}], [None]),
        }
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        self.save(dict(self.payload, **{field: value}))
        for value in (None, [], "data"):
            with self.assertRaises(ValueError):
                self.save(value) if value is not None else f.save_snapshot(None, db_path=self.db)
        self.assertFalse(self.db.exists())

    def test_failed_import_preserves_previous_snapshot(self):
        first = self.save()
        with self.assertRaises(ValueError):
            self.save(dict(self.payload, revenue=-1))
        self.assertEqual(self.load()["snapshot_id"], first)

    def test_required_fields_cannot_be_omitted(self):
        for field in ("symbol", "source_url", "published_at", "period_end",
                      "amount_unit", "reporting_basis"):
            with self.subTest(field=field):
                payload = dict(self.payload)
                payload.pop(field)
                with self.assertRaises(ValueError):
                    self.save(payload)
        self.assertFalse(self.db.exists())

    def test_existing_empty_database_is_missing(self):
        with closing(sqlite3.connect(self.db)):
            pass
        self.assertEqual(self.load()["status"], "MISSING")

    def test_missing_values_do_not_become_zero(self):
        payload = {key: value for key, value in self.payload.items() if key not in f.NUMERIC_FIELDS}
        payload["revenue"] = 0
        self.save(payload)
        context = self.load()
        self.assertEqual(context["metrics"]["revenue"], 0)
        self.assertIsNone(context["metrics"]["total_debt"])
        self.assertIsNone(context["metrics"]["debt_to_equity"])

    def test_valid_nse_symbols_and_offset_receipt(self):
        for symbol in ("m&m", "bajaj-auto", "360one", "niftybees"):
            payload = dict(self.payload, symbol=symbol)
            self.save(payload)
            self.assertEqual(f.load_context(symbol, now=self.now, db_path=self.db)["symbol"], symbol.upper())
        identifier = self.save(now="2026-10-24T15:30:00+05:30")
        self.assertEqual(self.load()["snapshot_id"], identifier)

    def test_invalid_now_and_settings(self):
        for now in (datetime(2026, 10, 24), "2026-10-24", True):
            with self.assertRaises(ValueError):
                self.load(now)
            with self.assertRaises(ValueError):
                self.save(now=now)
        for name in ("max_age_days", "event_review_hours", "blackout_before_minutes", "blackout_after_minutes"):
            for value in (-1, True, float("nan"), float("inf"), "24", 1e300):
                with self.subTest(name=name, value=value):
                    with self.assertRaises(ValueError):
                        self.load(**{name: value})

    def test_default_path_anchored_to_module(self):
        self.assertEqual(f.DEFAULT_DB_PATH, Path(f.__file__).resolve().parents[1] / "db" / "fundamentals.db")

    def advanced_payload(self):
        return dict(
            self.payload, entity_type="NON_FINANCIAL", comparisons_comparable=True,
            period_start="2026-07-01", cash_flow_period_start="2026-07-01",
            cash_flow_period_end="2026-09-30", assets_begin=100, assets_end=140,
            current_assets=60, current_liabilities=30, ebit=24, interest_expense=4, capex=8,
        )

    def expectation_payload(self):
        payload = self.advanced_payload()
        payload["earnings_expectation"] = {
            "actual_eps": 6, "consensus_eps": 5, "eps_basis": "DILUTED",
            "consensus_eps_basis": "DILUTED", "currency": "INR",
            "reporting_basis": "consolidated", "consensus_reporting_basis": "consolidated",
            "earnings_definition": "REPORTED", "consensus_earnings_definition": "REPORTED",
            "split_basis": "Adjusted to shares outstanding 2026-09-30",
            "consensus_split_basis": "Adjusted to shares outstanding 2026-09-30",
            "period_start": "2026-07-01", "period_end": "2026-09-30",
            "consensus_source_url": "https://example.com/consensus",
            "consensus_as_of": "2026-10-19T10:00:00Z",
            "announced_at": self.payload["published_at"],
        }
        return payload

    def test_advanced_nonfinancial_metrics_and_methodology(self):
        identifier = self.save(self.advanced_payload())
        context = self.load()
        expected = {
            "roa_pct": 10, "cash_accruals_pct": -5, "free_cash_flow": 10,
            "current_ratio": 2, "interest_coverage": 6, "operating_cash_flow_to_profit": 1.5,
        }
        self.assertEqual(context["entity_type"], "NON_FINANCIAL")
        self.assertEqual(context["method_version"], f.METHOD_VERSION)
        self.assertEqual(context["evidence_id"], f"fundamental:{identifier}")
        self.assertTrue(context["cash_flow_periods_aligned"])
        for field, value in expected.items():
            self.assertAlmostEqual(context["metrics"][field], value)
            self.assertEqual(context["metric_eligibility"][field]["status"], "AVAILABLE")
            self.assertIn(field, context["metric_definitions"])
        self.assertEqual(context["blockers"], [])
        self.assertEqual(context["financial_assessment"][0]["research_ids"],
                         ["sloan-1996", "dechow-dichev-2002"])
        self.assertIn("does not establish fraud", context["financial_assessment"][0]["finding"])
        self.assertIn("No Dechow-Dichev", context["financial_assessment"][0]["finding"])
        json.dumps(context, allow_nan=False)

    def test_old_persisted_json_defaults_to_unknown_not_nonfinancial(self):
        identifier = self.save()
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:
                connection.execute(
                    "UPDATE fundamental_snapshots SET payload_json=? WHERE id=?",
                    (json.dumps(self.payload), identifier),
                )
        context = self.load()
        self.assertEqual(context["entity_type"], "UNKNOWN")
        self.assertFalse(context["comparisons_comparable"])
        self.assertIsNone(context["metrics"]["roa_pct"])
        self.assertIsNone(context["period_start"])
        self.assertEqual(context["metrics"]["operating_cash_flow_to_profit"], 1.5)
        for name in ("debt_to_equity", "revenue_growth_pct", "operating_cash_flow_to_profit"):
            self.assertEqual(context["metric_eligibility"][name]["status"], "UNVERIFIED")
        self.assertTrue(any("entity_type UNKNOWN" in warning for warning in context["warnings"]))
        self.assertEqual(context["financial_assessment"], [])

    def test_mismatched_or_missing_cash_flow_windows_cannot_drive_findings(self):
        for updates in (
            {"cash_flow_period_start": "2026-04-01"},
            {"cash_flow_period_start": None, "cash_flow_period_end": None},
            {"period_start": None},
        ):
            with self.subTest(updates=updates):
                payload = dict(self.advanced_payload(), operating_cash_flow=-10, **updates)
                self.save(payload)
                context = self.load()
                self.assertFalse(context["cash_flow_periods_aligned"])
                for name in ("cash_accruals_pct", "free_cash_flow", "operating_cash_flow_to_profit"):
                    self.assertIsNone(context["metrics"][name])
                    self.assertEqual(context["metric_eligibility"][name]["status"], "UNAVAILABLE")
                self.assertFalse(any(item["role"] == "ACCOUNTING_RISK_CONTEXT"
                                     for item in context["financial_assessment"]))
                self.assertEqual(context["blockers"], [])

    def test_zero_denominators_and_missing_advanced_inputs(self):
        self.save(dict(self.advanced_payload(), assets_begin=0, assets_end=0,
                       current_liabilities=0, interest_expense=0, capex=None))
        context = self.load()
        for name in ("roa_pct", "cash_accruals_pct", "current_ratio", "interest_coverage", "free_cash_flow"):
            self.assertIsNone(context["metrics"][name])
            self.assertEqual(context["metric_eligibility"][name]["status"], "UNAVAILABLE")
        self.assertIn("capex", context["metric_eligibility"]["free_cash_flow"]["reason"])

    def test_financial_entities_suppress_inappropriate_generic_metrics(self):
        for entity in ("BANK", "NBFC", "INSURANCE"):
            with self.subTest(entity=entity):
                payload = dict(self.advanced_payload(), entity_type=entity, total_equity=-1,
                               operating_cash_flow=-10, gross_npa_pct=5,
                               net_npa_pct=2, capital_adequacy_pct=15)
                self.save(payload)
                context = self.load()
                for name in ("debt_to_equity", "current_ratio", "cash_accruals_pct", "roa_pct",
                             "free_cash_flow", "interest_coverage", "operating_cash_flow_to_profit"):
                    self.assertIsNone(context["metrics"][name])
                    self.assertIn(entity, context["metric_eligibility"][name]["reason"])
                self.assertEqual(context["financial_assessment"], [])
                self.assertEqual(context["blockers"], [])
                if entity == "INSURANCE":
                    self.assertIsNone(context["metrics"]["gross_npa_pct"])
                else:
                    self.assertEqual(context["metrics"]["gross_npa_pct"], 5)
                    self.assertEqual(context["metric_eligibility"]["gross_npa_pct"]["status"], "REPORTED")
                self.assertTrue(any(entity in item for item in context["warnings"]))

    def test_reported_prudential_ratios_are_unknown_when_missing(self):
        self.save(dict(self.payload, entity_type="BANK"))
        context = self.load()
        for name in f.REPORTED_RATIO_FIELDS:
            self.assertIsNone(context["metrics"][name])
            self.assertIn("not a failed test", context["metric_eligibility"][name]["reason"])
        self.assertEqual(context["blockers"], [])

    def test_nonfinancial_qualitative_findings_are_context_not_new_blockers(self):
        self.save(dict(self.advanced_payload(), net_profit=12, operating_cash_flow=-5, total_equity=0))
        context = self.load()
        roles = {item["role"] for item in context["financial_assessment"]}
        self.assertIn("ACCOUNTING_RISK_CONTEXT", roles)
        self.assertIn("BALANCE_SHEET_RISK_CONTEXT", roles)
        self.assertEqual(context["metrics"]["cash_accruals_pct"], 17 / 120 * 100)
        self.assertEqual(context["blockers"], [])
        for item in context["financial_assessment"]:
            self.assertEqual(item["evidence_id"], context["evidence_id"])
            self.assertIn("basis", item)
        self.assertTrue(any("piotroski-2000" in item["research_ids"]
                            for item in context["financial_assessment"]))

    def test_optional_schema_validation_and_publication_rules(self):
        cases = (
            {"entity_type": "TECH"}, {"entity_type": None}, {"comparisons_comparable": 1},
            {"comparisons_comparable": "true"}, {"period_start": "2026-10-01"},
            {"period_start": "2026-07-01T00:00:00Z"}, {"cash_flow_period_start": "2026-07-01"},
            {"cash_flow_period_end": "2026-09-30"},
            {"cash_flow_period_start": "2026-10-01", "cash_flow_period_end": "2026-09-30"},
            {"cash_flow_period_start": "2026-07-01", "cash_flow_period_end": "2026-10-21"},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.save(dict(self.payload, **changes))
        for field in ("assets_begin", "assets_end", "current_assets", "current_liabilities",
                      "interest_expense", "capex") + f.REPORTED_RATIO_FIELDS:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self.save(dict(self.payload, **{field: -1}))
        for field in ("gross_npa_pct", "net_npa_pct"):
            with self.assertRaises(ValueError):
                self.save(dict(self.payload, **{field: 100.01}))
        self.assertFalse(self.db.exists())

    def test_reported_percent_boundaries_and_signed_ebit_are_valid(self):
        for percentage in (0, 100):
            self.save(dict(self.advanced_payload(), ebit=-8, gross_npa_pct=percentage))
            self.assertEqual(self.load()["metrics"]["interest_coverage"], -2)
            self.assertIsNone(self.load()["metrics"]["gross_npa_pct"])

    def test_capital_adequacy_is_not_capped_like_an_ownership_percentage(self):
        self.save(dict(self.payload, entity_type="BANK", capital_adequacy_pct=150))
        context = self.load()
        self.assertEqual(context["metrics"]["capital_adequacy_pct"], 150)
        self.assertEqual(context["metric_eligibility"]["capital_adequacy_pct"]["status"], "REPORTED")

    def test_eps_only_snapshot_has_financial_availability_and_freshness(self):
        payload = self.expectation_payload()
        for field in f.NUMERIC_FIELDS:
            payload[field] = None
        self.save(payload)
        context = self.load()
        self.assertEqual(context["status"], "AVAILABLE")
        self.assertEqual(context["metrics"]["eps_surprise_pct"], 20)
        self.assertFalse(self.has_blocker(context, "FINANCIALS_MISSING"))
        stale = self.load(max_age_days=1)
        self.assertEqual(stale["status"], "STALE")
        self.assertTrue(self.has_blocker(stale, "FINANCIALS_STALE"))

    def test_eps_surprise_has_comparable_prerelease_provenance(self):
        payload = self.expectation_payload()
        original = copy.deepcopy(payload)
        self.save(payload)
        self.assertEqual(payload, original)
        context = self.load()
        self.assertEqual(context["metrics"]["eps_surprise_absolute"], 1)
        self.assertEqual(context["metrics"]["eps_surprise_pct"], 20)
        self.assertEqual(context["metric_eligibility"]["eps_surprise_pct"]["status"], "AVAILABLE")
        item = next(item for item in context["financial_assessment"]
                    if item["role"] == "DESCRIPTIVE_EVENT_CONTEXT")
        self.assertEqual(item["research_ids"], ["bernard-thomas-1989"])
        self.assertEqual(item["basis"]["consensus_as_of"], "2026-10-19T10:00:00.000000+00:00")
        self.assertEqual(self.load(self.now - timedelta(seconds=1))["snapshot_id"], None)

    def test_signed_and_zero_eps_consensus(self):
        for consensus, actual, absolute, percentage in (
            (-5, -4, 1, 20), (0, 1, 1, None), (5, -5, -10, -200), (5, 5, 0, 0),
        ):
            with self.subTest(consensus=consensus, actual=actual):
                payload = self.expectation_payload()
                payload["earnings_expectation"].update(actual_eps=actual, consensus_eps=consensus)
                self.save(payload)
                context = self.load()
                self.assertEqual(context["metrics"]["eps_surprise_absolute"], absolute)
                self.assertEqual(context["metrics"]["eps_surprise_pct"], percentage)

    def test_invalid_eps_comparisons_and_postrelease_consensus_are_rejected(self):
        cases = (
            {"eps_basis": "ADJUSTED"}, {"consensus_eps_basis": "BASIC"},
            {"period_start": "2026-04-01"}, {"period_end": "2026-09-29"},
            {"currency": ""}, {"consensus_source_url": "ftp://example.com/data"},
            {"consensus_as_of": "2026-10-20T10:00:00Z"},
            {"consensus_as_of": "2026-10-20T10:00:01Z"},
            {"consensus_as_of": "2026-10-19"},
            {"announced_at": "2026-10-20T10:00:01Z"},
            {"announced_at": "2026-10-25T10:00:00Z"},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                payload = self.expectation_payload()
                payload["earnings_expectation"].update(changes)
                with self.assertRaises(ValueError):
                    self.save(payload)
        for name in ("actual_eps", "consensus_eps"):
            for value in (None, True, float("nan"), float("inf"), "5"):
                payload = self.expectation_payload()
                payload["earnings_expectation"][name] = value
                with self.assertRaises(ValueError):
                    self.save(payload)
        for name in self.expectation_payload()["earnings_expectation"]:
            if name in f.EXPECTATION_QUALIFIERS:
                continue
            payload = self.expectation_payload()
            payload["earnings_expectation"].pop(name)
            with self.assertRaises(ValueError):
                self.save(payload)
        payload = self.expectation_payload()
        payload.pop("period_start")
        with self.assertRaises(ValueError):
            self.save(payload)
        self.assertFalse(self.db.exists())

    def test_no_surprise_from_ineligible_persisted_expectation(self):
        payload = self.expectation_payload()
        identifier = self.save(payload)
        payload["earnings_expectation"]["consensus_eps_basis"] = "BASIC"
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:
                connection.execute(
                    "UPDATE fundamental_snapshots SET payload_json=? WHERE id=?",
                    (json.dumps(payload), identifier),
                )
        context = self.load()
        self.assertIsNone(context["metrics"]["eps_surprise_absolute"])
        self.assertIsNone(context["metrics"]["eps_surprise_pct"])
        self.assertIn("bases must match", context["metric_eligibility"]["eps_surprise_pct"]["reason"])

    def test_advanced_overflows_remain_json_safe(self):
        payload = self.expectation_payload()
        payload.update(net_profit=1e308, operating_cash_flow=-1e308, capex=1e308)
        payload["earnings_expectation"].update(actual_eps=1e308, consensus_eps=-1e308)
        self.save(payload)
        context = self.load()
        for name in ("cash_accruals_pct", "free_cash_flow", "eps_surprise_absolute", "eps_surprise_pct"):
            self.assertIsNone(context["metrics"][name])
        json.dumps(context, allow_nan=False)

    def test_eps_percentage_minimum_policy_includes_exact_boundary(self):
        for threshold in (0.01, 0.1):
            for consensus, eligible in (
                (threshold, True), (-threshold, True),
                (threshold * 0.999, False), (-threshold * 0.999, False), (0, False),
            ):
                with self.subTest(threshold=threshold, consensus=consensus):
                    payload = self.expectation_payload()
                    expectation = payload["earnings_expectation"]
                    expectation.update(actual_eps=1, consensus_eps=consensus)
                    if threshold != 0.01:
                        expectation["min_abs_consensus_eps"] = threshold
                    self.save(payload)
                    context = self.load()
                    normalized = context["snapshot"]["earnings_expectation"]
                    self.assertEqual(normalized["min_abs_consensus_eps"], threshold)
                    self.assertEqual(context["metrics"]["eps_surprise_absolute"], 1 - consensus)
                    if eligible:
                        self.assertAlmostEqual(context["metrics"]["eps_surprise_pct"],
                                               (1 - consensus) / abs(consensus) * 100)
                    else:
                        self.assertIsNone(context["metrics"]["eps_surprise_pct"])
                        self.assertIn("numerical policy",
                                      context["metric_eligibility"]["eps_surprise_pct"]["reason"])

    def test_invalid_eps_minimum_policy_rejected(self):
        for threshold in (0, -0.01, True, None, "0.01", float("nan"), float("inf")):
            with self.subTest(threshold=threshold):
                payload = self.expectation_payload()
                payload["earnings_expectation"]["min_abs_consensus_eps"] = threshold
                with self.assertRaises(ValueError):
                    self.save(payload)
        self.assertFalse(self.db.exists())

    def test_missing_eps_qualifiers_are_unverified_not_rejected(self):
        for omitted in (f.EXPECTATION_QUALIFIERS,) + tuple((field,) for field in f.EXPECTATION_QUALIFIERS):
            with self.subTest(omitted=omitted):
                payload = self.expectation_payload()
                for field in omitted:
                    payload["earnings_expectation"].pop(field)
                self.save(payload)
                context = self.load()
                self.assertEqual(context["metrics"]["eps_surprise_absolute"], 1)
                self.assertEqual(context["metrics"]["eps_surprise_pct"], 20)
                for name in ("eps_surprise_absolute", "eps_surprise_pct"):
                    details = context["metric_eligibility"][name]
                    self.assertEqual(details["status"], "UNVERIFIED")
                    self.assertIn(omitted[0], details["reason"])
                self.assertTrue(any("EPS comparability qualifiers missing" in warning
                                    for warning in context["warnings"]))
                item = next(item for item in context["financial_assessment"]
                            if item["role"] == "DESCRIPTIVE_EVENT_CONTEXT")
                self.assertEqual(item["basis"]["comparability_status"], "UNVERIFIED")

    def test_invalid_or_mismatched_eps_qualifiers_rejected(self):
        for changes in (
            {"reporting_basis": "standalone"}, {"consensus_reporting_basis": "standalone"},
            {"reporting_basis": "standalone", "consensus_reporting_basis": "standalone"},
            {"earnings_definition": "ADJUSTED"}, {"consensus_earnings_definition": "ADJUSTED"},
            {"earnings_definition": "UNKNOWN"}, {"consensus_earnings_definition": ""},
            {"split_basis": "Unadjusted prior share count"},
            {"consensus_split_basis": "Unadjusted prior share count"},
            {"split_basis": ""}, {"consensus_split_basis": None},
        ):
            with self.subTest(changes=changes):
                payload = self.expectation_payload()
                payload["earnings_expectation"].update(changes)
                with self.assertRaises(ValueError):
                    self.save(payload)
        self.assertFalse(self.db.exists())

    def test_matching_adjusted_eps_is_eligible_and_provenance_preserved(self):
        payload = self.expectation_payload()
        payload["reporting_basis"] = "standalone"
        payload["earnings_expectation"].update(
            reporting_basis="standalone", consensus_reporting_basis="standalone",
            earnings_definition="ADJUSTED", consensus_earnings_definition="ADJUSTED",
        )
        self.save(payload)
        context = self.load()
        self.assertEqual(context["metric_eligibility"]["eps_surprise_pct"]["status"], "AVAILABLE")
        item = next(item for item in context["financial_assessment"]
                    if item["role"] == "DESCRIPTIVE_EVENT_CONTEXT")
        self.assertEqual(item["basis"]["earnings_definition"], "ADJUSTED")
        self.assertEqual(item["basis"]["reporting_basis"], "standalone")
        self.assertEqual(item["basis"]["min_abs_consensus_eps"], 0.01)

    def test_legacy_persisted_eps_gets_default_policy_and_unverified_qualifiers(self):
        payload = self.expectation_payload()
        for name in f.EXPECTATION_QUALIFIERS:
            payload["earnings_expectation"].pop(name)
        payload["earnings_expectation"]["consensus_eps"] = 0.001
        identifier = self.save(payload)
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:
                connection.execute(
                    "UPDATE fundamental_snapshots SET payload_json=? WHERE id=?",
                    (json.dumps(payload), identifier),
                )
        context = self.load()
        self.assertEqual(context["metrics"]["eps_surprise_absolute"], 5.999)
        self.assertIsNone(context["metrics"]["eps_surprise_pct"])
        self.assertEqual(context["metric_eligibility"]["eps_surprise_absolute"]["status"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
