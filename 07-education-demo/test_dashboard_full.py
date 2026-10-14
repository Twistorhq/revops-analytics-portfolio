# Prepared by Twistor Holdings LLC
# Tests for the presentation dashboard (TW-493 phase 2): callouts, custom
# metrics, model overlays. HTML builders are tested with injected data so
# these tests never need sklearn/lifelines.

import unittest

from callouts import Callout
from dashboard import (
    SURVIVAL_OVERLAY,
    _callout_to_dict,
    _kpi_cards_html,
    _model_overlays_html,
    _plain_kicker,
    _sev_class,
    _trend_strip_html,
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
        "template_id": "early_warning",
        "kicker": "Antioch Middle School &mdash; early warning",
        "big_html": "74.3% <small>on pace</small>",
        "line_html": "Three in four students on pace.",
        "sev": "sev-high",
    }
]

METRICS_DATA = {
    "blocks": [
        {
            "tag": "Early warning",
            "name": "Chronic absenteeism early warning",
            "formula": "pace = absent/enrolled over first 30 days",
            "plain_html": "Share of students on pace for chronic absence.",
            "why_html": "Arrives in time to act.",
            "headline_html": "<strong>Antioch</strong> at <strong>74.3%</strong>.",
            "big_html": "74.3%",
            "big_label": "of students on pace",
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
    def test_trend_strip_shows_trend_callouts_only(self):
        trend = {
            "template_id": "movement",
            "kicker": "Antioch &mdash; slipping",
            "big_html": "-7.0 pts",
            "line_html": "line",
            "sev": "sev-high",
        }
        metric = {
            "template_id": "early_warning",
            "kicker": "Antioch &mdash; early warning",
            "big_html": "74.3%",
            "line_html": "line",
            "sev": "sev-high",
        }
        page = _trend_strip_html([trend, metric])
        self.assertIn("What changed", page)
        self.assertIn("slipping", page)
        self.assertNotIn("early warning", page)

    def test_trend_strip_empty_without_trend_callouts(self):
        metric = {
            "template_id": "mf_ratio",
            "kicker": "k",
            "big_html": "1.34x",
            "line_html": "line",
            "sev": "sev-med",
        }
        self.assertEqual(_trend_strip_html([metric]), "")
        self.assertEqual(_trend_strip_html([]), "")

    def _co(self, **kw):
        base = {
            "template_id": "movement",
            "school": "Antioch Middle School",
            "metric": "attendance_rate",
            "metric_label": "attendance rate",
            "direction": "down",
            "delta_pts": -7.0,
            "value": 0.87,
            "severity": "high",
            "weight": 7.0,
            "kicker": "engine kicker",
            "big": "-7.0 pts",
            "line": "line",
        }
        base.update(kw)
        return Callout(**base)

    def test_plain_kicker_mapping(self):
        c = self._co(template_id="mf_ratio", direction="up")
        self.assertEqual(
            _plain_kicker(c), "Antioch Middle School — weekends hit hardest"
        )
        c = self._co(template_id="movement", direction="up")
        self.assertEqual(_plain_kicker(c), "Antioch Middle School — improving")
        c = self._co(template_id="early_warning", direction="down")
        self.assertEqual(_plain_kicker(c), "Antioch Middle School — early warning")

    def test_plain_kicker_falls_back_to_engine_text(self):
        c = self._co(template_id="unknown_rule", direction="down")
        self.assertEqual(_plain_kicker(c), "engine kicker")

    def test_severity_color_classes(self):
        self.assertEqual(_sev_class(self._co(severity="high")), "sev-high")
        self.assertEqual(_sev_class(self._co(severity="medium")), "sev-med")
        self.assertEqual(
            _sev_class(
                self._co(severity="info", template_id="recovery", direction="up")
            ),
            "sev-good",
        )
        self.assertEqual(
            _sev_class(
                self._co(
                    severity="info",
                    template_id="threshold_cross",
                    direction="up",
                )
            ),
            "sev-good",
        )
        self.assertEqual(_sev_class(self._co(severity="info")), "sev-info")

    def test_callout_dict_carries_sev_template_and_escapes(self):
        d = _callout_to_dict(self._co(school="A & B Elementary"))
        self.assertEqual(d["sev"], "sev-high")
        self.assertEqual(d["template_id"], "movement")
        self.assertIn("A &amp; B Elementary", d["kicker"])
        self.assertNotIn("A & B Elementary", d["kicker"])

    def test_trend_strip_item_has_severity_class(self):
        d = _callout_to_dict(self._co())
        page = _trend_strip_html([d])
        self.assertIn('class="trend-item sev-high"', page)


class KpiCardTests(unittest.TestCase):
    def test_cards_render_with_number_formula_and_dropdown(self):
        page = _kpi_cards_html(METRICS_DATA["blocks"], [])
        self.assertIn("Chronic absenteeism early warning", page)
        self.assertIn("74.3%", page)
        # formula lives one click away, not front and center
        self.assertIn("How this is calculated", page)
        self.assertIn("<details", page)
        self.assertIn("pace = absent/enrolled over first 30 days", page)
        self.assertIn('class="kpi-grid"', page)
        self.assertIn('class="kpi-card sev-info"', page)

    def test_card_claims_its_metric_callout(self):
        ew = {
            "template_id": "early_warning",
            "kicker": "Antioch &mdash; early warning",
            "big_html": "74.3%",
            "line_html": "7 in 10 on pace &mdash; intervene now.",
            "sev": "sev-high",
        }
        page = _kpi_cards_html(METRICS_DATA["blocks"], [ew])
        self.assertIn("intervene now", page)
        self.assertIn('class="card-callout sev-high"', page)

    def test_trend_callouts_do_not_land_in_cards(self):
        mv = {
            "template_id": "movement",
            "kicker": "Antioch &mdash; slipping",
            "big_html": "-7.0 pts",
            "line_html": "slipped vs Sep.",
            "sev": "sev-high",
        }
        page = _kpi_cards_html(METRICS_DATA["blocks"], [mv])
        self.assertNotIn("slipped vs Sep", page)

    def test_card_tag_carries_severity_color(self):
        b = dict(METRICS_DATA["blocks"][0], severity="sev-high")
        page = _kpi_cards_html([b], [])
        self.assertIn('class="kpi-card sev-high"', page)

    def test_formula_text_is_escaped(self):
        evil = dict(METRICS_DATA["blocks"][0])
        evil["formula"] = "<script>alert(1)</script>"
        page = _kpi_cards_html([evil], [])
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
            "The trend, first",
            "Five numbers worth",
            "What happens next",
            "Every school, every period",
            "How these numbers are built",
        ]
        idx = [self.page.find(s) for s in order]
        self.assertTrue(all(i >= 0 for i in idx), idx)
        self.assertEqual(idx, sorted(idx))

    def test_no_jargon_leads_the_page(self):
        # technical terms live in expandable dropdowns, not the main view
        for term in ("C-index", "isotonic", "Concordance index"):
            before = self.page.split("<details")[0]
            self.assertNotIn(term, before)
        self.assertIn("Concordance index", self.page)  # still in the product

    def test_hero_leads_with_chart(self):
        hero_idx = self.page.find("chart-hero")
        cards_idx = self.page.find("Five numbers worth")
        self.assertGreaterEqual(hero_idx, 0)
        self.assertGreater(cards_idx, hero_idx)

    def test_trend_callouts_ride_with_hero_chart(self):
        mv = {
            "template_id": "movement",
            "kicker": "Antioch &mdash; slipping",
            "big_html": "-7.0 pts",
            "line_html": "slipped vs Sep.",
            "sev": "sev-high",
        }
        page = render_full(
            _rows(),
            district="NKC-DEMO",
            allowed_schools=frozenset({"Antioch Middle School", "Staley High School"}),
            callouts=[mv],
            metrics_data=METRICS_DATA,
            logistic_data=LOGISTIC,
            title="Full demo",
        )
        hero_idx = page.find("What changed")
        cards_idx = page.find("Five numbers worth")
        self.assertGreaterEqual(hero_idx, 0)
        self.assertGreater(cards_idx, hero_idx)
        self.assertIn("slipping", page[:cards_idx])

    def test_metric_callout_lands_in_its_card(self):
        # the fixture early_warning callout renders inside the KPI card
        card_idx = self.page.find('class="kpi-card')
        self.assertGreaterEqual(card_idx, 0)
        self.assertIn("Three in four students on pace", self.page[card_idx:])

    def test_wide_table_has_scroll_region(self):
        # the page itself never scrolls sideways
        self.assertIn("table-scroll", self.page)

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
