# Prepared by Twistor Holdings LLC
# TW-495: tests for the Cox proportional-hazards survival overlay.


import numpy as np

from importer import DISTRICT_SCHOOLS
from predict import generate_day_level, instructional_days
from survival import (
    add_first30_strata,
    build_survival_data,
    calibration_at_horizons,
    concordance_index,
    event_probability,
    fit,
    median_days_to_event,
    ph_assumption_check,
    predict_fallback,
    risk_tiers,
)

SCHOOLS = [(n, s, b, dict(o, monfri_lift=0.03)) for n, s, b, o in DISTRICT_SCHOOLS]
STRATA = ["first30_stratum"]


def _district_df(seed=20261013):
    recs = list(generate_day_level(SCHOOLS, seed=seed))
    df, features = build_survival_data(recs)
    return add_first30_strata(df), features


def _nov_days():
    return [d for d, p in instructional_days() if p == "2026-11"]


def _manual_records(absent_nov_days, n_obs_enrolled=40, n_obs_absent=3):
    """Hand-built student: 7.5% absent through Oct, then a scripted November."""
    days = instructional_days()
    recs = []
    n = 0
    for d, period in days:
        if period in ("2026-09", "2026-10"):
            if n >= n_obs_enrolled:
                continue
            n += 1
            recs.append(
                {
                    "school": "Test High",
                    "student": "synth-test-0001",
                    "date": d.isoformat(),
                    "period": period,
                    "enrolled": 1,
                    "present": 0 if n <= n_obs_absent else 1,
                }
            )
        elif period == "2026-11":
            recs.append(
                {
                    "school": "Test High",
                    "student": "synth-test-0001",
                    "date": d.isoformat(),
                    "period": period,
                    "enrolled": 1,
                    "present": 0 if d.day in absent_nov_days else 1,
                }
            )
    return recs


def test_landmark_excludes_already_chronic():
    # 8/40 = 20% absent through Oct -> already chronic -> excluded
    recs = _manual_records(absent_nov_days=[], n_obs_absent=8)
    df, _ = build_survival_data(recs)
    assert len(df) == 0


def test_event_time_is_first_crossing_day():
    # Through Oct: 3/40 = 7.5%. Nov: absent on the 2nd and 3rd Nov weekdays.
    nov = _nov_days()
    absent_days = {nov[1].day, nov[2].day}
    recs = _manual_records(absent_nov_days=absent_days)
    df, _ = build_survival_data(recs)
    assert len(df) == 1
    # day1: 3/41=7.3%; day2: 4/42=9.5%; day3: 5/43=11.6% -> event at 3
    assert df.iloc[0]["event"] == 1
    assert df.iloc[0]["duration"] == 3


def test_censored_at_horizon_when_never_crosses():
    recs = _manual_records(absent_nov_days=[])
    df, _ = build_survival_data(recs)
    assert len(df) == 1
    assert df.iloc[0]["event"] == 0
    assert df.iloc[0]["duration"] == len(_nov_days())


def test_concordance_perfect_ordering():
    t = [1, 2, 3, 4]
    e = [1, 1, 1, 1]
    assert concordance_index(t, e, [4.0, 3.0, 2.0, 1.0]) == 1.0
    assert concordance_index(t, e, [1.0, 2.0, 3.0, 4.0]) == 0.0


def test_concordance_random_is_half():
    rng = np.random.RandomState(7)
    t = rng.randint(1, 22, size=500)
    e = rng.randint(0, 2, size=500)
    c = concordance_index(t, e, rng.rand(500))
    assert 0.4 < c < 0.6, f"random C should be ~0.5, got {c}"


def test_concordance_ignores_censored_early_member():
    # i censored at t=2 cannot serve as the earlier member of a pair
    t = [2, 5]
    e = [0, 1]
    assert concordance_index(t, e, [9.0, 1.0]) == 0.5  # no comparable pairs


def test_no_forecast_leakage_in_churn_flag():
    # Student unenrolled ONLY in November -> churn_flag must be 0
    # (TW-494 leak fix: the flag is measured on Sep-Oct only).
    days = instructional_days()
    recs = []
    n = 0
    for d, period in days:
        if period in ("2026-09", "2026-10"):
            if n >= 40:
                continue
            n += 1
            recs.append(
                {
                    "school": "Test High",
                    "student": "synth-test-0002",
                    "date": d.isoformat(),
                    "period": period,
                    "enrolled": 1,
                    "present": 1,
                }
            )
        elif period == "2026-11":
            recs.append(
                {
                    "school": "Test High",
                    "student": "synth-test-0002",
                    "date": d.isoformat(),
                    "period": period,
                    "enrolled": 0,  # unenrolled all November
                    "present": 0,
                }
            )
    df, _ = build_survival_data(recs)
    # no November enrolled days -> skipped entirely (no forecast window)
    assert len(df) == 0


def test_determinism():
    df1, _ = _district_df()
    df2, _ = _district_df()
    assert df1[["duration", "event"]].equals(df2[["duration", "event"]])


def test_cox_c_index_beats_random_by_margin():
    df, features = _district_df()
    feats = [f for f in features if f != "first30_rate"]
    cph = fit(df, feats, strata=STRATA)
    ep = event_probability(cph, df, feats, strata=STRATA)
    c = concordance_index(df["duration"].values, df["event"].values, ep)
    assert c > 0.65, f"C-index {c} must beat random by a real margin"


def test_stratified_ph_assumption_holds():
    df, features = _district_df()
    feats = [f for f in features if f != "first30_rate"]
    cph = fit(df, feats, strata=STRATA)
    _, violations = ph_assumption_check(cph, df, feats, strata=STRATA)
    assert violations == [], f"PH violations after stratification: {violations}"


def test_calibration_tracks_observed():
    df, features = _district_df()
    feats = [f for f in features if f != "first30_rate"]
    cph = fit(df, feats, strata=STRATA)
    rows = calibration_at_horizons(cph, df, feats, strata=STRATA)
    assert len(rows) == 15  # 3 horizons x 5 bins
    worst = max(abs(r["mean_predicted"] - r["observed_rate"]) for r in rows)
    assert worst < 0.15, f"worst calibration gap {worst} too large"


def test_risk_tiers_cover_and_separate():
    df, features = _district_df()
    feats = [f for f in features if f != "first30_rate"]
    cph = fit(df, feats, strata=STRATA)
    tiers = risk_tiers(cph, df, feats, strata=STRATA)
    assert len(tiers) == len(df)
    assert set(tiers) <= {"high", "medium", "low"}
    rates = {}
    for tier in ("high", "medium", "low"):
        mask = np.array(tiers) == tier
        rates[tier] = df["event"].values[mask].mean()
    assert rates["high"] > rates["medium"] > rates["low"], rates


def test_median_days_sane():
    df, features = _district_df()
    feats = [f for f in features if f != "first30_rate"]
    cph = fit(df, feats, strata=STRATA)
    meds = median_days_to_event(cph, df, feats, strata=STRATA)
    assert len(meds) == len(df)
    known = [m for m in meds if m is not None]
    assert known, "at least some students should have a finite median"
    assert all(1 <= m <= 21 for m in known)


def test_fallback_needs_no_model():
    assert abs(predict_fallback({"first30_rate": 0.85}) - 0.15) < 1e-9
    assert abs(predict_fallback({"first30_rate": 0.50}) - 0.50) < 1e-9


def test_no_student_ids_in_tier_output():
    df, features = _district_df()
    feats = [f for f in features if f != "first30_rate"]
    cph = fit(df, feats, strata=STRATA)
    tiers = risk_tiers(cph, df, feats, strata=STRATA)
    assert not any("synth-" in t for t in tiers)
