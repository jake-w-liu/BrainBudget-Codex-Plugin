from __future__ import annotations

import unittest

import mathops


class MathOpsTests(unittest.TestCase):
    def test_add(self) -> None:
        self.assertEqual(mathops.add(2, 3), 5)

    def test_subtract(self) -> None:
        self.assertEqual(mathops.subtract(9, 4), 5)


if __name__ == "__main__":
    unittest.main()
