# Prepared by Twistor Holdings LLC
# Tests for the presentation dashboard (TW-493 phase 2): callouts, custom
# metrics, model overlays. HTML builders are tested with injected data so
# these tests never need sklearn/lifelines.

import unittest

from dashboard import (
    SURVIVAL_OVERLAY,
    _callouts_html,
    _custom_metrics_html,
    _model_overlays_html,
    render_full,
)


def _rows():
    # Minimal monthly-grain rows for render_full: 2 schools x 2 periods.
    rows = []
    n = 0
    for school in ("Antioch Middle School", "Staley High School"):
        for period in ("2026-09", "2026-10"):
            n += 1
            rows.append(
                _R(
                    district="NKC-DEMO",
                    school=school,
                    period=period,
                    enrolled=1000,
                    present=900,
                    records=100,
                    sid=n,
                )
            )
    return rows


class _R:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.enrolled_days = kw["enrolled"]
        self.present_days = kw["present"]
        self.student_period_records = kw["records"]


# summarize() is bound into dashboard's namespace at import; the render_full
# tests patch it per-test (never at module scope — that would poison other
# test modules at pytest collection time).
import dashboard

_REAL_SUMMARIZE = dashboard.summarize


def _summarize(rows, district, allowed_schools):
    metrics = []
    for r in rows:
        metrics.append(
            {
                "school": r.school,
                "period": r.period,
                "enrolled_days": r.enrolled_days,
                "present_days": r.present_days,
                "student_period_records": r.student_period_records,
                "attendance_rate": r.present_days / r.enrolled_days,
            }
        )
    return {
        "metrics": metrics,
        "selected_records": len(rows),
        "selected_source_sha256": "ab" * 32,
    }


CALLOUTS = [
    {
        "kicker": "Antioch Middle School &mdash; early warning",
        "big_html": "74.3% <small>on pace</small>",
        "line_html": "Three in four students on pace.",
    }
]

METRICS_DATA = {
    "blocks": [
        {
            "tag": "Metric 1",
            "name": "Chronic absenteeism early warning",
            "formula": "pace = absent/enrolled over first 30 days",
            "why_html": "The predictive version.",
            "headline_html": "<strong>Antioch</strong> at <strong>74.3%</strong>.",
            "table_headers": ["School", "Pct"],
            "table_rows": [("Antioch Middle School", "74.3%")],
        }
    ]
}

LOGISTIC = {
    "auc": 0.779,
    "matched_precision": 0.659,
    "baseline_precision": 0.648,
    "tiers": [
        {"name": "high", "n": 2648},
        {"name": "medium", "n": 4527},
        {"name": "low", "n": 2588},
    ],
}


class CalloutTests(unittest.TestCase):
    def test_callouts_render_named_school_and_number(self):
        page = _callouts_html(CALLOUTS)
        self.assertIn("Antioch Middle School", page)
        self.assertIn("74.3%", page)
        self.assertIn("What the data is saying", page)

    def test_callouts_are_bands_not_cards(self):
        page = _callouts_html(CALLOUTS)
        # editorial pull-quote markup, no card-grid classes
        self.assertIn('class="callout"', page)
        self.assertNotIn("card", page)


class CustomMetricsTests(unittest.TestCase):
    def test_all_blocks_render_with_formula(self):
        page = _custom_metrics_html(METRICS_DATA)
        self.assertIn("Chronic absenteeism early warning", page)
        self.assertIn("pace = absent/enrolled over first 30 days", page)
        self.assertIn('class="metric-block"', page)

    def test_formula_text_is_escaped(self):
        evil = dict(METRICS_DATA["blocks"][0])
        evil["formula"] = "<script>alert(1)</script>"
        page = _custom_metrics_html({"blocks": [evil]})
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)


class ModelOverlayTests(unittest.TestCase):
    def test_logistic_overlay_shows_auc_and_tiers(self):
        page = _model_overlays_html(LOGISTIC, SURVIVAL_OVERLAY)
        self.assertIn("0.779", page)
        self.assertIn("2,648", page)
        self.assertIn("Will they go chronic?", page)

    def test_survival_overlay_labels_provenance(self):
        page = _model_overlays_html(LOGISTIC, SURVIVAL_OVERLAY)
        self.assertIn("0.783", page)
        self.assertIn("When do they cross the line?", page)
        # honest framing: values are from the TW-495 run, not recomputed
        self.assertIn("TW-495", page)

    def test_no_student_ids_in_overlays(self):
        page = _model_overlays_html(LOGISTIC, SURVIVAL_OVERLAY)
        self.assertNotIn("synth-", page)


class RenderFullTests(unittest.TestCase):
    def setUp(self):
        dashboard.summarize = _summarize
        self.addCleanup(setattr, dashboard, "summarize", _REAL_SUMMARIZE)
        self.page = render_full(
            _rows(),
            district="NKC-DEMO",
            allowed_schools=frozenset({"Antioch Middle School", "Staley High School"}),
            callouts=CALLOUTS,
            metrics_data=METRICS_DATA,
            logistic_data=LOGISTIC,
            title="Full demo",
        )

    def test_sections_present_in_order(self):
        order = [
            "What the data is saying",
            "Trend by period",
            "Metrics schools don",
            "Prediction overlays",
            "School performance",
            "How these numbers are built",
        ]
        idx = [self.page.find(s) for s in order]
        self.assertTrue(all(i >= 0 for i in idx), idx)
        self.assertEqual(idx, sorted(idx))

    def test_synthetic_banner_and_attribution(self):
        self.assertIn("SYNTHETIC SAMPLE DATA", self.page)
        self.assertIn("Prepared by Twistor Holdings LLC", self.page)

    def test_model_honest_framing(self):
        self.assertIn("retrain on the", self.page)
        self.assertIn("synthetic", self.page.lower())

    def test_no_student_ids_leak(self):
        self.assertNotIn("synth-", self.page)

    def test_trend_chart_present(self):
        self.assertIn("<svg", self.page)
        self.assertIn("Attendance rate trend by period", self.page)

    def test_mobile_viewport(self):
        self.assertIn('name="viewport"', self.page)


if __name__ == "__main__":
    unittest.main()
