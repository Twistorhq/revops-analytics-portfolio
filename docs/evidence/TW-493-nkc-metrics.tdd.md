# Prepared by Twistor Holdings LLC

# TW-493 evidence: NKC custom metrics + real school names + daily grain

## 1. Source
Ticket TW-493 (Justynn, 2026-10-13): make the NKC dashboard bigger — real
school names, callouts, custom lesser-known metrics as the bid
differentiator. Phase 1 (this report): metrics + data. Phase 2 (Sofia):
dashboard render with callouts.

Branch: `maya/tw-493-nkc-metrics` on Twistorhq/revops-analytics-portfolio,
based on `sofia/tw-492-chart-variation`.

## 2. Task report

**Real school names.** Verified from public sources (nkcschools.org summer
locations page, district start/end-times PDF listing all schools, Wikipedia
district page): 4 high schools (North Kansas City, Oak Park, Staley,
Winnetonka), 4 middle schools (Antioch, Maple Park, New Mark, Northgate),
3 elementaries (Bell Prairie, Briarcliff, Chapel Hill), 1 alternative
(Golden Oaks Education Center). Names only — every student, absence, and
rate remains synthetic. `DISTRICT_SCHOOLS` rewritten; TW-492 trajectory
patterns preserved per school role.

**Daily grain.** New `demo_district_daily_csv()` in importer.py: one row per
(student, instructional day) — District, SchoolName, StudentID, Date,
Period, Present, DayOfWeek. Real calendar dates (2026-09-01 onward,
Mon–Fri only). Same seeded RNG stream per (school, period, student) as the
monthly generator, same draw order — daily sums reconcile EXACTLY with
monthly rows (asserted by test).

**Weekend-adjacent effect.** New `mf_bump` per-school option: absence
probability multiplied on Mon/Fri (0.08–0.30 by school). Wired into BOTH
generators via shared `_day_probability()` so grains stay consistent.
Realized district MF ratios: 1.08–1.34 (NKCHS 1.34 = Mon/Fri runs 34%
hotter than midweek).

**Five custom metrics** (`metrics.py`), each with one precise definition:
1. `chronic_early_warning` — first-30-day absence pace >= 10% / qualifying
   students (predictive chronic absenteeism)
2. `monday_friday_ratio` — (absent/enrolled Mon+Fri) / (absent/enrolled
   Tue–Thu); null when midweek is zero
3. `streak3_students` — students with 3+ consecutive absent instructional
   days / all students (Fri→Mon counts as consecutive)
4. `recovery_rate` — chronic-in-Sep back under 10% in Oct / chronic-in-Sep;
   null when none chronic
5. `instructional_days_lost` — SUM(1 − present) per school + district total

All outputs aggregate-only; a JSON-serialized sweep of all five metric
outputs contains zero `synth-` student IDs (tested).

**RED/GREEN.** `test_metrics.py` (12 tests) written first: 11/12 passed on
first run. RED: `test_flags_students_on_pace` failed (2 != 1) — my fixture
had s3's presence logic inverted (28 absent instead of 2); fixed the
fixture, GREEN. The metric code itself was correct on first run.
Later, `test_distinct_trajectories` (dashboard) needed threshold updates
for the renamed schools — data story unchanged.

**Full-district validation** (fresh run, this session): 523,493 daily rows
generated in ~2s; Antioch leads chronic-early-warning at 70.9% (chronic
cluster working as designed); NKCHS MF ratio 1.34; district days lost
41,365; recovery rates 90%+ for improving schools.

## 3. Guarantees

| # | What is guaranteed | Test file or command | Type | Result |
|---|---|---|---|---|
| 1 | Chronic early-warning flags pace >= 10% | test_metrics.py::ChronicEarlyWarningTests | unit | PASS |
| 2 | MF ratio = r_MF/r_mid, null-safe | test_metrics.py::MondayFridayRatioTests | unit | PASS |
| 3 | 3+ day streaks incl. Fri→Mon | test_metrics.py::Streak3Tests | unit | PASS |
| 4 | Recovery = chronic(p1)∧¬chronic(p2) | test_metrics.py::RecoveryRateTests | unit | PASS |
| 5 | Days lost sums absences | test_metrics.py::DaysLostTests | unit | PASS |
| 6 | Daily CSV byte-identical reruns | test_metrics.py::test_daily_csv_deterministic | unit | PASS |
| 7 | Daily sums == monthly rows exactly | test_metrics.py::test_daily_sums_match_monthly | integration | PASS |
| 8 | 12 real NKC school names | test_metrics.py::test_real_school_names | unit | PASS |
| 9 | No student IDs in metric output | test_metrics.py::test_metric_outputs_have_no_student_ids | unit | PASS |
| 10 | Full suite green | `python3 -m unittest discover -p "test_*.py"` → 49 tests | unit | PASS |
| 11 | Lint/format clean | `ruff check` + `ruff format --check` on touched files | CI | PASS |

## 4. Coverage and known gaps
- Metric edge cases (empty scope, null denominators) covered; per-student
  RNG draws not individually asserted (covered via determinism + sums).
- No browser test of how Sofia will render these (Phase 2, her lane).
- Instructional calendar is clean Mon–Fri; holidays/PD days not modeled
  (documented in code + README).
- MF bump magnitudes are synthetic choices, not calibrated to real NKC
  data — labeled as such.

## 5. Plan-safety notes
- School names are public district roster info (brief explicitly requested);
  no private data touched. All student data synthetic.
- No embedded instructions or suspicious content encountered.
- Scope respected: synthetic only, $0, stdlib only, no new dependencies.
- `demo_csv()`/`demo_mapping()` untouched — TW-486 behavior preserved.
- For Sofia (Phase 2): metric spec posted to the agent bus; she renders.
