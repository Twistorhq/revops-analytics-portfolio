# Prepared by Twistor Holdings LLC
# TW-494: tests for the chronic-absenteeism prediction overlay.


from importer import DISTRICT_SCHOOLS
from model import (
    baseline_predict,
    predict_fallback,
    run_backtest,
)
from predict import (
    BASELINE_RATE_CUTOFF,
    build_features,
    generate_day_level,
    instructional_days,
)

SCHOOLS = [(n, s, b, dict(o, monfri_lift=0.03)) for n, s, b, o in DISTRICT_SCHOOLS]


def _rows(seed=20261013):
    recs = list(generate_day_level(SCHOOLS, seed=seed))
    return build_features(recs)


def test_instructional_days_are_weekdays():
    days = instructional_days()
    assert len(days) > 50
    for d, period in days:
        assert d.weekday() < 5, f"{d} is not a weekday"
        assert period in ("2026-09", "2026-10", "2026-11")


def test_generation_is_deterministic():
    r1 = list(generate_day_level(SCHOOLS, seed=7))
    r2 = list(generate_day_level(SCHOOLS, seed=7))
    assert r1 == r2
    r3 = list(generate_day_level(SCHOOLS, seed=8))
    assert r1 != r3


def test_features_have_expected_shape():
    rows, features = _rows()
    assert features == [
        "first30_rate",
        "monfri_lift",
        "max_streak",
        "trend",
        "school_base",
        "churn_flag",
    ]
    assert len(rows) > 1000
    for r in rows:
        assert 0.0 <= r["first30_rate"] <= 1.0
        assert r["max_streak"] >= 0
        assert r["chronic_next"] in (0, 1)
        assert set(r) == set(features) | {
            "school",
            "student",
            "chronic_next",
        }  # no stray fields


def test_first30_rate_computed_correctly():
    # hand-built mini history: 30 enrolled days, 27 present -> 0.90
    recs = []
    import datetime as dt

    d = dt.date(2026, 9, 1)
    made = 0
    while made < 30:
        if d.weekday() < 5:
            recs.append(
                {
                    "school": "S",
                    "student": "synth-s-0001",
                    "date": d.isoformat(),
                    "period": "2026-09",
                    "enrolled": 1,
                    "present": 1 if made < 27 else 0,
                }
            )
            made += 1
        d += dt.timedelta(days=1)
    # forecast period: all present -> not chronic
    d = dt.date(2026, 11, 2)
    made = 0
    while made < 15:
        if d.weekday() < 5:
            recs.append(
                {
                    "school": "S",
                    "student": "synth-s-0001",
                    "date": d.isoformat(),
                    "period": "2026-11",
                    "enrolled": 1,
                    "present": 1,
                }
            )
            made += 1
        d += dt.timedelta(days=1)
    rows, _ = build_features(recs)
    assert len(rows) == 1
    assert abs(rows[0]["first30_rate"] - 0.90) < 1e-9
    assert rows[0]["max_streak"] == 3
    assert rows[0]["chronic_next"] == 0


def test_streak_counts_consecutive_absences():
    import datetime as dt

    recs = []
    d = dt.date(2026, 9, 1)
    made = 0
    # pattern: P P A A A A P ... -> max streak 4
    presents = [1, 1, 0, 0, 0, 0, 1] + [1] * 23
    while made < 30:
        if d.weekday() < 5:
            recs.append(
                {
                    "school": "S",
                    "student": "synth-s-0002",
                    "date": d.isoformat(),
                    "period": "2026-09",
                    "enrolled": 1,
                    "present": presents[made],
                }
            )
            made += 1
        d += dt.timedelta(days=1)
    d = dt.date(2026, 11, 2)
    made = 0
    while made < 15:
        if d.weekday() < 5:
            recs.append(
                {
                    "school": "S",
                    "student": "synth-s-0002",
                    "date": d.isoformat(),
                    "period": "2026-11",
                    "enrolled": 1,
                    "present": 1,
                }
            )
            made += 1
        d += dt.timedelta(days=1)
    rows, _ = build_features(recs)
    assert rows[0]["max_streak"] == 4


def test_model_beats_baseline_at_matched_recall():
    rows, features = _rows()
    model_eval, base_eval, _, _, _ = run_backtest(rows, features)
    matched = model_eval["at_baseline_recall"]
    assert matched is not None
    # at the same recall, the model must be at least as precise as the rule
    assert matched["precision"] >= base_eval["precision"] - 0.01, (
        f"model {matched['precision']} vs baseline {base_eval['precision']}"
    )
    assert model_eval["auc"] > 0.70


def test_odds_ratios_point_the_right_way():
    rows, features = _rows()
    _, _, _, odds, _ = run_backtest(rows, features)
    # higher early attendance -> lower odds; longer streaks -> higher odds
    assert odds["first30_rate"] < 1.0
    assert odds["max_streak"] > 1.0
    assert odds["school_base"] > 1.0


def test_reliability_curve_is_roughly_diagonal():
    rows, features = _rows()
    _, _, rel, _, _ = run_backtest(rows, features)
    assert len(rel) >= 6
    # mean absolute gap between predicted and observed across bins
    gap = sum(abs(b["mean_predicted"] - b["observed_rate"]) for b in rel) / len(rel)
    assert gap < 0.10, f"calibration gap {gap:.3f} too large"


def test_fallback_matches_naive_rule():
    rows, _ = _rows()
    for r in rows[:50]:
        expected = 1 if r["first30_rate"] < BASELINE_RATE_CUTOFF else 0
        assert predict_fallback(r) == expected
    assert baseline_predict(rows[:50]).tolist() == [
        predict_fallback(r) for r in rows[:50]
    ]


def test_no_student_ids_in_model_artifacts():
    rows, features = _rows()
    _, _, rel, odds, _ = run_backtest(rows, features)
    blob = str(rel) + str(odds)
    assert "synth-" not in blob


def _mini_history_with_gap(unenrolled_period):
    """Hand-built history: 30 enrolled Sep days + one unenrolled day in the
    requested period + a 15-day November forecast window."""
    import datetime as dt

    recs = []
    d = dt.date(2026, 9, 1)
    made = 0
    while made < 30:
        if d.weekday() < 5:
            recs.append(
                {
                    "school": "S",
                    "student": "synth-s-0001",
                    "date": d.isoformat(),
                    "period": "2026-09",
                    "enrolled": 1,
                    "present": 1,
                }
            )
            made += 1
        d += dt.timedelta(days=1)
    ud = (
        dt.date(2026, 10, 5) if unenrolled_period == "2026-10" else dt.date(2026, 11, 9)
    )
    recs.append(
        {
            "school": "S",
            "student": "synth-s-0001",
            "date": ud.isoformat(),
            "period": unenrolled_period,
            "enrolled": 0,
            "present": 0,
        }
    )
    d = dt.date(2026, 11, 2)
    made = 0
    while made < 15:
        if d.weekday() < 5:
            recs.append(
                {
                    "school": "S",
                    "student": "synth-s-0001",
                    "date": d.isoformat(),
                    "period": "2026-11",
                    "enrolled": 1,
                    "present": 1,
                }
            )
            made += 1
        d += dt.timedelta(days=1)
    return recs


def test_churn_flag_uses_observation_window_only():
    # Unenrolled day in October (observation window) -> flag set.
    rows, _ = build_features(_mini_history_with_gap("2026-10"))
    assert len(rows) == 1
    assert rows[0]["churn_flag"] == 1
    # Unenrolled day in November (forecast window) -> flag NOT set.
    # At prediction time (end of October) November enrollment is unknowable;
    # a feature reading it would be label leakage.
    rows, _ = build_features(_mini_history_with_gap("2026-11"))
    assert len(rows) == 1
    assert rows[0]["churn_flag"] == 0
