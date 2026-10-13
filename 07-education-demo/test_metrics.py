# Prepared by Twistor Holdings LLC
"""Tests for TW-493 custom metrics + daily generator."""

import json
import unittest

from importer import (
    DISTRICT_SCHOOL_NAMES,
    demo_district_csv,
    demo_district_daily_csv,
    demo_mapping,
    import_csv,
)
from metrics import (
    DailyRecord,
    chronic_early_warning,
    instructional_days_lost,
    monday_friday_ratio,
    parse_daily_csv,
    recovery_rate,
    streak3_students,
)

SCHOOLS = frozenset({"Test Elementary"})


def _rec(school, student, date, present, dow=1, period="2026-09"):
    return DailyRecord("NKC-DEMO", school, student, date, period, present, dow)


class ChronicEarlyWarningTests(unittest.TestCase):
    def test_flags_students_on_pace(self):
        # 30-day window; s2 is exactly at the 10% line -> on pace
        recs = []
        dates = [f"2026-09-{d:02d}" for d in range(1, 31)]
        for i, d in enumerate(dates):
            recs.append(_rec("Test Elementary", "s1", d, True, 1))  # 0 absent
            recs.append(_rec("Test Elementary", "s2", d, i >= 3, 1))  # 3 absent
            recs.append(_rec("Test Elementary", "s3", d, i < 28, 1))  # 2 absent
        # s4: only 10 days enrolled -> does not qualify
        for i, d in enumerate(dates[:10]):
            recs.append(_rec("Test Elementary", "s4", d, i >= 5, 1))  # 5 absent
        out = chronic_early_warning(recs, district="NKC-DEMO", allowed_schools=SCHOOLS)
        row = out["schools"][0]
        self.assertEqual(row["students"], 3)
        self.assertEqual(row["on_pace_chronic"], 1)
        self.assertAlmostEqual(row["pct"], 1 / 3)

    def test_empty_scope_raises(self):
        with self.assertRaises(ValueError):
            chronic_early_warning([], district="", allowed_schools=SCHOOLS)


class MondayFridayRatioTests(unittest.TestCase):
    def test_ratio_above_one(self):
        recs = []
        # 10 MF days (dow 0/4), 3 absent -> 0.30; 15 mid days, 3 absent -> 0.20
        for i in range(10):
            recs.append(
                _rec("Test Elementary", "s1", f"d{i}", i < 7, 0 if i % 2 == 0 else 4)
            )
        for i in range(15):
            recs.append(_rec("Test Elementary", "s1", f"e{i}", i < 12, 2))
        out = monday_friday_ratio(recs, district="NKC-DEMO", allowed_schools=SCHOOLS)
        row = out["schools"][0]
        self.assertAlmostEqual(row["mf_absence_rate"], 0.30)
        self.assertAlmostEqual(row["midweek_absence_rate"], 0.20)
        self.assertAlmostEqual(row["mf_ratio"], 1.5)

    def test_null_when_no_midweek(self):
        recs = [_rec("Test Elementary", "s1", "d1", False, 0)]
        out = monday_friday_ratio(recs, district="NKC-DEMO", allowed_schools=SCHOOLS)
        self.assertIsNone(out["schools"][0]["mf_ratio"])


class Streak3Tests(unittest.TestCase):
    def test_streaks_detected(self):
        recs = []
        days = [f"2026-09-{d:02d}" for d in range(1, 11)]
        dows = [1, 2, 3, 4, 0, 1, 2, 3, 4, 0]  # d4=Thu d5=Fri d6=Mon
        # s1: 3 consecutive -> flagged
        for i, d in enumerate(days):
            recs.append(_rec("Test Elementary", "s1", d, i not in (0, 1, 2), dows[i]))
        # s2: spread out -> not flagged
        for i, d in enumerate(days):
            recs.append(_rec("Test Elementary", "s2", d, i not in (0, 2, 4), dows[i]))
        # s3: Thu+Fri+Mon = 3 consecutive instructional days -> flagged
        for i, d in enumerate(days):
            recs.append(_rec("Test Elementary", "s3", d, i not in (3, 4, 5), dows[i]))
        out = streak3_students(recs, district="NKC-DEMO", allowed_schools=SCHOOLS)
        row = out["schools"][0]
        self.assertEqual(row["students"], 3)
        self.assertEqual(row["students_with_streak3"], 2)
        self.assertAlmostEqual(row["pct"], 2 / 3)


class RecoveryRateTests(unittest.TestCase):
    def test_recovery_counted(self):
        recs = []
        for i in range(20):
            d = f"2026-09-{i + 1:02d}"
            recs.append(
                _rec("Test Elementary", "s1", d, i >= 4, 1, "2026-09")
            )  # 4/20 chronic
            recs.append(
                _rec("Test Elementary", "s2", d, i >= 4, 1, "2026-09")
            )  # 4/20 chronic
            recs.append(
                _rec("Test Elementary", "s3", d, i >= 1, 1, "2026-09")
            )  # 1/20 fine
        for i in range(20):
            d = f"2026-10-{i + 1:02d}"
            recs.append(
                _rec("Test Elementary", "s1", d, i >= 1, 1, "2026-10")
            )  # recovered
            recs.append(
                _rec("Test Elementary", "s2", d, i >= 5, 1, "2026-10")
            )  # still chronic
            recs.append(_rec("Test Elementary", "s3", d, True, 1, "2026-10"))
        # s4: too few days in p1 -> excluded
        for i in range(5):
            recs.append(
                _rec(
                    "Test Elementary", "s4", f"2026-09-{i + 1:02d}", False, 1, "2026-09"
                )
            )
        out = recovery_rate(recs, district="NKC-DEMO", allowed_schools=SCHOOLS)
        row = out["schools"][0]
        self.assertEqual(row["chronic_p1"], 2)
        self.assertEqual(row["recovered_p2"], 1)
        self.assertAlmostEqual(row["pct"], 0.5)

    def test_null_when_no_chronic(self):
        recs = [_rec("Test Elementary", "s1", "d1", True, 1, "2026-09")]
        out = recovery_rate(recs, district="NKC-DEMO", allowed_schools=SCHOOLS)
        self.assertIsNone(out["schools"][0]["pct"])


class DaysLostTests(unittest.TestCase):
    def test_sums_absences(self):
        recs = [
            _rec("A Elementary", "s1", "d1", False, 1),
            _rec("A Elementary", "s1", "d2", True, 2),
            _rec("B Elementary", "s2", "d1", False, 1),
            _rec("B Elementary", "s2", "d2", False, 2),
        ]
        out = instructional_days_lost(
            recs,
            district="NKC-DEMO",
            allowed_schools=frozenset({"A Elementary", "B Elementary"}),
        )
        by_school = {r["school"]: r["days_lost"] for r in out["schools"]}
        self.assertEqual(by_school["A Elementary"], 1)
        self.assertEqual(by_school["B Elementary"], 2)
        self.assertEqual(out["district_days_lost"], 3)


class DailyGeneratorTests(unittest.TestCase):
    SUBSET = ("Bell Prairie Elementary", "Briarcliff Elementary")

    def test_daily_csv_deterministic(self):
        a = demo_district_daily_csv(schools=self.SUBSET)
        b = demo_district_daily_csv(schools=self.SUBSET)
        self.assertEqual(a, b)

    def test_daily_sums_match_monthly(self):
        # Same RNG stream -> daily sums per (student, period) == monthly rows
        daily = parse_daily_csv(demo_district_daily_csv(schools=self.SUBSET))
        monthly = {
            (r.school, r.student, r.period): (r.enrolled_days, r.present_days)
            for r in import_csv(demo_district_csv(), demo_mapping()).accepted
            if r.school in self.SUBSET
        }
        agg: dict = {}
        for r in daily:
            key = (r.school, r.student, r.period)
            e, p = agg.get(key, (0, 0))
            agg[key] = (e + 1, p + (1 if r.present else 0))
        self.assertEqual(set(agg), set(monthly))
        for key, (me, mp) in monthly.items():
            self.assertEqual(agg[key], (me, mp), f"mismatch at {key}")

    def test_real_school_names(self):
        expected = {
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
        }
        self.assertEqual(DISTRICT_SCHOOL_NAMES, expected)

    def test_metric_outputs_have_no_student_ids(self):
        daily = parse_daily_csv(
            demo_district_daily_csv(schools=("Bell Prairie Elementary",))
        )
        outs = [
            chronic_early_warning(
                daily,
                district="NKC-DEMO",
                allowed_schools=frozenset({"Bell Prairie Elementary"}),
            ),
            monday_friday_ratio(
                daily,
                district="NKC-DEMO",
                allowed_schools=frozenset({"Bell Prairie Elementary"}),
            ),
            streak3_students(
                daily,
                district="NKC-DEMO",
                allowed_schools=frozenset({"Bell Prairie Elementary"}),
            ),
            recovery_rate(
                daily,
                district="NKC-DEMO",
                allowed_schools=frozenset({"Bell Prairie Elementary"}),
            ),
            instructional_days_lost(
                daily,
                district="NKC-DEMO",
                allowed_schools=frozenset({"Bell Prairie Elementary"}),
            ),
        ]
        blob = json.dumps(outs)
        self.assertNotIn("synth-", blob)


if __name__ == "__main__":
    unittest.main()
