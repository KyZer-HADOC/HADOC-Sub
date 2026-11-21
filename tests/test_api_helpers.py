import unittest
import urllib.parse

from app import (
    build_google_translate_url,
    build_mymemory_url,
    cloudflare_model_endpoint,
    extract_google_translate_translations,
    extract_cloudflare_translation,
    extract_mymemory_translation,
    split_mymemory_chunks,
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

    def test_mymemory_translation_response(self):
        response = {
            "responseStatus": 200,
            "responseData": {"translatedText": "ඔයාට කොහොමද?"},
        }
        self.assertEqual(extract_mymemory_translation(response), "ඔයාට කොහොමද?")

    def test_mymemory_translation_error(self):
        with self.assertRaises(ValueError):
            extract_mymemory_translation({
                "responseStatus": 403,
                "responseDetails": "Daily quota exceeded",
            })

    def test_mymemory_url_uses_sinhala_and_optional_email(self):
        url = build_mymemory_url(
            "https://api.mymemory.translated.net",
            "Hello world",
            "test@example.com",
            "en-US|si-LK",
        )
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(query["langpair"], ["en-US|si-LK"])
        self.assertEqual(query["de"], ["test@example.com"])
        self.assertEqual(query["q"], ["Hello world"])

    def test_mymemory_url_without_email(self):
        url = build_mymemory_url(
            "https://api.mymemory.translated.net",
            "Hello",
            "",
            "en-US|si-LK",
        )
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertNotIn("de", query)

    def test_mymemory_chunks_respect_utf8_byte_limit(self):
        chunks = split_mymemory_chunks(("ආයුබෝවන් " * 90).strip())
        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk.encode("utf-8")) <= 450 for chunk in chunks))

    def test_google_translate_url_batches_repeated_q_parameters(self):
        url = build_google_translate_url(
            "https://translate.googleapis.com/translate_a/t",
            ["Hello", "How are you?"],
            "en",
            "si",
        )
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(query["client"], ["dict-chrome-ex"])
        self.assertEqual(query["sl"], ["en"])
        self.assertEqual(query["tl"], ["si"])
        self.assertEqual(query["q"], ["Hello", "How are you?"])

    def test_google_translate_response_parses_multiple_lines(self):
        # With an explicit source language, the web endpoint returns plain strings.
        response = ["හෙලෝ", "ඔයාට කොහොමද?"]
        self.assertEqual(
            extract_google_translate_translations(response, 2),
            ["හෙලෝ", "ඔයාට කොහොමද?"],
        )

    def test_google_translate_response_rejects_missing_line(self):
        with self.assertRaises(ValueError):
            extract_google_translate_translations([["හෙලෝ", "en"]], 2)

    def test_google_translate_response_joins_segments(self):
        response = [[[["හෙලෝ", "hello"], [" ලෝකය", " world"]], "en"]]
        self.assertEqual(
            extract_google_translate_translations(response, 1),
            ["හෙලෝ ලෝකය"],
        )


if __name__ == "__main__":
    unittest.main()
