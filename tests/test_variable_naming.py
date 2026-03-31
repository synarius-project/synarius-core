import sys
import unittest
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from synarius_core.variable_naming import (  # noqa: E402
    InvalidVariableNameError,
    validate_pin_name,
    validate_python_variable_name,
)


class VariableNamingTest(unittest.TestCase):
    def test_strips_and_accepts_identifier(self) -> None:
        self.assertEqual(validate_python_variable_name("  foo  "), "foo")

    def test_rejects_empty(self) -> None:
        with self.assertRaises(InvalidVariableNameError):
            validate_python_variable_name("")
        with self.assertRaises(InvalidVariableNameError):
            validate_python_variable_name("   ")

    def test_rejects_non_identifier(self) -> None:
        with self.assertRaises(InvalidVariableNameError):
            validate_python_variable_name("1bad")
        with self.assertRaises(InvalidVariableNameError):
            validate_python_variable_name("no-hyphen")

    def test_rejects_keyword(self) -> None:
        with self.assertRaises(InvalidVariableNameError):
            validate_python_variable_name("class")

    def test_pin_name_allows_keywords_like_in_out(self) -> None:
        self.assertEqual(validate_pin_name("in"), "in")
        self.assertEqual(validate_pin_name("out"), "out")


if __name__ == "__main__":
    unittest.main()
