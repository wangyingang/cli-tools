import unittest

from subx.text import character_error_rate, normalize_text, text_similarity, word_error_rate


class TextTests(unittest.TestCase):
    def test_normalize_text(self) -> None:
        self.assertEqual(normalize_text("  A　B  \n C "), "A B C")

    def test_text_similarity(self) -> None:
        self.assertEqual(text_similarity("hello world", "hello  world"), 1.0)

    def test_error_rates(self) -> None:
        self.assertEqual(character_error_rate("abcd", "abce"), 0.25)
        self.assertEqual(word_error_rate("hello brave world", "hello world"), 0.5)


if __name__ == "__main__":
    unittest.main()
