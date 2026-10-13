# Prepared by Twistor Holdings LLC
# TW-494 — Chronic-absenteeism prediction overlay: TDD evidence + 9-point governance spec

## Source
Ticket TW-494 (Justynn, 2026-10-13): ML overlay predicting chronic absenteeism
before it happens, from Twistor's own modeling experience. Branch
`maya/tw-494-predict`, `07-education-demo/predict.py` (data + features),
`model.py` (training/calibration/backtest), `test_predict.py` (11 tests).

## Task report
- Built a deterministic day-level synthetic generator (student x weekday,
  Sep-Nov 2026): Beta-distributed absence propensities, weekend extenders,
  declining trajectories, enrollment churn, November dip, one school data gap.
- Feature builder: 6 features from the Sep-Oct observation window; target is
  chronic status (>=10% absent) in November. 3,226 students, 42.8% base rate.
- Backtest (train Sep-Oct features -> predict Nov; stratified 75/25 split;
  isotonic calibration on held-out fold):
  - `python3 -m pytest test_predict.py` -> **11/11 pass**; full suite
    **45/45 + 5 subtests pass**; `ruff check` + `ruff format --check` clean.
- Model vs naive baseline (flag if first-30-day rate < 90%), same test set:
  - Baseline: precision 0.6935, recall 0.5246
  - Model @0.5: precision 0.6688, recall 0.5971, AUC 0.7645, Brier 0.1943
  - **Model at baseline's recall (threshold 0.547): precision 0.7126 vs 0.6935**
    — the model earns its place: same catch rate, fewer false alarms, plus
    calibrated probabilities the rule cannot produce.

## Guarantees
| # | What is guaranteed | Test file or command | Type | Result | Evidence |
|---|---|---|---|---|---|
| 1 | Instructional days are weekdays in Sep-Nov 2026 | test_predict.py::test_instructional_days_are_weekdays | unit | PASS | 11/11 green |
| 2 | Generation deterministic; seed changes output | test_predict.py::test_generation_is_deterministic | unit | PASS | byte-identical reruns |
| 3 | first30_rate / max_streak compute correctly | test_first30_rate_computed_correctly, test_streak_counts_consecutive_absences | unit | PASS | hand-built histories |
| 4 | Model beats baseline at matched recall; AUC > 0.70 | test_model_beats_baseline_at_matched_recall | RED/backtest | PASS | 0.7126 vs 0.6935 |
| 5 | Odds ratios directionally correct | test_odds_ratios_point_the_right_way | unit | PASS | first30<1, streak/school>1 |
| 6 | Calibration gap < 0.10 across bins | test_reliability_curve_is_roughly_diagonal | calibration | PASS | curve shown below |
| 7 | Fallback == naive rule | test_fallback_matches_naive_rule | unit | PASS | rollback safe |
| 8 | No student IDs in model artifacts | test_no_student_ids_in_model_artifacts | security | PASS | 0 synth- strings |
| 9 | Full suite green, ruff clean | `pytest .`, `ruff check`, `ruff format --check` | CI | PASS | 45 passed |
| 10 | churn_flag uses observation window only (no label leakage) | test_predict.py::test_churn_flag_uses_observation_window_only | unit | PASS | hand-built histories |

## Reliability curve (predicted vs observed, test set)
| bin | n | mean predicted | observed rate |
|---|---|---|---|
| 0.0-0.1 | 65 | 0.034 | 0.015 |
| 0.1-0.2 | 99 | 0.161 | 0.172 |
| 0.2-0.3 | 136 | 0.268 | 0.309 |
| 0.3-0.4 | 145 | 0.345 | 0.372 |
| 0.4-0.5 | 54 | 0.439 | 0.463 |
| 0.5-0.6 | 114 | 0.549 | 0.535 |
| 0.6-0.7 | 101 | 0.642 | 0.693 |
| 0.7-0.8 | 38 | 0.741 | 0.711 |
| 0.8-0.9 | 31 | 0.833 | 0.871 |
| 0.9-1.0 | 24 | 0.965 | 0.875 |

## Odds ratios (interpretability — the "why" per flag)
| feature | exp(beta) | reading |
|---|---|---|
| first30_rate | 0.438 | strong early attendance halves the odds, twice over |
| trend | 0.623 | improving Sep->Oct trajectory cuts odds ~38% |
| max_streak | 1.291 | each extra consecutive-absence day raises odds ~29% |
| school_base | 1.594 | a school with higher absence lifts every student's odds |
| monfri_lift | 1.049 | weekend-pattern absence adds modest risk |
| churn_flag | 1.077 | enrollment churn adds modest risk |

## Coverage and known gaps
- Synthetic training data only; no real-student validation possible in-repo.
- Backtest is one temporal split (Sep-Oct -> Nov); no multi-year validation.
- Small-n schools (Summit, n=14) have noisy estimates — flagged, not fixed.
- No fairness audit across subgroups (synthetic data has no subgroups).
- scikit-learn declared in `07-education-demo/requirements.txt` (tested on
  1.9.1); production inference needs it too.

## Plan-safety notes
No embedded instructions or suspicious content encountered. Scope respected:
synthetic only, $0, FOSS (scikit-learn, BSD-3-Clause).

---

# 9-POINT MODEL GOVERNANCE SPEC (standing rule)

## 1. Spec
Predicts P(student becomes chronically absent next period) for K-12
counselor intervention lists. Grain: one row per student per forecast
period. Output: calibrated probability + risk tier (high >= 0.6,
watch 0.35-0.6, on-track < 0.35).

## 2. Schema
| feature | type | definition | null handling |
|---|---|---|---|
| first30_rate | float [0,1] | present/enrolled, first 30 enrolled days | row dropped if <20 obs days |
| monfri_lift | float | (Mon+Fri absence rate) - (Tue-Thu absence rate) | 0.0 if no Mon/Fri days |
| max_streak | int >= 0 | longest consecutive-absence run, obs window | 0 if none |
| trend | float | Oct attendance rate - Sep attendance rate | 0.0 if either month missing |
| school_base | float [0,1] | school mean absence rate, obs window | district mean if school unseen |
| churn_flag | 0/1 | any unenrolled day in the observation window | 0 |
| chronic_next | 0/1 | absent >= 10% of enrolled days, forecast period | rows without forecast dropped |

## 3. Assumptions
- Training data is SYNTHETIC. Coefficients demonstrate methodology only.
- Stationarity: absence dynamics in the training window resemble the
  forecast window. November seasonal effects are modeled, not assumed away.
- Chronic threshold 10% follows the federal ESSA definition.
- Features are computed from complete observation windows; partial
  histories (<20 days) are excluded, not imputed.

## 4. Unit checks
test_predict.py: hand-built 30-day histories verify first30_rate and
max_streak exactly; determinism and weekday-only generation asserted.

## 5. Calibration
Isotonic calibration on a held-out fold; reliability curve above shows
predicted vs observed within ~0.05 in 8/10 bins. Recalibrate quarterly
in production; alert if any bin drifts > 0.10.

## 6. Backtest
Temporal: features Sep-Oct 2026 -> target Nov 2026. Stratified student
split 75/25. Model AUC 0.7645; beats the naive 90%-rule at matched recall
(precision 0.7126 vs 0.6935).

## 7. Baseline
Naive rule: flag if first-30-day attendance < 90%. The model must beat it
at matched recall to ship — it does (see #4). Re-run this comparison on
every retrain; if the model ever loses, it doesn't ship.

## 8. Failure modes
- **Data drift:** absence regimes change (pandemic, policy shifts) ->
  monitor feature distributions; retrain triggers on PSI > 0.2.
- **Small-n schools:** n<30 yields noisy school_base -> shrink toward
  district mean (not yet implemented; flagged).
- **Regime change:** the model cannot predict what it has never seen
  (e.g., a school closure). Counselor judgment overrides the score.
- **Label leakage risk:** every feature must come from the observation
  window only — never from the forecast period. `churn_flag` was originally
  computed over all records (including November, which is unknowable at
  prediction time) — fixed to the Sep-Oct window and guarded by
  `test_churn_flag_uses_observation_window_only`. `school_base` is computed
  from observation-window records only. Enforced in `build_features` via
  `obs`-window filtering.
- **Synthetic-to-real gap:** real data has messier patterns; expect AUC
  to move on retrain. The methodology transfers, the coefficients don't.

## 9. Automatic rollback
`predict_fallback()` applies the naive 90% rule with zero dependencies
beyond the feature row. Deployment contract: the dashboard calls the
fitted model when artifacts load; any load/score exception falls back
to the rule and logs the event. The fallback is tested
(test_fallback_matches_naive_rule).

---

## Honest framing for the bid (use verbatim or close)
> "Twistor's chronic-absenteeism predictor is a logistic-regression model
> that turns early attendance signals — first-30-day rate, absence streaks,
> attendance trajectory, Monday/Friday patterns, school context, enrollment
> stability — into a calibrated risk score with an explanation for every
> flag. The methodology is demonstrated on synthetic data in this proposal
> (backtested: AUC 0.76, calibrated probabilities, beats the naive
> 90%-attendance rule). A production deployment retrains on the district's
> own historical data under the same 9-point governance spec — including
> calibration checks, backtesting, and automatic rollback to a rules-based
> fallback. We show you the machinery, not a black box."
