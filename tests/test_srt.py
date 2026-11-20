import unittest

from app import parse_srt


class SrtParserTests(unittest.TestCase):
    def test_parses_multiple_entries_and_preserves_timestamps(self):
        source = (
            "\ufeff1\r\n"
            "00:00:01,000 --> 00:00:02,500\r\n"
            "Hello there!\r\n"
            "\r\n"
            "2\r\n"
            "00:00:03,000 --> 00:00:05,000\r\n"
            "This is line one.\r\n"
            "This is line two.\r\n"
        )
        rows = parse_srt(source)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].number, "1")
        self.assertEqual(rows[0].timing, "00:00:01,000 --> 00:00:02,500")
        self.assertEqual(rows[0].original, "Hello there!")
        self.assertEqual(rows[1].original, "This is line one.\nThis is line two.")

    def test_ignores_invalid_blocks(self):
        source = (
            "not an srt block\n\n"
            "1\n00:00:01,000 --> 00:00:02,000\nValid subtitle\n"
        )
        rows = parse_srt(source)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].original, "Valid subtitle")

    def test_raises_for_invalid_file(self):
        with self.assertRaises(ValueError):
            parse_srt("This file has no subtitle timestamps.")


if __name__ == "__main__":
    unittest.main()
