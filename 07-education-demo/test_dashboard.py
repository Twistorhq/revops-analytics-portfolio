import re
import unittest

from dashboard import render
from importer import (
    DISTRICT_SCHOOL_NAMES,
    demo_district_csv,
    demo_mapping,
    import_csv,
)


def demo_rows():
    return import_csv(demo_district_csv(), demo_mapping()).accepted


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.page = render(
            demo_rows(),
            district="NKC-DEMO",
            allowed_schools=DISTRICT_SCHOOL_NAMES,
            title="Attendance overview",
        )

    def test_synthetic_label_present(self):
        self.assertIn("SYNTHETIC SAMPLE DATA", self.page)

    def test_filters_cover_all_schools_and_periods(self):
        for school in DISTRICT_SCHOOL_NAMES:
            self.assertIn(f'<option value="{school}">{school}</option>', self.page)
        for period in ("2026-09", "2026-10", "2026-11"):
            self.assertIn(f'<option value="{period}">{period}</option>', self.page)

    def test_metric_rows_with_filter_attributes(self):
        rows = re.findall(
            r'<tr data-school="([^"]+)" data-period="([^"]+)">', self.page
        )
        # 8 schools x 3 periods = 24 rows: 23 data + 1 explicit gap row
        self.assertEqual(len(rows), 24)
        self.assertEqual({s for s, _ in rows}, set(DISTRICT_SCHOOL_NAMES))
        self.assertEqual({p for _, p in rows}, {"2026-09", "2026-10", "2026-11"})

    def test_data_gap_renders_explicitly(self):
        self.assertIn("No data reported", self.page)
        self.assertIn('<span class="flag gap">Data gap</span>', self.page)
        # the gap row still carries filter attributes
        self.assertIn('data-school="Westfield Middle" data-period="2026-10"', self.page)

    def test_headline_rate_is_weighted(self):
        rows = demo_rows()
        enrolled = sum(r.enrolled_days for r in rows)
        present = sum(r.present_days for r in rows)
        expected = f"{present / enrolled * 100:.1f}%"
        self.assertIn(f'<div class="hero-num">{expected}</div>', self.page)

    def test_no_student_ids_leak(self):
        self.assertNotIn("synth-", self.page)

    def test_district_scope_shown(self):
        self.assertIn("District scope: NKC-DEMO", self.page)

    def test_empty_scope_renders(self):
        page = render([], district="NKC-DEMO", allowed_schools=DISTRICT_SCHOOL_NAMES)
        self.assertIn("SYNTHETIC SAMPLE DATA", page)
        self.assertIn("n/a", page)

    def test_trend_chart_present(self):
        self.assertIn("<svg", self.page)
        self.assertIn("Trend by period", self.page)
        # district line is drawn; gaps never interpolate (no path bridges Oct)
        self.assertIn('stroke="#0f766e"', self.page)

    def test_methodology_documents_math(self):
        self.assertIn("How these numbers are built", self.page)
        self.assertIn("never computed by averaging percentages", self.page)
        self.assertIn("zero enrolled-day denominator", self.page)

    def test_small_school_flagged(self):
        # Summit Alternative has 14 students: small-n flag must show
        self.assertIn("Small n", self.page)

    def test_demo_district_csv_deterministic(self):
        self.assertEqual(demo_district_csv(), demo_district_csv())

    def test_no_ai_tells_in_markup(self):
        # Impeccable floor: no gradients, no emoji-as-UI, no lorem filler
        lowered = self.page.lower()
        self.assertNotIn("linear-gradient", lowered)
        self.assertNotIn("radial-gradient", lowered)
        self.assertNotIn("lorem", lowered)


if __name__ == "__main__":
    unittest.main()
