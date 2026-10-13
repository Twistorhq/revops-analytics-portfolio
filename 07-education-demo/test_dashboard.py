import re
import unittest

from dashboard import render
from importer import demo_csv, demo_mapping, import_csv


def demo_rows():
    return import_csv(demo_csv(), demo_mapping()).accepted


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.schools = frozenset({"North", "South", "East", "West"})
        self.page = render(demo_rows(), district="DEMO",
                           allowed_schools=self.schools,
                           title="Attendance overview")

    def test_synthetic_label_present(self):
        self.assertIn("SYNTHETIC SAMPLE DATA", self.page)

    def test_filters_cover_all_schools_and_periods(self):
        for school in ("North", "South", "East", "West"):
            self.assertIn(f'<option value="{school}">{school}</option>',
                          self.page)
        for period in ("2026-09", "2026-10", "2026-11"):
            self.assertIn(f'<option value="{period}">{period}</option>',
                          self.page)

    def test_twelve_metric_rows_with_filter_attributes(self):
        rows = re.findall(r'<tr data-school="([^"]+)" data-period="([^"]+)">',
                          self.page)
        self.assertEqual(len(rows), 12)
        self.assertEqual({s for s, _ in rows},
                         {"North", "South", "East", "West"})
        self.assertEqual({p for _, p in rows},
                         {"2026-09", "2026-10", "2026-11"})

    def test_headline_rate_is_weighted(self):
        rows = demo_rows()
        enrolled = sum(r.enrolled_days for r in rows)
        present = sum(r.present_days for r in rows)
        expected = f"{present / enrolled * 100:.1f}%"
        self.assertIn(f'<div class="v">{expected}</div>', self.page)

    def test_no_student_ids_leak(self):
        self.assertNotIn("synth-", self.page)

    def test_district_scope_shown(self):
        self.assertIn("District scope: DEMO", self.page)

    def test_empty_scope_renders(self):
        page = render([], district="DEMO", allowed_schools=self.schools)
        self.assertIn("SYNTHETIC SAMPLE DATA", page)
        self.assertIn("n/a", page)


if __name__ == "__main__":
    unittest.main()
