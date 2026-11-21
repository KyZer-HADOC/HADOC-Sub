import unittest

from app import (
    cloudflare_model_endpoint,
    extract_cloudflare_translation,
    parse_json_response,
    parse_retry_seconds,
)


class ApiHelperTests(unittest.TestCase):
    def test_parse_retry_after_integer(self):
        self.assertEqual(parse_retry_seconds({"Retry-After": "3"}), 3)

    def test_parse_token_reset_duration(self):
        self.assertEqual(parse_retry_seconds({"x-ratelimit-reset-tokens": "6.7s"}), 6)

    def test_parse_request_reset_duration(self):
        self.assertEqual(parse_retry_seconds({"x-ratelimit-reset-requests": "1m2s"}), 62)

    def test_unknown_retry_header(self):
        self.assertIsNone(parse_retry_seconds({}))

    def test_parse_json_response(self):
        result = parse_json_response('{"translations":[{"index":1,"text":"හෙලෝ"}]}')
        self.assertEqual(result["translations"][0]["text"], "හෙලෝ")

    def test_cloudflare_translation_response(self):
        response = {
            "success": True,
            "result": {"translated_text": "ඔයාට කොහොමද?"},
        }
        self.assertEqual(extract_cloudflare_translation(response), "ඔයාට කොහොමද?")

    def test_cloudflare_translation_rejects_missing_text(self):
        with self.assertRaises(ValueError):
            extract_cloudflare_translation({"success": True, "result": {}})

    def test_cloudflare_endpoint(self):
        self.assertEqual(
            cloudflare_model_endpoint(
                "https://api.cloudflare.com/client/v4/accounts/abc/ai/run/",
                "@cf/meta/m2m100-1.2b",
            ),
            "https://api.cloudflare.com/client/v4/accounts/abc/ai/run/@cf/meta/m2m100-1.2b",
        )


if __name__ == "__main__":
    unittest.main()
