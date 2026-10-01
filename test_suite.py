import json
import os
import unittest
from unittest.mock import patch, MagicMock
import requests

# Import components from app
import app

class TestGroqKeyRotation(unittest.TestCase):
    def test_key_rotation_on_429(self):
        """Verify that on HTTP 429, key manager advances to the next key and retries."""
        os.environ["GROQ_API_KEYS"] = "gsk_first_key_1111,gsk_second_key_2222"
        mgr = app.GroqKeyManager()
        self.assertEqual(mgr.current_idx, 0)
        self.assertEqual(mgr.get_current_key(), "gsk_first_key_1111")
        
        # Rotate
        mgr.rotate_key()
        self.assertEqual(mgr.current_idx, 1)
        self.assertEqual(mgr.get_current_key(), "gsk_second_key_2222")

        # Rotate again (wraps around)
        mgr.rotate_key()
        self.assertEqual(mgr.current_idx, 0)
        self.assertEqual(mgr.get_current_key(), "gsk_first_key_1111")

    @patch("requests.post")
    def test_call_groq_api_recovers_after_429(self, mock_post):
        """Simulate 429 on first key, then 200 on second key."""
        os.environ["GROQ_API_KEYS"] = "gsk_key_rate_limited,gsk_key_working"
        app.key_manager = app.GroqKeyManager()

        # Mock first response: 429
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.text = '{"error": {"message": "Rate limit exceeded"}}'

        # Mock second response: 200
        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "reply": "నమస్కారం అమ్మా",
                        "docs": [],
                        "place": ""
                    })
                }
            }]
        }

        mock_post.side_effect = [resp_429, resp_200]

        result = app.call_groq_api("/chat/completions", method="POST", json_data={})
        self.assertIn("choices", result)
        self.assertEqual(mock_post.call_count, 2)
        # Verify headers used second key
        second_call_headers = mock_post.call_args_list[1][1]["headers"]
        self.assertEqual(second_call_headers["Authorization"], "Bearer gsk_key_working")

    @patch("requests.post")
    def test_all_keys_exhausted_raises_error(self, mock_post):
        """Verify clear error when all keys fail with 429."""
        os.environ["GROQ_API_KEYS"] = "gsk_key_1,gsk_key_2"
        app.key_manager = app.GroqKeyManager()

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.text = '{"error": "rate limit"}'
        mock_post.return_value = resp_429

        with self.assertRaises(RuntimeError) as ctx:
            app.call_groq_api("/chat/completions", method="POST", json_data={})
        self.assertIn("All Groq API keys exhausted", str(ctx.exception))

class TestBackendEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()

    def test_get_index(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("సఖి", html)

    def test_tts_endpoint(self):
        res = self.client.post("/api/tts", json={"text": "నమస్కారం అమ్మా", "lang": "te"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "audio/mpeg")

    def test_tts_missing_text(self):
        res = self.client.post("/api/tts", json={"text": ""})
        self.assertEqual(res.status_code, 400)

class TestDetectionAndPurity(unittest.TestCase):
    def test_detect_lang_keywords(self):
        # Telugu keywords
        self.assertEqual(app.detect_lang("నమస్కారం అమ్మా", "en"), "te")
        self.assertEqual(app.detect_lang("Hello namaskaram", "en"), "te")
        
        # Tamil keywords
        self.assertEqual(app.detect_lang("வணக்கம்", "en"), "ta")
        self.assertEqual(app.detect_lang("Vanakam amma", "en"), "ta")
        
    def test_detect_lang_whisper_fallback(self):
        # No keywords, but whisper guessed it
        self.assertEqual(app.detect_lang("అవును", "te"), "te")
        self.assertEqual(app.detect_lang("ஆமாம்", "ta"), "ta")
        
    def test_detect_lang_hallucination_prevention(self):
        # Empty text shouldn't return a language
        self.assertIsNone(app.detect_lang("", "te"))
        self.assertIsNone(app.detect_lang(" ", "ta"))

    def test_script_purity(self):
        # Telugu
        self.assertTrue(app.is_script_pure("నమస్కారం అమ్మా. ఎలా ఉన్నారు?", "te"))
        # Fails purity because of English letters
        self.assertFalse(app.is_script_pure("నమస్కారం అమ్మా. Hello?", "te"))
        # Fails purity because of Tamil letters
        self.assertFalse(app.is_script_pure("నమస్కారం வணக்கம்", "te"))
        
        # Tamil
        self.assertTrue(app.is_script_pure("வணக்கம் அம்மா, நான் சகி.", "ta"))
        self.assertFalse(app.is_script_pure("வணக்கம் Hello", "ta"))

if __name__ == "__main__":
    unittest.main()
