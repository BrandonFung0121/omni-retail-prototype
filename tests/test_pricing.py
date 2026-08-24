import unittest

from pricing import apply_discount


class TestApplyDiscount(unittest.TestCase):
    def test_no_discount(self):
        self.assertEqual(apply_discount(100, 0), 100)

    def test_half_off(self):
        self.assertEqual(apply_discount(100, 50), 50)

    def test_full_discount(self):
        self.assertEqual(apply_discount(100, 100), 0)

    def test_negative_percent_raises(self):
        with self.assertRaises(ValueError):
            apply_discount(100, -10)

    def test_over_100_percent_raises(self):
        with self.assertRaises(ValueError):
            apply_discount(100, 150)


if __name__ == "__main__":
    unittest.main()
