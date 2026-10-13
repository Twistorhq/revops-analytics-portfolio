# Prepared by Twistor Holdings LLC
# TW-495: Cox proportional-hazards overlay — WHEN does a student cross the
# chronic-absenteeism line?
#
# Landmark analysis at end of October (the standard way to use covariates
# that need the observation window):
#   cohort: students NOT yet chronic (absent < 10% of enrolled days) through
#           Oct, with >= 20 enrolled days in Sep-Oct and November data present
#   T:      instructional days from Nov 1 to the first day the cumulative
#           (from Sep 1) absent/enrolled ratio reaches 10%; censored at 21
#           (the last November instructional day) if never reached
#   X:      the same 6 Sep-Oct features as TW-494 — no forecast-window data
#
# Math: h(t|x) = h0(t) * exp(b.x). The baseline hazard h0(t) is shared by
# all students; covariates shift it multiplicatively. exp(bi) is the hazard
# ratio per unit of feature i — e.g. 1.3 means 30% higher instantaneous risk
# of crossing the chronic line on any given day, holding the rest fixed.
# Cox (1972) partial likelihood estimates b without specifying h0, so the
# model makes no assumption about the shape of absence risk over time —
# only that covariate effects are proportional (tested, not assumed).
#
# Methodology demonstrator: trains on SYNTHETIC data. A production
# deployment retrains on the district's real historical data — the
# synthetic-trained coefficients do not transfer; the methodology does.

import datetime as dt

import numpy as np
import pandas as pd
from lifelines import CoxPHFitter
from lifelines.statistics import proportional_hazard_test

from predict import (
    CHRONIC_THRESHOLD,
    OBSERVE_PERIODS,
    _absence_streak_max,
    instructional_days,
)

NOV_PERIOD = "2026-11"
LANDMARK_PERIODS = OBSERVE_PERIODS  # Sep-Oct: features and landmark window
MIN_OBS_DAYS = 20


def _nov_days():
    return [d for d, p in instructional_days() if p == NOV_PERIOD]


def build_survival_data(records):
    """One row per landmark-eligible student.

    Columns: student, school, duration (instructional days from Nov 1 to
    event/censoring), event (1 = crossed the 10% line in November),
    plus the 6 Sep-Oct features (identical definitions to TW-494's
    build_features — same code paths, no forecast-window leakage).
    """
    nov_days = _nov_days()
    horizon = len(nov_days)
    by_student = {}
    for r in records:
        by_student.setdefault(r["student"], []).append(r)
    for recs in by_student.values():
        recs.sort(key=lambda r: r["date"])

    # school base rates over the observation window (same as TW-494)
    school_absent, school_enrolled = {}, {}
    for student, recs in by_student.items():
        obs = [r for r in recs if r["period"] in LANDMARK_PERIODS and r["enrolled"]]
        a = sum(1 for r in obs if not r["present"])
        school_absent[recs[0]["school"]] = school_absent.get(recs[0]["school"], 0) + a
        school_enrolled[recs[0]["school"]] = school_enrolled.get(
            recs[0]["school"], 0
        ) + len(obs)

    rows = []
    for student, recs in sorted(by_student.items()):
        school = recs[0]["school"]
        obs = [r for r in recs if r["period"] in LANDMARK_PERIODS and r["enrolled"]]
        obs_any = [r for r in recs if r["period"] in LANDMARK_PERIODS]
        nov = [r for r in recs if r["period"] == NOV_PERIOD and r["enrolled"]]
        if len(obs) < MIN_OBS_DAYS or not nov:
            continue
        # landmark: must not already be chronic through October
        a_oct = sum(1 for r in obs if not r["present"])
        if a_oct / len(obs) >= CHRONIC_THRESHOLD:
            continue
        # event time: first Nov day cumulative-from-Sep ratio hits 10%
        nov_by_date = {r["date"]: r for r in nov}
        A, E = a_oct, len(obs)
        duration, event = horizon, 0
        for i, d in enumerate(nov_days, start=1):
            r = nov_by_date.get(d.isoformat())
            if r is None:
                continue  # data-gap day: no record, clock keeps ticking
            E += 1
            if not r["present"]:
                A += 1
            if A / E >= CHRONIC_THRESHOLD:
                duration, event = i, 1
                break
        # 6 features — same definitions as TW-494 build_features
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
        rows.append(
            {
                "school": school,
                "student": student,
                "duration": duration,
                "event": event,
                "first30_rate": first30_rate,
                "monfri_lift": mf_rate - mid_rate,
                "max_streak": _absence_streak_max(obs),
                "trend": oct_rate - sep_rate,
                "school_base": school_absent[school] / school_enrolled[school],
                "churn_flag": 1 if any(r["enrolled"] == 0 for r in obs_any) else 0,
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
    return pd.DataFrame(rows), features


def add_first30_strata(df, n_bins=3):
    """Tertile strata for first30_rate — used when the PH assumption fails
    for that covariate (Schoenfeld p < 0.05). Stratification lets each
    tertile have its own baseline hazard instead of forcing one
    proportional effect."""
    labels = [f"q{i + 1}" for i in range(n_bins)]
    df = df.copy()
    df["first30_stratum"] = pd.qcut(df["first30_rate"], n_bins, labels=labels)
    return df


def fit(df, features, penalizer=0.1, strata=None):
    """Fit Cox PH. Deterministic — no random seed needed.

    strata: optional list of categorical columns for stratification
    (separate baseline hazard per stratum, no coefficient estimated).
    Returns the fitted CoxPHFitter.
    """
    cph = CoxPHFitter(penalizer=penalizer)
    cols = ["duration", "event"] + features + (strata or [])
    cph.fit(df[cols], duration_col="duration", event_col="event", strata=strata)
    return cph


def concordance_index(durations, events, risk_scores):
    """Harrell's C: fraction of comparable pairs the risk ordering gets right.

    A pair (i, j) is comparable when the earlier event time is observed
    (not censored). Higher risk score should mean earlier event.
    0.5 = random, 1.0 = perfect ordering.
    """
    t = np.asarray(durations, dtype=float)
    e = np.asarray(events, dtype=int)
    r = np.asarray(risk_scores, dtype=float)
    order = np.argsort(t, kind="stable")
    t, e, r = t[order], e[order], r[order]
    concordant = discordant = tied = 0
    n = len(t)
    for i in range(n):
        if e[i] == 0:
            continue  # censored at t[i]: only usable as the later member
        for j in range(i + 1, n):
            if t[j] == t[i]:
                continue  # tied times: not comparable
            # i had the event earlier; j survived at least to t[i]
            if r[i] > r[j]:
                concordant += 1
            elif r[i] < r[j]:
                discordant += 1
            else:
                tied += 1
    total = concordant + discordant + tied
    if total == 0:
        return 0.5
    return (concordant + 0.5 * tied) / total


def risk_scores(cph, df, features, strata=None):
    """Partial hazard exp(b.x): higher = earlier expected crossing.

    Within-stratum ordering. For cross-stratum comparison use
    event_probability() — partial hazards are not comparable across
    different baseline hazards.
    """
    cols = features + (strata or [])
    ph = cph.predict_partial_hazard(df[cols])
    return ph.reindex(df.index).values.ravel()


def event_probability(cph, df, features, strata=None, horizon=21):
    """P(cross the chronic line within `horizon` instructional days).

    Comparable across strata — the right risk score for cohort-wide
    ordering and for the counselor-facing risk tiers.
    """
    cols = features + (strata or [])
    curves = cph.predict_survival_function(df[cols])
    avail = curves.index[curves.index <= horizon]
    t = int(avail.max())
    return 1.0 - curves.loc[t].reindex(df.index).values.ravel()


def survival_curves(cph, df, features, strata=None):
    """Per-student survival function S(t|x) over the November window."""
    cols = features + (strata or [])
    return cph.predict_survival_function(df[cols])


def calibration_at_horizons(
    cph, df, features, horizons=(7, 14, 21), n_bins=5, strata=None
):
    """Predicted P(T <= t) vs Kaplan-Meier observed, per risk quintile.

    Returns a list of dicts: horizon, bin, n, mean_predicted, observed_rate.
    Well-calibrated: observed tracks predicted within each bin.
    """
    from lifelines import KaplanMeierFitter

    curves = survival_curves(cph, df, features, strata=strata)
    out = []
    for t in horizons:
        if t not in curves.index:
            # nearest available time point at or below t
            avail = curves.index[curves.index <= t]
            if len(avail) == 0:
                continue
            t = int(avail.max())
        p_event = 1.0 - curves.loc[t].reindex(df.index).values
        order = np.argsort(p_event, kind="stable")
        bins = np.array_split(order, n_bins)
        for b, idx in enumerate(bins):
            sub = df.iloc[idx]
            kmf = KaplanMeierFitter()
            kmf.fit(sub["duration"], sub["event"])
            observed = float(1.0 - kmf.predict(t))
            out.append(
                {
                    "horizon_days": int(t),
                    "bin": b + 1,
                    "n": len(idx),
                    "mean_predicted": round(float(p_event[idx].mean()), 4),
                    "observed_rate": round(observed, 4),
                }
            )
    return out


def ph_assumption_check(cph, df, features, alpha=0.05, strata=None):
    """Schoenfeld-residuals test per covariate. Returns (p_values, violations).

    p < alpha rejects proportional hazards for that covariate — the effect
    is not constant over time. Callers must not hide violations: stratify
    or report them as a limitation.
    """
    cols = ["duration", "event"] + features + (strata or [])
    results = proportional_hazard_test(cph, df[cols], time_transform="rank")
    p_values = {f: round(float(results.summary.loc[f, "p"]), 4) for f in features}
    violations = [f for f, p in p_values.items() if p < alpha]
    return p_values, violations


def median_days_to_event(cph, df, features, strata=None):
    """Predicted median instructional days from Nov 1 to crossing.

    None when the curve never drops to 0.5 within the 21-day window —
    reported as '>21 days', not extrapolated.
    """
    curves = survival_curves(cph, df, features, strata=strata)
    out = []
    for idx in df.index:
        below = curves.index[curves[idx] <= 0.5]
        out.append(int(below.min()) if len(below) else None)
    return out


def risk_tiers(cph, df, features, horizon=21, high=0.5, medium=0.2, strata=None):
    """Counselor-facing tiers from P(cross within `horizon` days).

    high:   P >= 0.5 — intervene now
    medium: 0.2 <= P < 0.5 — watch list
    low:    P < 0.2 — routine monitoring
    """
    curves = survival_curves(cph, df, features, strata=strata)
    avail = curves.index[curves.index <= horizon]
    t = int(avail.max())
    p_event = 1.0 - curves.loc[t].reindex(df.index).values
    tiers = []
    for p in p_event:
        if p >= high:
            tiers.append("high")
        elif p >= medium:
            tiers.append("medium")
        else:
            tiers.append("low")
    return tiers


def compare_risk_ordering(durations, events, cox_risk, logistic_proba):
    """Fair fight on identical data: Harrell's C for each risk ordering.

    Higher score = higher risk = earlier event, for both models.
    """
    return {
        "cox_c_index": round(concordance_index(durations, events, cox_risk), 4),
        "logistic_c_index": round(
            concordance_index(durations, events, logistic_proba), 4
        ),
    }


def predict_fallback(row):
    """Rollback: rank risk by first-30-day rate (lower = riskier).

    Returns a risk score usable in place of the Cox partial hazard when
    the fitted model is unavailable. No model, no calibration — the
    dashboard must prefer the fitted model and fall back without error.
    """
    return 1.0 - row["first30_rate"]
