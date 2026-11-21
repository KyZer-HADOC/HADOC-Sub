import unittest

from app import parse_json_response, parse_retry_seconds


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


if __name__ == "__main__":
    unittest.main()
