import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from stocktrading import ai_analyst as ai
from stocktrading.analysis_evidence import save_evidence, load_run
from stocktrading.data_fetcher import fetch_candles
from stocktrading.intraday_engine import calculate_features, load_rules, market_now, _wilder
from stocktrading.config import PROJECT_ROOT

NOW = pd.Timestamp("2026-10-23T11:01:00+05:30")


def candles():
    rows = []
    for date in pd.bdate_range("2026-10-15", "2026-10-23"):
        start = date.tz_localize("Asia/Kolkata") + pd.Timedelta(hours=9, minutes=15)
        for slot in range(75):
            stamp = start + pd.Timedelta(minutes=slot * 5)
            if stamp + pd.Timedelta(minutes=5) > NOW:
                continue
            price = 100 + len(rows) * 0.02
            rows.append([stamp, "TEST", price, price + 0.03, price - 0.03, price + 0.01, 100])
    frame = pd.DataFrame(rows, columns=["timestamp", "symbol", "open", "high", "low", "close", "volume"])
    frame.attrs.update(timeframe_minutes=5, source="synthetic test")
    return frame


class TechnicalTests(unittest.TestCase):
    def setUp(self):
        self.frame = candles()
        self.rules = load_rules()

    def test_session_vwap_and_completed_range(self):
        result = calculate_features(self.frame, NOW, self.rules)
        session = self.frame[self.frame.timestamp.dt.date == NOW.date()]
        expected = (((session.high + session.low + session.close) / 3) * session.volume).sum() / session.volume.sum()
        self.assertAlmostEqual(result["intraday"]["vwap"], expected, places=5)
        self.assertEqual(result["intraday"]["opening_range_high"], session.head(3).high.max())
        self.assertEqual(result["intraday"]["rvol_samples"], 5)
        self.assertEqual(result["intraday"]["relative_volume"], 1)
        self.assertEqual(result["intraday"]["previous_observed_session"]["date"], "2026-10-22")
        self.assertEqual(result["intraday"]["blockers"], [])
        json.dumps(result, allow_nan=False)

    def test_unfinished_bar_is_excluded(self):
        before = calculate_features(self.frame, NOW, self.rules)
        extra = self.frame.iloc[-1].copy()
        extra["timestamp"] = NOW.floor("5min")
        extra["close"], extra["high"] = 10000, 10000
        frame = pd.concat([self.frame, extra.to_frame().T], ignore_index=True)
        frame.attrs = self.frame.attrs.copy()
        after = calculate_features(frame, NOW, self.rules)
        self.assertEqual(before, after)

    def test_gap_removes_session_features_and_blocks(self):
        frame = self.frame.drop(self.frame[self.frame.timestamp.dt.date == NOW.date()].index[0])
        context = calculate_features(frame, NOW, self.rules)["intraday"]
        self.assertIsNone(context["vwap"])
        self.assertIsNone(context["opening_range_high"])
        self.assertTrue(context["blockers"])

    def test_zero_volume_and_flat_prices_are_finite(self):
        self.frame["volume"] = 0
        for key in ("open", "high", "low", "close"):
            self.frame[key] = 100
        result = calculate_features(self.frame, NOW, self.rules)
        self.assertEqual(result["rsi"], 50)
        self.assertEqual(result["intraday"]["adx"], 0)
        self.assertIsNone(result["intraday"]["vwap"])
        self.assertIsNone(result["intraday"]["relative_volume"])
        self.assertEqual(result["preliminary_signal"], "WAIT")
        json.dumps(result, allow_nan=False)

    def test_bad_data_rejected(self):
        for mutation in ("duplicate", "timezone", "ohlc", "negative_volume", "nan", "future"):
            with self.subTest(mutation=mutation):
                frame = self.frame.copy()
                if mutation == "duplicate":
                    frame.loc[0, "timestamp"] = frame.loc[1, "timestamp"]
                elif mutation == "timezone":
                    frame["timestamp"] = frame.timestamp.dt.tz_localize(None)
                elif mutation == "ohlc":
                    frame.loc[0, "high"] = 1
                elif mutation == "negative_volume":
                    frame.loc[0, "volume"] = -1
                elif mutation == "nan":
                    frame.loc[0, "close"] = float("nan")
                else:
                    frame.loc[0, "timestamp"] = NOW + pd.Timedelta(days=1)
                with self.assertRaises(ValueError):
                    calculate_features(frame, NOW, self.rules)

    def test_stale_and_closed_market_block(self):
        context = calculate_features(self.frame, NOW + pd.Timedelta(days=1), self.rules)["intraday"]
        self.assertTrue(any("stale" in text for text in context["blockers"]))
        self.assertTrue(any("Outside" in text for text in context["blockers"]))

    def test_rvol_excludes_current_session(self):
        self.frame.loc[self.frame.index[-1], "volume"] = 300
        result = calculate_features(self.frame, NOW, self.rules)
        self.assertEqual(result["intraday"]["relative_volume"], 3)

    def test_insufficient_rvol_history_is_unknown(self):
        frame = self.frame[self.frame.timestamp.dt.date >= pd.Timestamp("2026-10-20").date()]
        context = calculate_features(frame, NOW, self.rules)["intraday"]
        self.assertIsNone(context["relative_volume"])
        self.assertTrue(any("volume history" in reason for reason in context["blockers"]))

    def test_trend_candidate_requires_all_conditions(self):
        self.rules["intraday"]["min_relative_volume"] = 1
        self.rules["intraday"]["max_vwap_distance_atr"] = 100
        self.rules["filters"]["avoid_rsi_above"] = 100
        result = calculate_features(self.frame, NOW, self.rules)
        self.assertEqual(result["preliminary_signal"], "BUY")
        self.rules["intraday"]["min_adx"] = 101
        self.assertEqual(calculate_features(self.frame, NOW, self.rules)["preliminary_signal"], "WAIT")

    def test_wilder_sma_seed(self):
        values = _wilder(pd.Series([1., 2., 3., 4.]), 3)
        self.assertTrue(pd.isna(values.iloc[1]))
        self.assertEqual(values.iloc[2], 2)
        self.assertAlmostEqual(values.iloc[3], 2 + 2 / 3)


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.rules = load_rules()
        self.ind = {"symbol": "TEST", "rsi": 60, "macd_momentum": "BULLISH",
                    "fundamentals": {"blockers": [], "event_status": "REVIEWED",
                                     "events_reviewed_at": "2026-10-23T09:00:00+05:30", "events": []},
                    "intraday": {"setup": "BUY", "blockers": [],
                                 "completed_bar_end": "2026-10-23T11:00:00+05:30", "timeframe_minutes": 5}}
        self.result = {"signal": "BUY", "confidence": 80, "entry": 100, "stop_loss": 99,
                       "target": 102, "risk_reward": "1:100", "reasoning": "Test"}
        self.clock = patch.object(ai, "market_now", side_effect=lambda value=None: market_now(NOW if value is None else value))
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def apply(self):
        return ai._apply_rule_filters(copy.deepcopy(self.result), self.ind, self.rules)

    def test_recomputes_ratio(self):
        self.assertEqual(self.apply()["risk_reward"], "1:2.00")
        self.result["target"] = 100.2
        self.assertEqual(self.apply()["signal"], "WAIT")

    def test_model_cannot_override_setup(self):
        self.ind["intraday"]["setup"] = "WAIT"
        self.assertEqual(self.apply()["signal"], "WAIT")

    def test_event_and_missing_context_block(self):
        self.ind["fundamentals"]["blockers"] = ["EVENTS_MISSING: review required"]
        self.assertEqual(self.apply()["signal"], "WAIT")
        self.rules["intraday"]["require_event_review"] = False
        self.assertEqual(self.apply()["signal"], "BUY")
        self.ind["fundamentals"]["blockers"] = ["EVENT_BLACKOUT: earnings"]
        self.assertEqual(self.apply()["signal"], "WAIT")

    def test_invalid_numbers_and_geometry(self):
        for key, value in (("confidence", "high"), ("confidence", float("nan")), ("entry", 0),
                           ("entry", True), ("target", 99), ("stop_loss", 101), ("signal", "HOLD")):
            with self.subTest(key=key, value=value):
                original = self.result.copy()
                self.result[key] = value
                result = self.apply()
                self.assertEqual(result["signal"], "WAIT")
                self.assertIsNone(result["entry"])
                self.result = original

    def test_wait_clears_levels(self):
        self.result["signal"] = "WAIT"
        self.assertIsNone(self.apply()["entry"])

    def test_review_and_event_window_rechecked_after_model(self):
        self.ind["fundamentals"]["events_reviewed_at"] = "2026-10-22T10:00:00+05:30"
        self.assertEqual(self.apply()["signal"], "WAIT")
        self.rules["intraday"]["require_event_review"] = False
        self.ind["fundamentals"]["events"] = [
            {"at": "2026-10-23T12:00:00+05:30", "importance": "HIGH", "title": "Results"}
        ]
        self.assertEqual(self.apply()["signal"], "WAIT")


class IntegrationTests(unittest.TestCase):
    def test_batch_and_single_prompts_include_fundamentals_and_persist(self):
        features = calculate_features(candles(), NOW)
        result = {"symbol": "TEST", "signal": "WAIT", "confidence": 0, "reasoning": "Test",
                  "indicators_summary": "Test", "news_sentiment": "NEUTRAL"}
        fundamental = {"status": "MISSING", "blockers": ["EVENTS_MISSING: no review"]}
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            def persist(*args):
                return save_evidence(*args, db_path=db)
            with patch.object(ai, "load_context", return_value=fundamental), patch.object(ai, "load_institutional_context", return_value={"status": "MISSING"}), patch.object(ai, "save_evidence", side_effect=persist) as save, patch.object(ai, "_call_model", side_effect=[json.dumps({"TEST": result}), json.dumps(result)]) as call:
                batch = ai.analyze_all_at_once({"TEST": features}, fetch_news=False)
                single = ai.analyze(features, fetch_news=False)
            self.assertEqual(batch["TEST"]["signal"], "WAIT")
            self.assertEqual(single["signal"], "WAIT")
            self.assertEqual(save.call_count, 2)
            self.assertTrue(all("EVENTS_MISSING" in item.args[0] for item in call.call_args_list))
            self.assertEqual(features["fundamentals"], fundamental)
            self.assertEqual(features["institutions"]["status"], "MISSING")
            self.assertEqual(single["decision_trace"]["final_signal"], "WAIT")

    def test_dashboard_renders_methodology_and_offline_evidence(self):
        from streamlit.testing.v1 import AppTest
        from stocktrading import config, data_fetcher, trade_journal

        with tempfile.TemporaryDirectory() as temp:
            db = str(Path(temp) / "app.db")
            with patch.object(config, "DB_PATH", db), patch.object(data_fetcher, "DB_PATH", db), patch.object(trade_journal, "DB_PATH", db), patch("stocktrading.analysis_evidence.list_runs", return_value=[]):
                app = AppTest.from_file(str(PROJECT_ROOT / "dashboard.py"))
                app.run(timeout=30)
                self.assertEqual(len(app.exception), 0, str(app.exception))
                app.session_state["offline_indicators"] = calculate_features(candles(), NOW)
                traced = ai._apply_rule_filters(
                    {"signal": "WAIT", "confidence": 0, "reasoning": "No eligible setup"},
                    app.session_state["offline_indicators"], load_rules(),
                )
                app.session_state["search_result"] = traced
                app.session_state["search_ind"] = app.session_state["offline_indicators"]
                app.run(timeout=30)
                self.assertEqual(len(app.exception), 0, str(app.exception))
                self.assertTrue(any(tab.label == "Research papers" for tab in app.tabs))
                self.assertTrue(any(tab.label == "Institutions" for tab in app.tabs))
                self.assertTrue(any(tab.label == "Model setup" for tab in app.tabs))

    def test_upstox_merges_endpoints_and_preserves_metadata(self):
        responses = []
        for stamp in ("2026-10-22T15:25:00+05:30", "2026-10-23T09:15:00+05:30"):
            response = Mock()
            response.json.return_value = {"status": "success", "data": {"candles": [[stamp, 100, 101, 99, 100, 500, 0]]}}
            responses.append(response)
        with patch("stocktrading.data_fetcher.get_instrument_key", return_value="NSE_EQ|TEST"), patch("stocktrading.data_fetcher.requests.get", side_effect=responses) as get:
            result = fetch_candles("TEST", "not-a-real-token")
        self.assertEqual(len(result), 2)
        self.assertEqual(result.attrs["timeframe_minutes"], 5)
        self.assertIn("/intraday/", get.call_args_list[1].args[0])
        self.assertTrue(all(call.kwargs["timeout"] == 20 for call in get.call_args_list))

    def test_audit_includes_research_and_fundamentals(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "audit.db"
            record = save_evidence({"TEST": {"fundamentals": {"status": "MISSING"}}}, None, load_rules(), "exact prompt", {}, db)
            saved = load_run(record, db)
            self.assertEqual(saved["prompt"], "exact prompt")
            self.assertIn("lo-2000", {paper["id"] for paper in saved["research_basis"]})
            self.assertEqual(saved["indicators"]["TEST"]["fundamentals"]["status"], "MISSING")


if __name__ == "__main__":
    unittest.main()
