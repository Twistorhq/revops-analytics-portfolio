# Prepared by Twistor Holdings LLC

# TW-492 evidence: NKC chart variation — TDD report

## 1. Source

- Ticket: **TW-492** — "NKC dashboard chart variation" (reporter: Justynn)
- Brief: the trend chart needs to "showcase much more variation" — each school
  needs its own visible trajectory so the chart reads like a real district.
  The only revision asked: more variation. Deadline: Fri Oct 16, 1pm Denver.
- Branch: `sofia/tw-492-chart-variation` (Twistorhq/revops-analytics-portfolio),
  commit `b51659d`, on top of the merged TW-490 dashboard upgrade
  (`ab5318e`, PR #2).

## 2. Task report

Per behavior: what was built, the validation command actually run, and the outcome.

**Per-school trajectory generation (importer.py, +54/-38 lines, strictly additive):**
- Each school in `DISTRICT_SCHOOLS` gets a `trend` option: per-period
  absence-probability deltas (sep, oct, nov) applied on top of the base rate
  at the per-student propensity step — before the shared `NOVEMBER_DIP`, so
  both the school's own story and the seasonal bump show in the data.
- The eight stories: Brookfield (steady top, near-perfect), Cedar Ridge
  (climbing turnaround), Maple Grove (declining), Riverside (volatile),
  Harlow (worsening struggler w/ chronic cluster), Westfield (data gap),
  Northgate (flu-hit), Summit (tiny, noisy).
- Propensity clamped to `[0.001, 0.60]` — trends can never push it negative or
  absurd; the generator stays honest at the edges. Verified in source.
- `demo_csv()`/`demo_mapping()` untouched — TW-486 behavior preserved.
- Determinism verified: `demo_district_csv()` twice → **byte-identical**,
  9,082 lines (9,081 data rows + header), same count as TW-490.

**Spread threshold (test_dashboard.py):** new `test_chart_spread_exceeds_threshold`
asserts every period's max–min school spread exceeds 8 points.
- Measured on the new data: 2026-09 **13.0%**, 2026-10 **14.0%**, 2026-11
  **17.1%** — all pass. (The increase over TW-490 is modest because base rates
  already varied; the *shape* of the lines is what changed — see trajectories.)

**Distinct trajectories (test_dashboard.py):** new `test_distinct_trajectories`
asserts named stories on real rates (not deltas-of-deltas):
- Cedar Ridge Sep→Oct: **+2.5pp** (requires >2pp) ✓
- Harlow Sep→Oct: **−1.9pp** (requires <−1pp) ✓
- Riverside: **+6.5pp** then **−9.5pp** (requires >+4pp and <−4pp) ✓
- Measured values: Cedar Ridge 91.1%→93.6%→92.3%; Harlow 86.6%→84.7%→79.8%;
  Riverside 90.8%→97.3%→87.8%.

**4-label chart (dashboard.py):** `_extreme_schools` (2 labels: top + bottom)
→ `_labeled_schools` (top-2 + bottom-2). Alternate labels stagger vertically
(`dy = 4` / `−10`) so neighboring lines' labels don't collide.
- Old render (TW-490) SVG labels: **2** (Brookfield, Summit Alternative).
- New render SVG labels: **4** (Brookfield, Cedar Ridge, Summit Alternative,
  Harlow) — and the stagger is confirmed in the markup.

**No-leakage:** render probes — `grep -c synth-` on the new page → **0**;
"SYNTHETIC SAMPLE DATA" banner present; 1 `<svg>`; 8 schools, 12 metric rows.

**Validation commands run (fresh, this session):**
- `python3 -m pytest test_attendance.py test_importer.py test_dashboard.py -q`
  → **37 passed, 5 subtests passed in 5.79s** (GREEN). (8 attendance + 13 importer + 16 dashboard — dashboard gained the 3 TW-492 tests.)
- `ruff check` on the four demo files → **All checks passed** (GREEN).
- `ruff format --check` on the four TW-492 files → clean (one reformat applied
  to the new `_school_series` helper before commit; pre-existing drift in
  `attendance.py`/`test_attendance.py` left untouched per Rosa's deadline note).
- Independent behavioral probes: determinism, per-period spreads, trajectory
  values, label counts on old vs. new renders, leakage scan (all GREEN).

**RED notes (honest):** I did not capture separate RED run logs in this
session. Against the old TW-490 generator, checked out and run directly:
- `test_distinct_trajectories` **FAILS** on old data (Cedar Ridge +0.4pp, not
  >2pp; Harlow −0.8pp, not <−1pp; Riverside swings +1.0pp/−3.9pp, missing the
  ±4pp bars) — genuine RED, the trajectories are new behavior.
- `test_chart_spread_exceeds_threshold` **PASSES** on old data (old spread was
  11.8–13.2%) — it is a guardrail against future flattening, not a RED
  differentiator. Stated plainly so the record is honest.
- The 2→4 label change was verified behaviorally on old vs. new renders
  (2 vs. 4 school-name `<text>` elements in the SVG), which the old render
  cannot satisfy.

## 3. Guarantees table

| # | What is guaranteed | Test file or command | Type | Result | Evidence |
|---|---|---|---|---|---|
| 1 | Full suite green, nothing regressed | `python3 -m pytest test_attendance.py test_importer.py test_dashboard.py -q` | unit | 37 passed + 5 subtests, 5.79s | this session, terminal output |
| 2 | Every period's school spread exceeds 8pp | `test_chart_spread_exceeds_threshold` in test_dashboard.py | unit | pass (13.0/14.0/17.1%) | measured values above |
| 3 | Cedar Ridge climbs, Harlow falls, Riverside swings hard | `test_distinct_trajectories` in test_dashboard.py | unit | pass (+2.5/−1.9/+6.5/−9.5pp) | measured values above |
| 4 | Four schools labeled on the chart | `test_four_schools_labeled_on_chart` in test_dashboard.py + render probe | unit/manual | pass; 4 SVG labels | label lists above |
| 5 | Generator deterministic across runs | `demo_district_csv()` called twice | unit | byte-identical | terminal output |
| 6 | Propensity never leaves [0.001, 0.60] | source inspection, `test_dashboard.py` suite | unit | clamp present, tests pass | source line + suite |
| 7 | No student IDs in rendered output | `grep -c synth-` on page; `test_no_student_ids_leak` | unit | 0 matches | terminal output |
| 8 | TW-486 demo_csv() behavior preserved | `test_importer.py` full file | unit | 13/13 pass | suite run |
| 9 | Ruff lint + format clean on changed files | `ruff check` / `ruff format --check` | CI | pass | terminal output |

## 4. Coverage and known gaps

- No RED run logs captured this session; the RED case is established by the
  old-generator runs documented above. State it or it reads as "everything
  covered."
- No browser test of the staggered SVG labels (unittest + markup probes only).
- The spread test is a guardrail, not a differentiator (passes on old data).
- Trajectory stories are asserted at the school level; per-student Beta
  propensity draws are seeded but not individually asserted.
- Westfield's data gap predates TW-492 (TW-490) and is unchanged; the gap-break
  behavior is covered by TW-490's tests.

## 5. Plan-safety notes

- No embedded instructions, suspicious strings, or unexpected network/file
  behavior anywhere in the diff. Scope respected: synthetic data only, stdlib
  only, $0, no new dependencies.
- The diff is 138 insertions/25 deletions across 3 files (+ this report) —
  under the 400-line split threshold. `demo_csv()`/`demo_mapping()` provably
  untouched.
