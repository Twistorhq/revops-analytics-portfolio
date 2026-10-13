# Prepared by Twistor Holdings LLC
# Tests for the dynamic callout insight engine. Each trigger rule is
# exercised on crafted data: fires up, fires down, fires flat, fires on
# threshold cross, and stays silent when nothing is notable.

import unittest

from callouts import (
    Callout,
    Thresholds,
    detect_callouts,
    detect_days_lost_concentration,
    detect_early_warnings,
    detect_flatlines,
    detect_mf_ratios,
    detect_movements,
    detect_recoveries,
    detect_threshold_crosses,
)

T = Thresholds()
PERIODS = ["2026-09", "2026-10", "2026-11"]


def series(school_rates):
    """{school: {period: rate}} from {school: [r_sep, r_oct, r_nov]}."""
    return {
        s: {p: r for p, r in zip(PERIODS, rates)} for s, rates in school_rates.items()
    }


class MovementTests(unittest.TestCase):
    def test_fires_on_big_drop(self):
        s = series({"A": [0.93, 0.93, 0.88]})  # -5.0 pts Oct->Nov
        out = detect_movements(s, PERIODS, T)
        self.assertEqual(len(out), 1)
        c = out[0]
        self.assertEqual(c.direction, "down")
        self.assertEqual(c.severity, "high")
        self.assertAlmostEqual(c.delta_pts, -5.0)
        self.assertIn("slipped", c.line)

    def test_fires_on_rise(self):
        s = series({"A": [0.90, 0.90, 0.925]})  # +2.5 pts
        out = detect_movements(s, PERIODS, T)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].direction, "up")
        self.assertIn("climbed", out[0].line)

    def test_silent_below_threshold(self):
        s = series({"A": [0.93, 0.925, 0.915]})  # -1.0 pt
        self.assertEqual(detect_movements(s, PERIODS, T), [])

    def test_fires_across_data_gaps(self):
        # Sep->Nov are not adjacent in the series order with a gap between;
        # _pop takes the last two non-null which are non-adjacent. -5.0 pts
        # still fires — gaps never silently suppress a real move.
        out = detect_movements({"A": {"2026-09": 0.93, "2026-11": 0.88}}, PERIODS, T)
        self.assertEqual(len(out), 1)


class ThresholdCrossTests(unittest.TestCase):
    def test_fires_falling_into_warning(self):
        s = series({"A": [0.93, 0.905, 0.895]})
        out = detect_threshold_crosses(s, PERIODS, T)
        self.assertEqual(len(out), 1)
        c = out[0]
        self.assertEqual(c.severity, "high")
        self.assertEqual(c.direction, "down")
        self.assertIn("warning territory", c.line)

    def test_fires_climbing_out(self):
        s = series({"A": [0.93, 0.895, 0.905]})
        out = detect_threshold_crosses(s, PERIODS, T)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].direction, "up")
        self.assertEqual(out[0].severity, "info")

    def test_silent_when_always_below(self):
        s = series({"A": [0.88, 0.87, 0.86]})
        self.assertEqual(detect_threshold_crosses(s, PERIODS, T), [])

    def test_silent_when_always_above(self):
        s = series({"A": [0.95, 0.94, 0.93]})
        self.assertEqual(detect_threshold_crosses(s, PERIODS, T), [])


class FlatlineTests(unittest.TestCase):
    def test_fires_on_three_flat_periods(self):
        s = series({"A": [0.921, 0.922, 0.920]})
        out = detect_flatlines(s, PERIODS, T)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].direction, "flat")
        self.assertEqual(out[0].template_id, "flat")

    def test_silent_when_moving(self):
        s = series({"A": [0.92, 0.93, 0.92]})
        self.assertEqual(detect_flatlines(s, PERIODS, T), [])

    def test_silent_with_too_few_periods(self):
        s = series({"A": [0.92, 0.921]})
        self.assertEqual(detect_flatlines(s, ["2026-09", "2026-10"], T), [])


class MetricRuleTests(unittest.TestCase):
    def test_early_warning_fires(self):
        rows = [
            {
                "school": "Antioch",
                "pct": 0.743,
                "on_pace_chronic": 508,
                "students": 684,
            },
            {"school": "Calm", "pct": 0.10, "on_pace_chronic": 5, "students": 50},
        ]
        out = detect_early_warnings(rows, T)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].school, "Antioch")
        self.assertEqual(out[0].severity, "high")
        self.assertIn("7 in 10", out[0].line)

    def test_mf_ratio_fires(self):
        rows = [
            {
                "school": "NKCHS",
                "mf_ratio": 1.34,
                "mf_absence_rate": 0.101,
                "midweek_absence_rate": 0.076,
            },
            {
                "school": "Calm",
                "mf_ratio": 1.05,
                "mf_absence_rate": 0.05,
                "midweek_absence_rate": 0.048,
            },
        ]
        out = detect_mf_ratios(rows, T)
        self.assertEqual(len(out), 1)
        self.assertIn("34%", out[0].line)

    def test_recovery_fires_good_news(self):
        rows = [
            {"school": "Staley", "pct": 0.989, "chronic_p1": 87, "recovered_p2": 86},
            {"school": "Meh", "pct": 0.5, "chronic_p1": 10, "recovered_p2": 5},
        ]
        out = detect_recoveries(rows, T)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].severity, "info")
        self.assertEqual(out[0].direction, "up")

    def test_concentration_fires(self):
        idl = {
            "district_days_lost": 10000,
            "schools": [
                {"school": "Big", "days_lost": 2500},
                {"school": "Small", "days_lost": 500},
            ],
        }
        out = detect_days_lost_concentration(idl, T)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].school, "Big")

    def test_nulls_never_fire(self):
        rows = [{"school": "X", "pct": None, "on_pace_chronic": 0, "students": 0}]
        self.assertEqual(detect_early_warnings(rows, T), [])
        rows = [{"school": "X", "mf_ratio": None}]
        self.assertEqual(detect_mf_ratios(rows, T), [])


class OrchestrationTests(unittest.TestCase):
    def test_ranks_high_before_info_and_caps(self):
        s = series(
            {
                "Drop": [0.93, 0.93, 0.85],  # -8 high
                "Warn": [0.93, 0.905, 0.895],  # cross high
                "Flat": [0.921, 0.922, 0.920],  # flat info
                "Rise": [0.90, 0.90, 0.93],  # +3 medium
            }
        )
        out = detect_callouts(s, PERIODS, thresholds=Thresholds(max_callouts=3))
        self.assertEqual(len(out), 3)
        sevs = [c.severity for c in out]
        self.assertEqual(
            sevs, sorted(sevs, key={"high": 0, "medium": 1, "info": 2}.get)
        )

    def test_caps_per_template_for_diversity(self):
        # Four threshold crosses fire, but only two survive the per-template
        # cap — the band surfaces distinct insight types.
        s = series(
            {
                "A": [0.95, 0.93, 0.89],
                "B": [0.95, 0.93, 0.88],
                "C": [0.95, 0.93, 0.87],
                "D": [0.95, 0.93, 0.86],
            }
        )
        out = detect_callouts(s, PERIODS)
        crosses = [c for c in out if c.template_id == "threshold_cross"]
        self.assertEqual(len(crosses), 2)

    def test_deterministic_tiebreak(self):
        s = series({"B": [0.93, 0.93, 0.90], "A": [0.93, 0.93, 0.90]})
        out1 = detect_callouts(s, PERIODS)
        out2 = detect_callouts(s, PERIODS)
        self.assertEqual(out1, out2)
        self.assertEqual(out1[0].school, "A")

    def test_dedupes_same_school_metric(self):
        # Drop (-8) and threshold cross on the same school+metric tell one
        # story — only the stronger survives.
        s = series({"A": [0.93, 0.93, 0.85]})
        out = detect_callouts(s, PERIODS)
        a_callouts = [c for c in out if c.school == "A"]
        self.assertEqual(len(a_callouts), 1)

    def test_empty_when_nothing_notable(self):
        s = series({"A": [0.93, 0.931, 0.929], "B": [0.94, 0.941, 0.939]})
        # flat needs 3 periods within eps — these ARE flat, so expect flat
        # callouts; use 2 periods to get true silence
        out = detect_callouts(s, ["2026-09", "2026-10"])
        self.assertEqual(out, [])

    def test_callout_objects_carry_plain_text(self):
        s = series({"A": [0.93, 0.93, 0.88]})
        out = detect_callouts(s, PERIODS)
        c = out[0]
        self.assertIsInstance(c, Callout)
        # no pre-escaped entities — dashboard escapes on render
        self.assertNotIn("&amp;", c.kicker + c.big + c.line)
        self.assertNotIn("&mdash;", c.kicker + c.big + c.line)


if __name__ == "__main__":
    unittest.main()
