import unittest

from attendance import Attendance, demo, summarize


class AttendanceTests(unittest.TestCase):
    def row(self, days=20, present=18, district="D", school="S", student="1"):
        return Attendance(district, school, student, "2026-09", days, present)

    def run_rows(self, rows):
        return summarize(rows, district="D", allowed_schools=frozenset({"S"}))

    def test_weighted_rate_not_average(self):
        result = self.run_rows([self.row(), self.row(10, 10, student="2")])
        metric = result["metrics"][0]
        self.assertEqual(metric["enrolled_days"], 30)
        self.assertEqual(metric["present_days"], 28)
        self.assertAlmostEqual(metric["attendance_rate"], 28 / 30)

    def test_scope_before_aggregation(self):
        result = self.run_rows([self.row(), self.row(district="OTHER"),
                                self.row(school="OTHER")])
        self.assertEqual(result["selected_records"], 1)
        self.assertEqual(result["metrics"][0]["present_days"], 18)

    def test_duplicate_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.run_rows([self.row(), self.row()])

    def test_bad_counts_rejected(self):
        for days, present in [(20, 21), (-1, 0), (20, -1), (True, 1), (20, 18.0)]:
            with self.subTest(days=days, present=present), self.assertRaises(ValueError):
                self.run_rows([self.row(days, present)])

    def test_zero_and_empty(self):
        self.assertIsNone(self.run_rows([self.row(0, 0)])["metrics"][0]["attendance_rate"])
        self.assertEqual(self.run_rows([])["metrics"], [])

    def test_deterministic_source_hash(self):
        rows = [self.row(), self.row(student="2")]
        self.assertEqual(self.run_rows(rows), self.run_rows(list(reversed(rows))))

    def test_no_scope_refused(self):
        with self.assertRaises(ValueError):
            summarize([], district="D", allowed_schools=frozenset())

    def test_demo_no_student_identifiers(self):
        result = demo()
        self.assertTrue(result["sample_data"])
        self.assertEqual(result["selected_records"], 3)
        self.assertNotIn("fictional", str(result))


if __name__ == "__main__":
    unittest.main()
