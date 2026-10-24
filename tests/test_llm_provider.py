import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from stocktrading import llm_provider as llm
from stocktrading.analysis_evidence import save_evidence, load_run
from stocktrading.decision_evidence import evidence_packet
from stocktrading import ai_analyst as ai
from stocktrading.intraday_engine import load_rules
from stocktrading.config import RESOURCE_DIR


def response(payload=None, code=200):
    item = Mock(status_code=code)
    item.json.return_value = payload if payload is not None else {
        "choices": [{"finish_reason": "stop", "message": {"content": '{"signal":"WAIT"}'}}]
    }
    return item


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.settings = llm.get_settings({"LLM_PROVIDER": "nvidia", "NVIDIA_API_KEY": "test-only"})

    def test_defaults_and_secrets_not_in_metadata(self):
        self.assertEqual(llm.get_settings({}).provider, "gemini")
        self.assertEqual(self.settings.model, llm.NVIDIA_MODEL)
        self.assertNotIn("test-only", repr(self.settings))
        self.assertNotIn("test-only", json.dumps(self.settings.metadata()))

    def test_nvidia_uses_non_streaming_final_answer_endpoint(self):
        with patch.object(llm.requests, "request", return_value=response()) as request:
            self.assertEqual(llm.generate_text("evidence", self.settings), '{"signal":"WAIT"}')
        args = request.call_args
        self.assertEqual(args.args, ("POST", llm.NVIDIA_BASE_URL + "/chat/completions"))
        self.assertFalse(args.kwargs["allow_redirects"])
        self.assertEqual(args.kwargs["headers"]["Authorization"], "Bearer test-only")
        body = args.kwargs["json"]
        self.assertFalse(body["stream"])
        self.assertEqual(body["model"], llm.NVIDIA_MODEL)
        self.assertIn("/no_think", body["messages"][0]["content"])
        self.assertNotIn("response_format", body)

    def test_local_server_has_no_nvidia_auth_and_can_request_json(self):
        settings = llm.get_settings({
            "LLM_PROVIDER": "openai_compatible", "LLM_BASE_URL": "http://127.0.0.1:8000/v1",
            "LLM_MODEL": "my-local-model", "LLM_JSON_MODE": "true",
        })
        with patch.object(llm.requests, "request", return_value=response()) as request:
            llm.generate_text("evidence", settings)
        self.assertNotIn("Authorization", request.call_args.kwargs["headers"])
        self.assertEqual(request.call_args.kwargs["json"]["response_format"], {"type": "json_object"})

    def test_no_network_for_missing_key(self):
        with patch.object(llm.requests, "request") as request:
            with self.assertRaisesRegex(ValueError, "NVIDIA_API_KEY"):
                llm.generate_text("evidence", llm.get_settings({"LLM_PROVIDER": "nvidia"}))
        request.assert_not_called()

    def test_model_change_does_not_change_provider(self):
        settings = llm.get_settings({"LLM_PROVIDER": "nvidia", "LLM_MODEL": "nvidia/replacement",
                                     "NVIDIA_API_KEY": "test-only"})
        with patch.object(llm.requests, "request", return_value=response()) as request:
            llm.generate_text("evidence", settings)
        self.assertEqual(request.call_args.kwargs["json"]["model"], "nvidia/replacement")
        self.assertNotIn("/no_think", request.call_args.kwargs["json"]["messages"][0]["content"])

    def test_gemini_dispatch_preserves_json_and_limits(self):
        from google import genai

        candidate = SimpleNamespace(finish_reason="STOP")
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.models.generate_content.return_value = SimpleNamespace(candidates=[candidate], text='{"signal":"WAIT"}')
        settings = llm.get_settings({"GEMINI_API_KEY": "test-only", "LLM_MAX_TOKENS": "2048"})
        with patch.object(genai, "Client", return_value=client) as constructor:
            self.assertEqual(llm.generate_text("evidence", settings), '{"signal":"WAIT"}')
        call = client.models.generate_content.call_args
        self.assertEqual(call.kwargs["model"], "gemini-2.5-flash")
        self.assertEqual(call.kwargs["config"].response_mime_type, "application/json")
        self.assertEqual(call.kwargs["config"].max_output_tokens, 2048)
        self.assertEqual(constructor.call_args.kwargs["http_options"].timeout, 90000)

    def test_temporary_failures_retry_but_unauthorized_does_not(self):
        with patch.object(llm.requests, "request", side_effect=[response(code=429), response(code=503), response()]) as request, patch.object(llm.time, "sleep") as sleep:
            llm.generate_text("evidence", self.settings)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        with patch.object(llm.requests, "request", return_value=response(code=401)) as request:
            with self.assertRaisesRegex(RuntimeError, "401"):
                llm.generate_text("evidence", self.settings)
        self.assertEqual(request.call_count, 1)

    def test_failures_are_not_success_shaped(self):
        for status in (202, 302, 404):
            with self.subTest(status=status), patch.object(llm.requests, "request", return_value=response(code=status)):
                with self.assertRaises(RuntimeError):
                    llm.generate_text("evidence", self.settings)
        for error in (requests.Timeout(), requests.ConnectionError()):
            with patch.object(llm.requests, "request", side_effect=error):
                with self.assertRaises(RuntimeError):
                    llm.generate_text("evidence", self.settings)
        for payload in ({}, {"choices": []}, {"choices": [{"finish_reason": "length"}]},
                        {"choices": [{"finish_reason": "stop", "message": {"reasoning_content": "not a final answer"}}]}):
            with patch.object(llm.requests, "request", return_value=response(payload)):
                with self.assertRaises(ValueError):
                    llm.generate_text("evidence", self.settings)

    def test_model_listing_is_explicit(self):
        with patch.object(llm.requests, "request", return_value=response({"data": [{"id": "model-b"}, {"id": "model-a"}]})) as request:
            self.assertEqual(llm.list_models(self.settings), ["model-a", "model-b"])
        self.assertEqual(request.call_args.args[0], "GET")

    def test_bad_configuration_is_rejected(self):
        for env in (
            {"LLM_PROVIDER": "typo"},
            {"LLM_PROVIDER": "openai_compatible"},
            {"LLM_PROVIDER": "nvidia", "LLM_BASE_URL": "https://different.example/v1"},
            {"LLM_PROVIDER": "openai_compatible", "LLM_MODEL": "model", "LLM_BASE_URL": "http://remote.example/v1"},
            {"LLM_PROVIDER": "openai_compatible", "LLM_MODEL": "model", "LLM_BASE_URL": "https://user:password@example.com/v1"},
            {"LLM_TEMPERATURE": "NaN"}, {"LLM_TIMEOUT_SECONDS": "inf"},
            {"LLM_MAX_TOKENS": "0"}, {"LLM_JSON_MODE": "maybe"},
        ):
            with self.subTest(env=env):
                with self.assertRaises(ValueError):
                    llm.get_settings(env)

    def test_audit_names_selected_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "audit.db"
            with patch.dict(os.environ, {"LLM_PROVIDER": "nvidia", "LLM_MODEL": "nvidia/replacement", "LLM_BASE_URL": ""}):
                saved_id = save_evidence({}, {}, {}, "prompt", {}, db)
            payload = load_run(saved_id, db)
            self.assertEqual(payload["provider"], "nvidia")
            self.assertEqual(payload["model"], "nvidia/replacement")
            self.assertNotIn("api_key", payload["model_configuration"])
            self.assertIn("system_prompt", payload["model_configuration"])

    def test_news_picks_use_selected_model_adapter(self):
        with patch("stocktrading.news_fetcher.fetch_news_for_recommendations", return_value="Public test headline"), patch.object(ai, "_call_model", return_value='{"recommendations": []}') as model:
            result, error = ai.recommend_stocks_from_news()
        self.assertIsNone(error)
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(model.call_args.args[1], "recommendations")


class DecisionTraceTests(unittest.TestCase):
    def test_all_sources_have_reading_scope_and_unique_ids(self):
        papers = json.loads((RESOURCE_DIR / "research_catalog.json").read_text())
        ids = {paper["id"] for paper in papers}
        self.assertEqual(len(ids), len(papers))
        self.assertTrue({"sloan-1996", "dechow-dichev-2002", "piotroski-2000",
                         "bernard-thomas-1989", "kyle-1985", "chan-lakonishok-1995"}.issubset(ids))
        for paper in papers:
            self.assertTrue(all(paper[key] for key in ("verification", "limitations", "implemented", "not_implemented", "url")))

    def test_bad_citations_force_wait_and_preserve_proposal(self):
        indicators = {"symbol": "TEST", "rsi": 50, "intraday": {"setup": "WAIT"}}
        result = {"signal": "BUY", "confidence": 80, "entry": 100, "target": 102, "stop_loss": 99,
                  "evidence_refs": ["invented-source"], "reasoning": "Test"}
        filtered = ai._apply_rule_filters(result, indicators, load_rules())
        self.assertEqual(filtered["signal"], "WAIT")
        self.assertEqual(filtered["decision_trace"]["model_proposal"]["signal"], "BUY")
        self.assertEqual(filtered["decision_trace"]["final_signal"], "WAIT")
        self.assertTrue(any("evidence IDs" in reason for reason in filtered["rule_violations"]))

    def test_institutional_evidence_is_bounded_and_citable(self):
        record = {"evidence_id": "institutional:1", "source_url": "https://example.com",
                  "published_at": "2026-10-24T18:00:00+05:30", "status": "STALE"}
        indicators = {"symbol": "TEST", "institutions": {"deals": {"rows": [
            {**record, "evidence_id": f"institutional:{i}"} for i in range(20)
        ]}}}
        packet = evidence_packet(indicators)
        institution_rows = [row for row in packet if row["part"] == "Institutions"]
        self.assertEqual(len(institution_rows), 10)
        self.assertEqual(institution_rows[0]["value"]["status"], "STALE")
        prompt = ai._evidence_prompt(indicators)
        self.assertIn('"available_rows": 20', prompt)
        self.assertIn('"supplied_rows": 10', prompt)
        self.assertNotIn('"id": "institutional:19"', prompt)


if __name__ == "__main__":
    unittest.main()
