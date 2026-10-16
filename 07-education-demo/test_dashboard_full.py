# Prepared by Twistor Holdings LLC
# Tests for the presentation dashboard (TW-493 phase 2): callouts, custom
# metrics, model overlays. HTML builders are tested with injected data so
# these tests never need sklearn/lifelines.

import json
import re
import unittest

from callouts import Callout
from dashboard import (
    SURVIVAL_OVERLAY,
    _callout_to_dict,
    _fmt_period,
    _kpi_cards_html,
    _model_overlays_html,
    _place_labels,
    _plain_kicker,
    _sev_class,
    _short_name,
    _trend_strip_html,
    _trend_svg,
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

    def test_cards_use_severity_dot_not_top_strip(self):
        # Justynn: the full-width colored top border screams AI-generated.
        # Severity now reads as a dot + colored kicker text.
        b = dict(METRICS_DATA["blocks"][0], severity="sev-high")
        page = _kpi_cards_html([b], [])
        self.assertIn('class="sev-dot"', page)
        self.assertIn('class="kpi-card sev-high"', page)

    def test_no_ai_candy_strips_in_css(self):
        import dashboard

        css = dashboard.PAGE_CSS + dashboard.PAGE_CSS_EXTRA
        self.assertNotIn("border-top:4px", css)
        self.assertNotIn("border-left:4px", css)

    def test_trend_items_use_severity_dot(self):
        mv = {
            "template_id": "movement",
            "kicker": "Antioch &mdash; slipping",
            "big_html": "-7.0 pts",
            "line_html": "slipped vs Sep.",
            "sev": "sev-high",
        }
        page = _trend_strip_html([mv])
        self.assertIn('class="sev-dot"', page)
        self.assertIn('class="trend-item sev-high"', page)


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

    def test_masthead_is_product_not_placeholder(self):
        # Executive-facing: product header, no internal district code.
        # (The methodology section's Scope line may still name the
        # internal district code — that's honest provenance, not UI.)
        masthead = self.page.split("</header>")[0]
        self.assertIn("Attendance Intelligence", masthead)
        self.assertIn("North Kansas City Schools", masthead)
        self.assertNotIn("NKC-DEMO", masthead)
        self.assertNotIn("student-period records", masthead)


class HelperTests(unittest.TestCase):
    def test_short_name(self):
        self.assertEqual(_short_name("Staley High School"), "Staley HS")
        self.assertEqual(_short_name("Antioch Middle School"), "Antioch MS")
        self.assertEqual(
            _short_name("North Kansas City High School"), "NKC HS"
        )
        self.assertEqual(_short_name("Bell Prairie Elementary"), "Bell Prairie")
        self.assertEqual(_short_name("Golden Oaks Education Center"), "Golden Oaks")

    def test_fmt_period(self):
        self.assertEqual(_fmt_period("2026-09"), "Sep 2026")
        self.assertEqual(_fmt_period("2026-11"), "Nov 2026")
        self.assertEqual(_fmt_period("weird"), "weird")


TWELVE_SCHOOLS = [
    "Staley High School",
    "Oak Park High School",
    "Winnetonka High School",
    "North Kansas City High School",
    "Antioch Middle School",
    "New Mark Middle School",
    "Maple Park Middle School",
    "Northgate Middle School",
    "Bell Prairie Elementary",
    "Briarcliff Elementary",
    "Chapel Hill Elementary",
    "Golden Oaks Education Center",
]


def _colliding_series():
    """12 schools x 3 periods with final rates clustered to force label
    collisions — the de-overlap pass must still separate every label."""
    periods = ["2026-09", "2026-10", "2026-11"]
    finals = [
        0.970, 0.969, 0.968, 0.930, 0.800, 0.910,
        0.905, 0.940, 0.972, 0.971, 0.900, 0.790,
    ]
    series = {
        s: {p: (0.95 if i < 2 else f) for i, p in enumerate(periods)}
        for s, f in zip(TWELVE_SCHOOLS, finals)
    }
    return series, {p: 0.915 for p in periods}, periods


_LABEL_RE = None


def _chart_labels(svg):
    import re

    return re.findall(
        r'<text x="([\d.]+)" y="([\d.]+)" class="([^"]+)" '
        r'data-school="([^"]+)">([^<]+)</text>',
        svg,
    )


class ChartLabelTests(unittest.TestCase):
    def test_all_twelve_schools_labeled(self):
        series, district, periods = _colliding_series()
        svg = _trend_svg(series, district, periods, w=900, h=380)
        labels = _chart_labels(svg)
        schools_labeled = {ds for _, _, _, ds, _ in labels} - {"__district__"}
        self.assertEqual(schools_labeled, set(TWELVE_SCHOOLS))

    def test_labels_are_bold_and_dark(self):
        # Justynn: school names must read as highlighted, not gray whispers.
        series, district, periods = _colliding_series()
        svg = _trend_svg(series, district, periods, w=900, h=380)
        labels = _chart_labels(svg)
        self.assertTrue(labels)
        for _, _, cls, _, _ in labels:
            self.assertIn("chart-label", cls)
        import dashboard

        css = dashboard.PAGE_CSS + dashboard.PAGE_CSS_EXTRA
        self.assertIn("font-weight:700", css.split(".chart-label{")[1].split("}")[0])

    def test_no_label_collisions(self):
        # the v7 bug: two labels 1px apart. Minimum 17px enforced now.
        series, district, periods = _colliding_series()
        svg = _trend_svg(series, district, periods, w=900, h=380)
        ys = sorted(float(y) for _, y, _, _, _ in _chart_labels(svg))
        gaps = [b - a for a, b in zip(ys, ys[1:])]
        self.assertTrue(gaps)
        self.assertGreaterEqual(min(gaps), 16.9)

    def test_district_label_present(self):
        series, district, periods = _colliding_series()
        svg = _trend_svg(series, district, periods, w=900, h=380)
        labels = _chart_labels(svg)
        dist = [t for _, _, _, ds, t in labels if ds == "__district__"]
        self.assertEqual(dist, ["District avg"])

    def test_paths_carry_data_school(self):
        series, district, periods = _colliding_series()
        svg = _trend_svg(series, district, periods, w=900, h=380)
        for s in TWELVE_SCHOOLS:
            self.assertIn(f'data-school="{s}"', svg)
        self.assertIn('data-school="__district__"', svg)

    def test_place_labels_unit(self):
        placed = _place_labels(
            [("a", 100.0), ("b", 101.0), ("c", 102.0)],
            min_gap=17,
            top=0,
            bottom=500,
        )
        ys = [y for _, y in placed]
        self.assertEqual([k for k, _ in placed], ["a", "b", "c"])
        self.assertGreaterEqual(ys[1] - ys[0], 17)
        self.assertGreaterEqual(ys[2] - ys[1], 17)

    def test_displaced_labels_get_leader_lines(self):
        series, district, periods = _colliding_series()
        svg = _trend_svg(series, district, periods, w=900, h=380)
        # clustered finals force displacement -> leader lines appear
        self.assertIn('stroke="#c9c4b6"', svg)


class DrillDownTests(unittest.TestCase):
    def test_cards_have_drill_buttons(self):
        page = _kpi_cards_html(METRICS_DATA["blocks"], [])
        for i in range(len(METRICS_DATA["blocks"])):
            self.assertIn(f'data-card="{i}"', page)
        self.assertIn('aria-controls="drill-panel"', page)
        self.assertIn("See the schools behind this", page)
        self.assertIn('id="drill-panel"', page)

    def test_drill_blob_has_five_entries(self):
        import json
        import re

        blocks = list(METRICS_DATA["blocks"]) * 5
        page = _kpi_cards_html(blocks, [])
        m = re.search(r"window\.KPI_DRILL=(\[.*?\]);</script>", page)
        self.assertIsNotNone(m)
        blob = json.loads(m.group(1))
        self.assertEqual(len(blob), 5)
        for entry in blob:
            self.assertIn("name", entry)
            self.assertIn("headers", entry)
            self.assertIn("rows", entry)
            self.assertIn("schools", entry)
            self.assertTrue(entry["schools"])

    def test_drill_blob_schools_match_table_rows(self):
        # the blob's school keys must equal the table's data-school values
        import json
        import re

        dashboard.summarize = _summarize
        try:
            page = render_full(
                _rows(),
                district="NKC-DEMO",
                allowed_schools=frozenset(
                    {"Antioch Middle School", "Staley High School"}
                ),
                callouts=CALLOUTS,
                metrics_data=METRICS_DATA,
                logistic_data=LOGISTIC,
                title="Full demo",
            )
        finally:
            dashboard.summarize = _REAL_SUMMARIZE
        m = re.search(r"window\.KPI_DRILL=(\[.*?\]);</script>", page)
        blob = json.loads(m.group(1))
        blob_schools = {s for e in blob for s in e["schools"]}
        for s in blob_schools:
            self.assertIn(f'data-school="{s}"', page)

    def test_hero_chart_and_table_are_drill_targets(self):
        dashboard.summarize = _summarize
        try:
            page = render_full(
                _rows(),
                district="NKC-DEMO",
                allowed_schools=frozenset(
                    {"Antioch Middle School", "Staley High School"}
                ),
                callouts=CALLOUTS,
                metrics_data=METRICS_DATA,
                logistic_data=LOGISTIC,
                title="Full demo",
            )
        finally:
            dashboard.summarize = _REAL_SUMMARIZE
        self.assertIn('id="hero-chart"', page)
        self.assertIn('id="schools-section"', page)
        self.assertIn("function showcase(school)", page)
        self.assertIn("scrollIntoView", page)


class HeaderTests(unittest.TestCase):
    def _page(self):
        dashboard.summarize = _summarize
        try:
            return render_full(
                _rows(),
                district="NKC-DEMO",
                allowed_schools=frozenset(
                    {"Antioch Middle School", "Staley High School"}
                ),
                callouts=CALLOUTS,
                metrics_data=METRICS_DATA,
                logistic_data=LOGISTIC,
                title="Full demo",
            )
        finally:
            dashboard.summarize = _REAL_SUMMARIZE

    def test_hero_has_real_h2(self):
        self.assertIn('<h2 class="hero-h">', self._page())

    def test_trend_strip_heading_is_h3(self):
        mv = {
            "template_id": "movement",
            "kicker": "Antioch &mdash; slipping",
            "big_html": "-7.0 pts",
            "line_html": "slipped.",
            "sev": "sev-high",
        }
        page = _trend_strip_html([mv])
        self.assertIn('<h3 class="strip-h">What changed</h3>', page)

    def test_heading_outline_has_no_skips(self):
        import re

        page = self._page()
        levels = [int(m.group(1)) for m in re.finditer(r"<h([123])[\s>]", page)]
        self.assertTrue(levels)
        self.assertEqual(levels[0], 1)
        for a, b in zip(levels, levels[1:]):
            self.assertLessEqual(b - a, 1, f"heading skip: h{a} -> h{b}")

    def test_h2_sized_like_a_header(self):
        import dashboard
        import re

        css = dashboard.PAGE_CSS + dashboard.PAGE_CSS_EXTRA
        # the EXTRA sheet overrides the old 19px section h2 with 24px/750
        m = re.findall(r"section\.block h2\{([^}]*)\}", css)
        self.assertTrue(m)
        last = m[-1]
        self.assertIn("font-size:24px", last)
        self.assertIn("font-weight:750", last)


class ExportTests(unittest.TestCase):
    """TW-530: every data section offers a raw-data CSV download
    (district Q&A: each data section must export to Excel/CSV)."""

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
        m = re.search(r"window\.EXPORT_DATA=(\{.*?\});</script>", self.page, re.S)
        self.assertIsNotNone(m, "EXPORT_DATA blob missing from page")
        self.data = json.loads(m.group(1))

    def test_one_export_button_per_data_section(self):
        btns = re.findall(r'data-export="(\w+)"', self.page)
        self.assertEqual(btns, ["trend", "kpi", "table"])

    def test_export_blob_has_all_datasets(self):
        self.assertEqual(sorted(self.data.keys()), ["kpi", "table", "trend"])

    def test_table_export_matches_rendered_rows(self):
        n_tr = len(re.findall(r"<tr data-school=", self.page))
        self.assertEqual(len(self.data["table"]["rows"]), n_tr)
        self.assertEqual(
            self.data["table"]["headers"],
            [
                "school", "period", "attendance_rate", "vs_district_pp",
                "enrolled_days", "present_days", "student_period_records", "note",
            ],
        )

    def test_trend_export_covers_schools_and_district(self):
        n_tr = len(re.findall(r"<tr data-school=", self.page))
        periods = {r[1] for r in self.data["table"]["rows"]}
        self.assertEqual(
            len(self.data["trend"]["rows"]), n_tr + 1 + len(periods)
        )

    def test_kpi_export_matches_metric_blocks(self):
        self.assertEqual(
            len(self.data["kpi"]["cards"]), len(METRICS_DATA["blocks"])
        )
        for card in self.data["kpi"]["cards"]:
            self.assertTrue(card["headers"])
            self.assertTrue(card["rows"])

    def test_no_student_identifiers_in_export(self):
        blob = json.dumps(self.data)
        self.assertNotIn("synth-", blob)
        self.assertNotIn("student_id", blob.lower())

    def test_buttons_label_csv_honestly(self):
        labels = re.findall(r'data-export="\w+">([^<]+)</button>', self.page)
        self.assertEqual(len(labels), 3)
        for label in labels:
            self.assertIn("CSV", label)


if __name__ == "__main__":
    unittest.main()
