import io
import unittest
from contextlib import redirect_stdout

import compare_junit_reports as mod


class PrintDifferencesTest(unittest.TestCase):
    def test_print_differences_uses_report_timestamps(self):
        report = {
            "first": {"file": "D:/tmp/junit_interoperability_report_2026-08-30-06_18_47.xml"},
            "second": {"file": "D:/tmp/junit_interoperability_report_2026-08-30-16_15_12.xml"},
            "added": [],
            "removed": [],
            "changed": [
                {
                    "test": "suite / case",
                    "differences": {"status": {"first": "failure", "second": "passed"}},
                }
            ],
        }

        output = io.StringIO()
        with redirect_stdout(output):
            mod.print_differences(report)

        text = output.getvalue()
        self.assertIn("- 2026-08-30-06_18_47: failure", text)
        self.assertIn("+ 2026-08-30-16_15_12: passed", text)


if __name__ == "__main__":
    unittest.main()
