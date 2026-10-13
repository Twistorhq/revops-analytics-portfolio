# Twistor education analytics: synthetic first slice

Owner authorization: Justynn requested scope and development for both pursuits on October 12, 2026. Development is authorized, not submission, spending, signatures or buyer commitments.

## Scope and deadline

Official source: https://www.nkcschools.org/district/dept/purchasing

North Kansas City Schools' data dashboard RFP closes October 16, 2026 at 2 PM Central (1 PM Denver). Questions closed October 9. Complete packet, addenda, required references, forms, integrations and scoring are not yet reviewed. No claim that a prototype qualifies as the requested platform. Prior research park decision is superseded for internal development only.

First thin workflow: synthetic attendance source → validated student/school/period grain → scoped aggregate → source hash and KPI definition → future dashboard.

## Implemented

attendance.py uses Python standard library only. It rejects duplicate grain, invalid counts and empty access scope. It scopes records before aggregation and calculates weighted attendance as total present days / total enrolled days, not an average of individual rates. Zero denominator returns null. Output is aggregate-only, deterministic and labeled sample data.

Eight focused tests pass, including cross-district/school filtering, duplicates, counts, null/empty cases and rerun stability. Demo returns 28/30 North and 19/20 South attendance days. These are fictional values, not NKC data or approved definitions.

This adapter follows the existing pipeline's validate-before-gold pattern; it does not copy the legacy commerce schema or modify existing ETL. A real authorized SIS export adapter is a later integration. Scope inputs must be derived from authenticated identity server-side. This function is not an authentication/security boundary, does not protect stored raw records and is not FERPA certification. Small-cell suppression and student-level disclosure rules are unimplemented.

## Next iterations

1. Browser dashboard, source reconciliation panel and filters: 6–10 developer hours.
2. Import mapping/error quarantine and role integration: 6–10 hours, synthetic inputs only until authorized.
3. Keyboard/mobile checks, role-denial tests, requirements matrix and demo rehearsal: 4–6 hours.

Proposed checkpoints: October 13 requirements gate; October 14 demo review; October 15 bid go/no-go and claim freeze; October 16 owner-approved submission only if every mandatory gate is met. Estimates exclude full production implementation and share capacity with the property-document track. No unattended background execution or deadline guarantee is implied.

## Minimum demonstrator acceptance

District/school filters reconcile to scoped source totals; zero/invalid/duplicate cases are explicit; no cross-scope rows appear; hashes change on source changes; reruns match; metric denominator/period and sample labels visible; keyboard/mobile navigation works. Browser, real authentication, SIS, assessment, behavior, privacy, hosting and support remain outside iteration 1.

## Owner/paperwork gate

Obtain the full official e-bidding packet and addenda using approved business contact details. Confirm legal bidder identity, authorized signer, any required references, insurance, E-Verify/debarment/work-based-learning forms and whether a prototype/custom build is responsive. Secondary summaries are not sufficient. No account or application was created here. If mandatory gates cannot be met, keep building reusable capability but do not submit an unsupported bid.

## Run

python -m unittest discover -s 07-education-demo -v
python 07-education-demo/attendance.py

No API keys, real student records or incremental cash spend. Existing ETL/product-wide suites were not rerun for this new isolated slice.

## Import workflow + dashboard (October 13)

**importer.py** — CSV import with explicit column mapping, rejected-row
diagnostics, and reconciled totals. Mapping problems (missing field, mapped
header absent from the CSV) fail fast with ValueError. Row-level problems
become Rejections carrying row number, reason code
(missing_identifier | bad_count | invalid_counts | duplicate_grain), a
human-readable detail, and the raw row. `publish()` blocks while any row is
rejected or totals don't reconcile (source == accepted + rejected).

**dashboard.py** — renders the published mart as a self-contained HTML page
(stdlib only, no external assets): district headline rate with period-over-period
delta, hand-built SVG trend chart (per-school lines + district average; data gaps
break the line, never interpolated), school x period performance table with
school + period filters (vanilla JS), explicit data-gap rows, small-n flags, and
a methodology section documenting the formula, grain, and null handling.
Aggregate only — no student-level data reaches the page. Every render carries
the "SYNTHETIC SAMPLE DATA" banner. Impeccable detector: 0 anti-patterns.

**demo_district_csv()** (importer.py, TW-490/TW-493) — richer synthetic district
alongside the original `demo_csv()`: 12 real NKC school names x 3 periods
(~8,800 students, deterministic; names are the district's public roster,
all data synthetic). Edge cases: near-perfect school (Staley ~98%), struggling
school with chronic-absence cluster (Antioch ~87%), district-wide November dip
(flu season), one school missing a whole period (New Mark Oct data gap),
mid-year transfer students, tiny alternative center (Golden Oaks, n=18).
Per-student absence propensity drawn from a Beta distribution around the
school base rate (overdispersed, like real schools). `demo_district_daily_csv()`
(TW-493) emits the same trials at daily grain — Mon-Fri instructional calendar,
DayOfWeek per row — so streak and weekday metrics reconcile exactly with the
monthly rows. Strictly additive — `demo_csv()` untouched.

**Metric definitions** (one definition per metric, everywhere):
- attendance_rate = SUM(present_days) / SUM(enrolled_days), weighted across
  records; never an average of per-record rates; null when denominator is 0.
- Grain: one record per (district, school, student, period); daily grain is
  one record per (student, instructional day) in `metrics.py`.
- chronic_early_warning = students with first-30-day absence pace >= 10% /
  qualifying students — the predictive version of chronic absenteeism.
- monday_friday_ratio = (absent/enrolled on Mon+Fri) / (absent/enrolled on
  Tue-Thu); null when the midweek denominator is zero.
- streak3_students = students with a 3+ consecutive-absent-day streak /
  all students (streaks run over consecutive instructional days).
- recovery_rate = chronic-in-Sep students back under 10% in Oct /
  chronic-in-Sep students; null when none were chronic.
- instructional_days_lost = SUM(1 - present) over all student-days;
  each lost day is a day of attendance-based funding not earned.

**Run**
```
python -m unittest discover -s 07-education-demo
python 07-education-demo/importer.py   # import report + published summary
python 07-education-demo/dashboard.py  # writes attendance-dashboard.html
```

49 tests pass (8 attendance + 13 importer + 16 dashboard + 12 metrics). All data synthetic;
school names are the district's real public roster; no real student records, ever.
