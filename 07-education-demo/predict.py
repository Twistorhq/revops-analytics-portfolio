# Prepared by Twistor Holdings LLC
# TW-494: chronic-absenteeism prediction overlay — logistic regression.
#
# Predicts P(student is chronically absent in the forecast period) from
# early-window behavior. Methodology demonstrator: trains on SYNTHETIC data.
# The bid must state plainly that a production deployment retrains on the
# district's real historical data — synthetic-trained coefficients do not
# transfer.
#
# Math: P(y=1|x) = 1 / (1 + exp(-(b0 + b1*x1 + ... + bk*xk))).
# Log-odds are linear in the features, so each coefficient is interpretable:
# exp(bi) is the multiplicative change in the odds of chronic absenteeism
# per one-unit change in feature i, holding the rest fixed. That is what
# makes the flag actionable for a counselor instead of a black-box score.

import csv
import datetime as dt
import io
import random

CHRONIC_THRESHOLD = 0.10  # absent 10%+ of enrolled days = chronically absent
BASELINE_RATE_CUTOFF = 0.90  # naive rule: flag if first-30-day rate < 90%

# Instructional calendar: weekdays of Sep-Nov 2026, split into 3 periods.
PERIODS = (("2026-09", 9), ("2026-10", 10), ("2026-11", 11))
OBSERVE_PERIODS = ("2026-09", "2026-10")  # features come from here
FORECAST_PERIOD = "2026-11"  # target comes from here


def instructional_days(year=2026):
    """Weekday dates for Sep-Nov, tagged with period. Deterministic."""
    days = []
    d = dt.date(year, 9, 1)
    while d <= dt.date(year, 11, 30):
        if d.weekday() < 5:
            period = f"{d.year}-{d.month:02d}"
            days.append((d, period))
        d += dt.timedelta(days=1)
    return days


def _seeded(seed, *parts):
    return random.Random(f"{seed}|{'|'.join(map(str, parts))}")


def generate_day_level(schools, seed=20261013):
    """Deterministic student x day attendance records.

    schools: iterable of (name, n_students, base_absence_rate, opts).
    opts: chronic_share/chronic_rate (a share of students with high
    propensity), monfri_lift (extra absence probability on Mon/Fri),
    gap_period (no records — the data gap), november_dip.
    Yields dicts: school, student, date, period, present (0/1), enrolled (0/1).
    Student IDs are synthetic (synth-*) and must never reach output pages.
    """
    days = instructional_days()
    for name, n, base, opts in schools:
        slug = "".join(name.lower().split())
        for i in range(n):
            student = f"synth-{slug}-{i:04d}"
            chronic = (i % 100) < int(opts.get("chronic_share", 0.0) * 100)
            churner = (i % 37) == 0  # enrollment churn: partial enrollment
            extender = (i % 13) == 0  # weekend extender: Mon/Fri absence pattern
            decliner = (i % 11) == 0  # declining trajectory: gets worse over time
            p_base = opts["chronic_rate"] if chronic else base
            if churner:
                p_base += 0.03  # churn correlates weakly with absence
            p_student = _seeded(seed, "propensity", name, student).betavariate(
                max(p_base * 30, 0.5), 30 - max(p_base * 30, 0.5) + 0.5
            )
            for d, period in days:
                if opts.get("gap_period") == period:
                    continue
                rng = _seeded(seed, "day", name, student, d.isoformat())
                enrolled = 0 if (churner and rng.random() < 0.15) else 1
                p = p_student
                if d.weekday() in (0, 4):  # Monday / Friday
                    p += opts.get("monfri_lift", 0.0)
                    if extender:
                        p += 0.18  # weekend extenders skip the bookend days
                if period == "2026-11":
                    p += opts.get("november_dip", 0.0)
                if decliner:
                    # declining trajectory: absence propensity ramps up
                    p += {"2026-09": 0.0, "2026-10": 0.08, "2026-11": 0.18}[period]
                p = min(max(p, 0.0), 0.95)
                present = (
                    0 if (enrolled and rng.random() < p) else (1 if enrolled else 0)
                )
                yield {
                    "school": name,
                    "student": student,
                    "date": d.isoformat(),
                    "period": period,
                    "enrolled": enrolled,
                    "present": present,
                }


def _absence_streak_max(records):
    best = run = 0
    for r in records:
        if r["enrolled"] and not r["present"]:
            run += 1
            best = max(best, run)
        elif r["enrolled"]:
            run = 0
    return best


def build_features(records):
    """Aggregate day-level records to one row per student.

    Features (observation window only):
      first30_rate  present/enrolled over first 30 enrolled days
      monfri_lift   (Mon+Fri absence rate) - (Tue-Thu absence rate), in points
      max_streak    longest consecutive-absence run in the window
      school_base   school mean absence rate over the window
      churn_flag    1 if the student missed any enrolled day entirely
    Target:
      chronic_next  1 if absent 10%+ of enrolled days in the forecast period
    Returns (rows, feature_names). Rows are dicts with 'school','student'.
    """
    by_student = {}
    for r in records:
        by_student.setdefault(r["student"], []).append(r)
    for recs in by_student.values():
        recs.sort(key=lambda r: r["date"])

    school_absent = {}
    school_enrolled = {}
    for student, recs in by_student.items():
        obs = [r for r in recs if r["period"] in OBSERVE_PERIODS and r["enrolled"]]
        a = sum(1 for r in obs if not r["present"])
        school_absent[recs[0]["school"]] = school_absent.get(recs[0]["school"], 0) + a
        school_enrolled[recs[0]["school"]] = school_enrolled.get(
            recs[0]["school"], 0
        ) + len(obs)

    rows = []
    for student, recs in sorted(by_student.items()):
        school = recs[0]["school"]
        obs = [r for r in recs if r["period"] in OBSERVE_PERIODS and r["enrolled"]]
        fc = [r for r in recs if r["period"] == FORECAST_PERIOD and r["enrolled"]]
        if len(obs) < 20 or not fc:
            continue  # insufficient history or no forecast window: skip
        first30 = obs[:30]
        first30_rate = sum(r["present"] for r in first30) / len(first30)
        mf = [r for r in obs if dt.date.fromisoformat(r["date"]).weekday() in (0, 4)]
        mid = [
            r for r in obs if dt.date.fromisoformat(r["date"]).weekday() in (1, 2, 3)
        ]
        mf_rate = (sum(1 for r in mf if not r["present"]) / len(mf)) if mf else 0.0
        mid_rate = (sum(1 for r in mid if not r["present"]) / len(mid)) if mid else 0.0
        sep = [r for r in obs if r["period"] == "2026-09"]
        oct_ = [r for r in obs if r["period"] == "2026-10"]
        sep_rate = sum(r["present"] for r in sep) / len(sep) if sep else first30_rate
        oct_rate = sum(r["present"] for r in oct_) / len(oct_) if oct_ else first30_rate
        trend = oct_rate - sep_rate  # negative = declining attendance
        school_base = school_absent[school] / school_enrolled[school]
        churn_flag = 1 if any(r["enrolled"] == 0 for r in recs) else 0
        fc_absent_rate = sum(1 for r in fc if not r["present"]) / len(fc)
        rows.append(
            {
                "school": school,
                "student": student,
                "first30_rate": first30_rate,
                "monfri_lift": mf_rate - mid_rate,
                "max_streak": _absence_streak_max(obs),
                "trend": trend,
                "school_base": school_base,
                "churn_flag": churn_flag,
                "chronic_next": 1 if fc_absent_rate >= CHRONIC_THRESHOLD else 0,
            }
        )
    features = [
        "first30_rate",
        "monfri_lift",
        "max_streak",
        "trend",
        "school_base",
        "churn_flag",
    ]
    return rows, features


def to_csv(records):
    """Serialize day-level records (debug/inspection aid)."""
    out = io.StringIO()
    w = csv.DictWriter(
        out, fieldnames=["school", "student", "date", "period", "enrolled", "present"]
    )
    w.writeheader()
    w.writerows(records)
    return out.getvalue()
