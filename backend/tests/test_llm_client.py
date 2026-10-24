import os
import unittest
from unittest import mock

import httpx

from app.services import llm_client, rag_generation


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}

    def json(self):
        return self._body


OK = FakeResponse(200, {"choices": [{"message": {"content": "  Délai : 48 heures. Source : Procédure achats.  "}}]})
SOURCES = [{"title": "Procédure achats", "source": "achats.pdf (p. 2)", "excerpt": "Le délai est de 48 heures."}]


class LLMClientTests(unittest.TestCase):
    def setUp(self):
        llm_client.reset_cooldown()
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for k in ("LLM_PROVIDER", "RAG_LLM_BASE_URL", "RAG_LLM_MODEL", "RAG_LLM_API_KEY", "RAG_LLM_TIMEOUT"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.env.stop()

    def test_default_is_ollama_without_key(self):
        cfg = llm_client.get_config()
        self.assertEqual(cfg["provider"], "ollama")
        self.assertTrue(cfg["base_url"].endswith(":11434/v1"))
        with mock.patch.object(httpx, "post", return_value=OK) as post:
            answer = rag_generation.generer_reponse("délai ?", SOURCES, "fr")
        self.assertIn("48 heures", answer)
        self.assertNotIn("Authorization", post.call_args.kwargs["headers"])

    def test_openai_without_key_is_disabled(self):
        os.environ["LLM_PROVIDER"] = "openai"
        self.assertIsNone(llm_client.get_config())
        self.assertIsNone(rag_generation.generer_reponse("q", SOURCES, "fr"))

    def test_provider_none_disables_llm(self):
        os.environ["LLM_PROVIDER"] = "none"
        self.assertIsNone(rag_generation.generer_reponse("q", SOURCES, "fr"))

    def test_legacy_openai_config_still_works(self):
        os.environ.update({"RAG_LLM_BASE_URL": "https://api.openai.com/v1", "RAG_LLM_MODEL": "gpt-4o-mini", "RAG_LLM_API_KEY": "sk-test"})
        with mock.patch.object(httpx, "post", return_value=OK) as post:
            self.assertIsNotNone(rag_generation.generer_reponse("q", SOURCES, "fr"))
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer sk-test")

    def _fail(self, response=None, exc=None):
        with mock.patch.object(httpx, "post", return_value=response, side_effect=exc):
            with self.assertRaises(llm_client.LLMError) as ctx:
                llm_client.chat_completion([{"role": "user", "content": "x"}])
        return ctx.exception

    def test_error_classification(self):
        self.assertEqual(self._fail(FakeResponse(401)).kind, "auth")
        llm_client.reset_cooldown()
        self.assertEqual(self._fail(FakeResponse(429, {"error": {"code": "insufficient_quota"}})).kind, "quota")
        llm_client.reset_cooldown()
        self.assertEqual(self._fail(FakeResponse(429, {"error": {"code": "rate_limit_exceeded"}})).kind, "rate_limit")
        llm_client.reset_cooldown()
        self.assertEqual(self._fail(FakeResponse(404)).kind, "model_missing")
        llm_client.reset_cooldown()
        self.assertEqual(self._fail(exc=httpx.TimeoutException("t")).kind, "timeout")
        self.assertEqual(self._fail(exc=httpx.TransportError("c")).kind, "unreachable")

    def test_cooldown_avoids_repeated_calls_after_quota_error(self):
        quota = FakeResponse(429, {"error": {"code": "insufficient_quota"}})
        with mock.patch.object(httpx, "post", return_value=quota) as post:
            for _ in range(3):
                self.assertIsNone(rag_generation.generer_reponse("q", SOURCES, "fr"))
        self.assertEqual(post.call_count, 1)

    def test_secrets_never_logged(self):
        os.environ.update({"LLM_PROVIDER": "openai", "RAG_LLM_API_KEY": "sk-SECRET-123"})
        leaky = FakeResponse(401, {"error": {"message": "Incorrect API key provided: sk-SECRET-123"}})
        with self.assertLogs("erp.llm", level="WARNING") as logs, mock.patch.object(httpx, "post", return_value=leaky):
            self.assertIsNone(rag_generation.generer_reponse("q", SOURCES, "fr"))
        self.assertNotIn("SECRET", "\n".join(logs.output))

    def test_empty_sources_skip_llm(self):
        with mock.patch.object(httpx, "post") as post:
            self.assertIsNone(rag_generation.generer_reponse("q", [], "fr"))
        post.assert_not_called()


class FallbackTests(unittest.TestCase):
    def test_multiple_sources_listed_and_not_presented_as_summary(self):
        from app.services.rag_response import reponse_rag_concise
        sources = [{"title": f"Doc {i}", "source": f"d{i}.pdf", "excerpt": f"Fait numéro {i}. Suite."} for i in range(5)]
        answer = reponse_rag_concise(sources, "fr")
        self.assertIn("synthèse IA indisponible", answer)
        self.assertEqual(answer.count("Source :"), 3)


if __name__ == "__main__":
    unittest.main()
