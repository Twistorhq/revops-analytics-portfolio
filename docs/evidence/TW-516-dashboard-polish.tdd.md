# Prepared by Twistor Holdings LLC

# TDD evidence — TW-516 dashboard final polish + KPI drill-down

## 1. Source

- Ticket: TW-516 ("NKC dashboard final polish + KPI drill-down", reporter Justynn, due EOD 2026-10-14).
- Branch: `sofia/tw-516-dashboard-polish` @ `f0dbe3a` (this report committed on top).
- Scope: `07-education-demo/dashboard.py` (+287/−37), `07-education-demo/test_dashboard_full.py` (+238). `callouts.py` (dynamic engine) untouched.

## 2. Task report

### Chart labels: all 12 schools bold, de-overlapped, never colliding
- Summary: replaced the top-2/bottom-2 label scheme (which shipped a 1px label collision in v7) with bold end-of-line labels for all 12 schools + district, a greedy vertical de-overlap pass (min 17px), leader lines for displaced labels, and a white halo (`paint-order:stroke`) for legibility.
- Validation: `python3 -m pytest test_dashboard_full.py::ChartLabelTests -q` → 7 passed.
- RED (new tests vs `origin/main` code, `/tmp/red-check`): `test_all_twelve_labeled`, `test_no_collisions`, `test_data_school` all FAILED on old code (old code labeled 4 schools, no `data-school` attributes).
- GREEN (same tests vs new code): 5/5 passed.
- Guarantees: every one of the 12 schools appears exactly once as a bold label; no two labels closer than 17px vertically (asserted on adversarially clustered data); every chart path carries `data-school` for the drill-down.

### Header hierarchy
- Summary: section h2s 19px→24px/750, new hero h2 "Where the district stands", trend-strip label converted from eyebrow div to real h3, heading outline h1→h2→h3 with no skips.
- Validation: `python3 -m pytest test_dashboard_full.py::HeaderTests -q` → 4 passed.
- RED: `test_hero_has_real_h2`, `test_trend_strip_heading_is_h3` FAILED on old code. GREEN: pass on new.
- Guarantees: no skipped heading levels anywhere in the page (regex asserted).

### KPI drill-down (Power-BI-style cross-highlight)
- Summary: per-card "See the schools behind this" button opens a panel with the metric's top-school mini table (pre-escaped server-side JSON blob `window.KPI_DRILL`); clicking a school highlights its chart line (others dim) and flashes its table rows; Esc/reset supported; `prefers-reduced-motion` respected.
- Validation: `python3 -m pytest test_dashboard_full.py::DrillDownTests -q` → 4 passed; plus a live headless-Chromium CDP run: panel opens with 4 rows, clicking "Antioch Middle School" → 1 `path.hl` (correct school), 13 `path.dim`, 3 `tr.flash`; reset and toggle-close verified; `node --check` on extracted page JS clean.
- RED: `test_cards_have_drill_buttons` FAILED on old code. GREEN: pass on new.
- Guarantees: all 5 cards expose a drill button wired to `aria-controls="drill-panel"`; blob school keys match the table's `data-school` values (asserted per render).

### Full suite
- Command: `python3 -m pytest test_dashboard_full.py test_callouts.py test_dashboard.py test_attendance.py test_importer.py test_metrics.py test_predict.py -q`
- Result: **129 passed, 5 subtests passed** (0:01:47).

## 3. Guarantees table

| # | What is guaranteed | Test file or command | Type | Result | Evidence |
|---|---|---|---|---|---|
| 1 | All 12 schools labeled exactly once, bold | `test_dashboard_full.py::ChartLabelTests::test_all_twelve_schools_labeled` | unit | PASS | §2 RED/GREEN |
| 2 | No two chart labels closer than 17px | `...::test_no_label_collisions` | unit | PASS | min gap asserted on clustered data |
| 3 | Labels bold + dark (not gray whispers) | `...::test_labels_are_bold_and_dark` | unit | PASS | class + CSS weight asserted |
| 4 | Every chart path carries `data-school` | `...::test_paths_carry_data_school` | unit | PASS | §2 |
| 5 | `_place_labels` enforces min gap | `...::test_place_labels_unit` | unit | RED | direct algorithm test |
| 6 | Displaced labels get leader lines | `...::test_displaced_labels_get_leader_lines` | unit | PASS | |
| 7 | District label present ("District avg") | `...::test_district_label_present` | unit | PASS | |
| 8 | 5 drill buttons wired to panel | `test_dashboard_full.py::DrillDownTests::test_cards_have_drill_buttons` | unit | PASS | §2 |
| 9 | Drill blob has 5 entries w/ schools | `...::test_drill_blob_has_five_entries` | unit | PASS | JSON parsed |
| 10 | Blob schools match table data-school | `...::test_drill_blob_schools_match_table_rows` | unit | PASS | per render |
| 11 | Chart + table are drill targets; JS present | `...::test_hero_chart_and_table_are_drill_targets` | unit | PASS | |
| 12 | Hero has real h2; strip has real h3 | `test_dashboard_full.py::HeaderTests` | unit | PASS | §2 |
| 13 | No heading-level skips | `...::test_heading_outline_has_no_skips` | unit | PASS | regex over page |
| 14 | Drill-down works in a real browser | CDP script `/tmp/cdp_drill.py` vs headless Chromium | manual | PASS | §2 output |
| 15 | No regressions anywhere in the demo | full pytest command above | unit | PASS | 129 passed, 5 subtests |

## 4. Coverage and known gaps

- `test_survival.py` cannot run in this environment (`lifelines` not installed) — identical on the clean tree; pre-existing, unrelated to this diff. Its TW-495 run passed separately.
- `test_predict.py` (11 tests) passes here because scikit-learn was installed during this task (was missing at task start).
- Visual verification: full-page and 390px-mobile screenshots reviewed in headless Chromium; one real bug found and fixed at screenshot stage (`.card-big small` wrap). Screenshots are point-in-time, not automated.
- Impeccable detector CLI could not run (no DNS for the bundle download in sandbox); manual 15-tell audit performed — no new tells (only functional dim/hl/flash, reduced-motion respected).
- Non-blocking nits from Rosa's review (accepted, not fixed in this diff): 4 new ruff style findings (PLR1730, RUF007×2, I001; repo had 1 pre-existing), the `"schools"` key in `window.KPI_DRILL` is unread by client JS, diff is 488 insertions (over the 400-line soft rule).

## 5. Plan-safety notes

- No untrusted plan content was acted on. All direction came from the TW-516 ticket brief (Justynn via Marcus).
- The drill blob is pre-escaped server-side (`html.escape` at blob build; rows escaped at all five block-build sites; `</`→`<\/` JSON guard); client `innerHTML` only inserts pre-escaped content — verified by Rosa's independent review.
- Synthetic-data banner and "Prepared by Twistor Holdings LLC" attribution intact; no student IDs; aggregate only.
