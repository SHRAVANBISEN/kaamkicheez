"""Run with system Python: python -X utf8 -m unittest -q test_institutions."""

import copy
import json
import sqlite3
import unittest
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from stocktrading import institutions


class InstitutionsTests(unittest.TestCase):
    def setUp(self):
        self.db = Path(__file__).resolve().parent / ("institutions_test_" + uuid.uuid4().hex + ".db")
        self.now = datetime(2026, 10, 24, 10, tzinfo=timezone.utc)
        self.flow = {
            "kind": "MARKET_FLOW", "source_url": "https://www.nseindia.com/flows",
            "record_id": "flow-1", "published_at": "2026-10-24T15:00:00+05:30",
            "observation_date": "2026-10-23", "scope": "NSE+BSE+MSEI cash equity",
            "participant": "FII_FPI", "gross_buy_crore": 100, "gross_sell_crore": 120,
        }
        self.owner = dict(
            self.flow, kind="OWNERSHIP", record_id="owner-1", symbol=" reliance ",
            category="FII/FPI", observation_date="2026-09-30", ownership_pct=23.5,
            previous_observation_date="2026-06-30", previous_ownership_pct=24,
        )
        self.deal = dict(
            self.flow, kind="DEAL", record_id="deal-1", symbol="RELIANCE", deal_type="BULK",
            participant_name="Some Fund Limited", side="BUY", quantity=100, price=20.5,
        )

    def tearDown(self):
        for suffix in ("", "-journal", "-wal", "-shm"):
            path = Path(str(self.db) + suffix)
            if path.exists():
                path.unlink()

    def save(self, payload=None, now=None):
        return institutions.save_observation(
            self.flow if payload is None else payload, db_path=self.db,
            now=self.now if now is None else now,
        )

    def load(self, now=None, **kwargs):
        return institutions.load_context(
            "RELIANCE", now=self.now if now is None else now, db_path=self.db, **kwargs,
        )

    def test_missing_does_not_touch_database(self):
        with patch.object(institutions.sqlite3, "connect") as connect:
            context = self.load()
        connect.assert_not_called()
        self.assertFalse(self.db.exists())
        self.assertEqual(context["status"], "MISSING")
        for name in ("market_flows", "ownership", "deals"):
            self.assertEqual(context[name]["status"], "MISSING")
            self.assertTrue(context[name]["missing"])
        self.assertEqual(context["evidence_ids"], [])
        json.dumps(context, allow_nan=False)

    def test_validation_before_writes(self):
        invalid = [
            ("kind", "OTHER"), ("source_url", "file://source"), ("source_url", "https://u:p@host"),
            ("source_url", "https://host:bad"), ("source_url", "https://ho st"),
            ("source_url", "https://host\\evil"), ("record_id", " "),
            ("published_at", "2026-10-24T10:00:00"),
            ("published_at", "2026-10-25T10:00:00Z"), ("published_at", True),
            ("observation_date", "2026-02-30"), ("observation_date", "20261023"),
            ("observation_date", "2026-10-25"), ("scope", ""),
            ("participant", "FOREIGN"), ("gross_buy_crore", True),
            ("gross_buy_crore", -1), ("gross_sell_crore", float("nan")),
            ("gross_buy_crore", float("inf")), ("gross_buy_crore", 10**400),
        ]
        for field, value in invalid:
            with self.subTest(field=field, value=str(value)):
                with self.assertRaises(ValueError):
                    self.save(dict(self.flow, **{field: value}))
                self.assertFalse(self.db.exists())
        with self.assertRaises(ValueError):
            self.save([])
        with self.assertRaises(ValueError):
            self.load(now=datetime(2026, 10, 24))
        for value in (True, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.load(flow_max_age_days=value)

    def test_ist_date_validation(self):
        when = datetime(2026, 10, 24, 19, tzinfo=timezone.utc)
        payload = dict(self.flow, published_at="2026-10-24T18:45:00Z", observation_date="2026-10-25")
        self.save(payload, now=when)
        self.assertEqual(self.load(now=when)["market_flows"]["rows"][0]["age_days"], 0)
        with self.assertRaises(ValueError):
            self.save(dict(payload, published_at="2026-10-24T18:00:00Z"), now=when)

    def test_signed_net_and_server_receipt(self):
        payload = dict(self.flow, received_at="2000-01-01T00:00:00Z", net_crore=999)
        original = copy.deepcopy(payload)
        row_id = self.save(payload)
        context = self.load()
        row = context["market_flows"]["rows"][0]
        self.assertEqual(payload, original)
        self.assertEqual(row["net_crore"], -20)
        self.assertEqual(row["flow_description"], "NET_SELLING")
        self.assertEqual(row["received_at"], self.now.isoformat(timespec="microseconds"))
        self.assertEqual(row["evidence_id"], f"institutional:{row_id}")
        self.assertEqual(context["status"], "PARTIAL")
        self.assertEqual(context["market_flows"]["status"], "PARTIAL")
        self.assertTrue(any("DII missing" in msg for msg in context["market_flows"]["missing"]))
        self.assertNotIn("signal", row)
        self.save(dict(self.flow, gross_buy_crore=120))
        self.assertEqual(self.load()["market_flows"]["rows"][0]["flow_description"], "BALANCED")
        self.save(dict(self.flow, gross_buy_crore=121))
        self.assertEqual(self.load()["market_flows"]["rows"][0]["flow_description"], "NET_BUYING")
        json.dumps(context, allow_nan=False)

    def test_receipt_and_publication_lookahead(self):
        first = self.save()
        second = self.save(dict(self.flow, gross_buy_crore=140), now=self.now + timedelta(days=1))
        self.assertEqual(self.load()["evidence_ids"], [f"institutional:{first}"])
        self.assertEqual(self.load(self.now + timedelta(days=1))["evidence_ids"], [f"institutional:{second}"])
        self.assertEqual(self.load(self.now - timedelta(microseconds=1))["status"], "MISSING")
        # Simulate a legacy row with a future publication independently of receipt.
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:
                connection.execute(
                    "UPDATE institutional_observations SET published_at=? WHERE id=?",
                    ("2026-10-26T00:00:00.000000+00:00", second),
                )
        self.assertEqual(self.load(self.now + timedelta(days=1))["evidence_ids"], [f"institutional:{first}"])

    def test_revision_dedup_and_late_old_revision(self):
        first = self.save(self.deal)
        newer = dict(self.deal, price=25, published_at="2026-10-24T15:20:00+05:30")
        second = self.save(newer)
        self.save(self.deal, now=self.now + timedelta(hours=1))
        rows = self.load(self.now + timedelta(hours=1))["deals"]["rows"]
        self.assertEqual([row["id"] for row in rows], [second])
        self.assertNotEqual(first, second)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM institutional_observations").fetchone()[0], 3)
        third = self.save(newer, now=self.now + timedelta(hours=2))
        self.assertEqual(self.load(self.now + timedelta(hours=2))["deals"]["rows"][0]["id"], third)

    def test_scope_source_and_latest_date_selection_without_sum(self):
        self.save()
        self.save(dict(self.flow, record_id="older", observation_date="2026-10-22", gross_buy_crore=999))
        self.save(dict(self.flow, record_id="other-scope", scope="NSE only"))
        self.save(dict(self.flow, source_url="https://other.example/flows"))
        rows = self.load()["market_flows"]["rows"]
        self.assertEqual(len(rows), 3)
        self.assertEqual([row["net_crore"] for row in rows], [-20, -20, -20])
        self.assertNotIn("total", self.load()["market_flows"])
        self.assertEqual({row["observation_date"] for row in rows}, {"2026-10-23"})

    def test_ownership_delta_is_dated_and_not_purchase(self):
        self.save(self.owner)
        context = self.load()
        row = context["ownership"]["rows"][0]
        self.assertEqual(row["symbol"], "RELIANCE")
        self.assertEqual(row["change_percentage_points"], -0.5)
        self.assertEqual(row["previous_observation_date"], "2026-06-30")
        self.assertNotIn("net_purchasing", row)
        self.assertEqual(context["ownership"]["status"], "FRESH")
        self.assertEqual(context["deals"]["status"], "MISSING")
        other = institutions.load_context("TCS", db_path=self.db, now=self.now)
        self.assertEqual(other["ownership"]["status"], "MISSING")
        payload = dict(self.owner)
        del payload["previous_observation_date"]
        del payload["previous_ownership_pct"]
        self.save(payload)
        self.assertIsNone(self.load()["ownership"]["rows"][0]["change_percentage_points"])
        for field, value in (
            ("ownership_pct", 101), ("ownership_pct", True), ("previous_ownership_pct", -1),
            ("previous_observation_date", None), ("previous_ownership_pct", None),
            ("previous_observation_date", "2026-09-30"), ("previous_observation_date", "2026-10-01"),
            ("category", " "), ("symbol", "ABC/DEF"),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.save(dict(self.owner, **{field: value}))

    def test_deals_not_inferred_and_finite_notional(self):
        self.save(self.deal)
        row = self.load()["deals"]["rows"][0]
        self.assertEqual(row["institutional_identity"], "UNVERIFIED")
        self.assertEqual(row["notional_inr"], 2050)
        self.assertTrue(any("counterparty" in w for w in self.load()["warnings"]))
        identified = dict(self.deal, institutional_identity="SOURCE_IDENTIFIED",
                          identity_source_url="https://source.example/disclosed-identity")
        self.save(identified)
        self.assertEqual(self.load()["deals"]["rows"][0]["institutional_identity"], "SOURCE_IDENTIFIED")
        for changes in (
            {"quantity": True}, {"quantity": 1.5}, {"quantity": 0}, {"price": 0},
            {"price": float("nan")}, {"quantity": 10**308, "price": 1e308},
            {"price": float("inf")}, {"side": "HOLD"}, {"deal_type": "LARGE"},
            {"participant_name": ""}, {"institutional_identity": "INFERRED"},
            {"institutional_identity": "SOURCE_IDENTIFIED"},
            {"institutional_identity": "SOURCE_IDENTIFIED", "identity_source_url": "ftp://host"},
        ):
            with self.subTest(changes=str(changes)), self.assertRaises(ValueError):
                self.save(dict(self.deal, **changes))

    def test_separate_deals_retained_and_truncated(self):
        for index in range(51):
            self.save(dict(self.deal, record_id=f"deal-{index}", side="BUY" if index % 2 else "SELL"))
        context = self.load()
        self.assertEqual(len(context["deals"]["rows"]), 50)
        self.assertEqual(context["deals"]["total_available"], 51)
        self.assertTrue(context["deals"]["truncated"])
        self.assertEqual(context["deals"]["status"], "PARTIAL")
        self.assertTrue(any("Truncated" in w for w in context["warnings"]))
        self.assertEqual(len(set(context["evidence_ids"])), 50)
        self.assertNotIn("net_quantity", context["deals"])

    def test_independent_stale_thresholds_and_complete_fresh_sections(self):
        self.save()
        self.save(dict(self.flow, participant="DII", record_id="flow-dii"))
        self.save(self.owner)
        self.save(self.deal)
        self.assertEqual(self.load()["status"], "AVAILABLE")
        context = self.load(flow_max_age_days=0, ownership_max_age_days=24, deal_max_age_days=1)
        self.assertEqual(context["market_flows"]["status"], "STALE")
        self.assertEqual(context["ownership"]["status"], "FRESH")
        self.assertEqual(context["deals"]["status"], "FRESH")
        self.assertEqual(context["status"], "PARTIAL")
        context = self.load(self.now + timedelta(days=1), ownership_max_age_days=24, deal_max_age_days=1)
        self.assertEqual(context["market_flows"]["status"], "FRESH")
        self.assertEqual(context["ownership"]["status"], "STALE")
        self.assertEqual(context["deals"]["status"], "STALE")
        self.assertNotIn("ALL_CLEAR", json.dumps(context))

    def test_partial_flow_dates_and_mixed_stale_ownership(self):
        self.save()
        self.save(dict(self.flow, participant="DII", record_id="dii", observation_date="2026-10-22"))
        self.save(self.owner)
        self.save(dict(self.owner, category="DII", record_id="older-owner",
                       observation_date="2026-07-01", previous_observation_date="2026-04-01"))
        context = self.load(ownership_max_age_days=30)
        self.assertEqual(context["market_flows"]["status"], "PARTIAL")
        self.assertEqual(context["ownership"]["status"], "PARTIAL")
        self.assertEqual({r["status"] for r in context["ownership"]["rows"]}, {"STALE", "FRESH"})

    def test_revision_can_correct_symbol(self):
        self.save(self.deal)
        self.save(dict(self.deal, symbol="TCS"))
        self.assertEqual(self.load()["deals"]["status"], "MISSING")
        self.assertEqual(institutions.load_context("TCS", db_path=self.db, now=self.now)["deals"]["status"], "FRESH")

    def test_publication_status_validated_preserved_and_defaults(self):
        for payload, section in (
            (self.flow, "market_flows"), (self.owner, "ownership"), (self.deal, "deals"),
        ):
            self.save(payload)
            self.assertEqual(self.load()[section]["rows"][0]["publication_status"], "UNKNOWN")
            for status in ("UNKNOWN", "PROVISIONAL", "FINAL", "REVISED"):
                with self.subTest(kind=payload["kind"], status=status):
                    self.save(dict(payload, publication_status=status, source_note="Source qualifier"))
                    row = self.load()[section]["rows"][0]
                    self.assertEqual(row["publication_status"], status)
                    self.assertEqual(row["source_note"], "Source qualifier")
            for status in (None, True, "final", "INFERRED", ""):
                with self.subTest(kind=payload["kind"], status=status), self.assertRaises(ValueError):
                    self.save(dict(payload, publication_status=status))

    def test_legacy_rows_default_publication_status_on_read(self):
        for payload in (self.flow, self.owner, self.deal):
            row_id = self.save(payload)
            with closing(sqlite3.connect(self.db)) as connection:
                with connection:
                    serialized = connection.execute(
                        "SELECT payload_json FROM institutional_observations WHERE id=?", (row_id,),
                    ).fetchone()[0]
                    legacy = json.loads(serialized)
                    del legacy["publication_status"]
                    connection.execute(
                        "UPDATE institutional_observations SET payload_json=? WHERE id=?",
                        (json.dumps(legacy), row_id),
                    )
        context = self.load()
        for section in ("market_flows", "ownership", "deals"):
            self.assertEqual(context[section]["rows"][0]["publication_status"], "UNKNOWN")
        with closing(sqlite3.connect(self.db)) as connection:
            for (serialized,) in connection.execute("SELECT payload_json FROM institutional_observations"):
                self.assertNotIn("publication_status", json.loads(serialized))

    def test_ui_compact_tables_retain_full_raw_provenance(self):
        for payload in (self.flow, self.owner, self.deal):
            self.save(dict(payload, publication_status="PROVISIONAL"))
        context = self.load()
        st = MagicMock()
        st.selectbox.return_value = "RELIANCE"
        st.text_input.return_value = ""
        st.form_submit_button.return_value = False
        with patch.dict("sys.modules", {"streamlit": st}), \
                patch.object(institutions, "load_context", return_value=context):
            institutions.render_institutions_panel(["RELIANCE"])
        self.assertEqual(st.table.call_count, 3)
        for call, derived in zip(st.table.call_args_list, ("net_crore", "change_percentage_points", "notional_inr")):
            row = call.args[0][0]
            self.assertTrue({
                "evidence_id", "observation_date", "status", "publication_status", "source_url", derived,
            }.issubset(row))
            self.assertEqual(row["publication_status"], "PROVISIONAL")
            self.assertNotIn("received_at", row)
            self.assertNotIn("published_at", row)
        self.assertEqual(st.json.call_args.args[0], context)
        for call in st.json.call_args_list[:3]:
            self.assertEqual(call.args[0]["publication_status"], "UNKNOWN")

    def test_ui_only_saves_on_submit_and_passes_settings(self):
        st = MagicMock()
        st.selectbox.return_value = "RELIANCE"
        st.text_input.return_value = ""
        st.form_submit_button.return_value = False
        settings = {"flow_max_age_days": 3, "ownership_max_age_days": 90, "deal_max_age_days": 2}
        with patch.dict("sys.modules", {"streamlit": st}), \
                patch.object(institutions, "save_observation") as save, \
                patch.object(institutions, "load_context", return_value=self.load()) as load:
            institutions.render_institutions_panel(["RELIANCE"], settings)
        save.assert_not_called()
        load.assert_called_once_with("RELIANCE", **settings)
        st.form_submit_button.return_value = True
        st.text_area.return_value = json.dumps(self.flow)
        with patch.dict("sys.modules", {"streamlit": st}), \
                patch.object(institutions, "save_observation", return_value=42) as save, \
                patch.object(institutions, "load_context", return_value=self.load()):
            institutions.render_institutions_panel(["RELIANCE"])
        save.assert_called_once_with(self.flow)


if __name__ == "__main__":
    unittest.main()
