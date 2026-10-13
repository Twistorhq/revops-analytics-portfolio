# Prepared by Twistor Holdings LLC

# TW-486 TDD evidence: NKC import workflow + dashboard slice

## 1. Source

- Ticket: TW-486 — NKC (North Kansas City Schools) build: import workflow +
  dashboard slice. Proposal due Fri Oct 16, 2026 1pm Denver; internal cutoff
  Thu Oct 15.
- Branch: `feat/education-analytics-slice-20261012` on
  Twistorhq/revops-analytics-portfolio (tip at time of writing:
  `e5e676b` "TW-486: address Rosa round 1").
- Files: `07-education-demo/importer.py`, `07-education-demo/dashboard.py`,
  `07-education-demo/attendance.py` (pre-existing), `test_importer.py`,
  `test_dashboard.py`, `test_attendance.py`, README metric definitions.
- Authorship note: this report was written by the TW-486 engineer after
  re-running every test fresh and re-reading every file on the branch tip,
  at Rosa's request. RED-stage checkpoint commits do not exist in the
  branch history (both work commits are single "done" commits); RED is
  demonstrated behaviorally below, not from a checkpoint commit.

## 2. Task report (per behavior)

Validation command (run fresh on the branch tip, `07-education-demo/`):

```
python3 -m pytest test_attendance.py test_importer.py test_dashboard.py -v
→ 28 passed, 5 subtests passed in 0.10s
```

### Importer — explicit column mapping
`import_csv` requires every `REQUIRED_FIELDS` entry in `column_map`, every
mapped header present in the CSV header row, and injectivity (no two
canonical fields reading the same CSV header). Violations raise `ValueError`
before any row is read. Covered by `test_mapping_missing_field_fails_fast`,
`test_mapped_header_absent_fails_fast`, `test_non_injective_mapping_fails_fast`,
`test_non_injective_mapping_names_the_header` — all PASS.

### Importer — rejected-row diagnostics
Bad rows become `Rejection` records (1-based row number, stable reason code,
human detail, raw row) instead of exceptions. Reason codes:
`missing_identifier`, `bad_count`, `invalid_counts`, `duplicate_grain`.
Covered by `test_rejected_rows_diagnosed` — PASS. Fresh behavioral receipt
(run this turn, not in history):

```
dirty CSV (present> enrolled, missing student, non-integer count)
→ rejected = 3, reasons = {'invalid_counts': 1, 'missing_identifier': 1, 'bad_count': 1}
```

This is the observable RED: without the rejection logic these rows would
raise or corrupt the mart; with it they are quarantined with codes.

### Importer — reconciled totals
`ImportResult.reconciled` asserts `source_rows == accepted + rejected`.
`report()` exposes the full reconciliation. Covered by
`test_clean_import_reconciles`, `test_empty_csv_reconciles`,
`test_demo_csv_end_to_end` (300/300 accepted, reconciled) — all PASS.
Fresh receipt: demo CSV 300 source rows → 300 accepted, 0 rejected,
reconciled True.

### Importer — publish block
`publish()` raises `ValueError` when totals don't reconcile or any row is
rejected. Covered by `test_publish_blocked_on_rejections` and
`test_publish_clean_import` — PASS. Fresh receipt: the 3-rejection dirty
import above → publish BLOCKED with "import has 3 rejected row(s); resolve
diagnostics before publishing".

### Dashboard — aggregates and filters
`dashboard.py` renders self-contained HTML (stdlib only, no external
assets): headline cards (weighted attendance rate, enrolled/present days,
school+period counts), school/period dropdown filters with `data-school` /
`data-period` row attributes, 12 metric rows (4 schools × 3 periods).
Headline rate is weighted `Σpresent/Σenrolled`, never an average of rates.
Covered by `test_headline_rate_is_weighted`,
`test_filters_cover_all_schools_and_periods`,
`test_twelve_metric_rows_with_filter_attributes`,
`test_district_scope_shown`, `test_empty_scope_renders` — all PASS.

### Dashboard — no PII, synthetic labeled
`test_no_student_ids_leak` asserts no `synth-*` identifiers reach the page;
`test_synthetic_label_present` asserts the "SYNTHETIC SAMPLE DATA" banner.
Both PASS. All student IDs in fixtures are synthetic (`synth-no-001`,
`fictional-N`).

### Attendance mart (pre-existing, 8 tests)
`test_attendance.py` (8 tests): weighted-rate-not-average, scope-before-
aggregation, duplicate rejection, bad-count rejection, zero/empty handling,
deterministic source hash, no-scope refused, demo-no-identifiers — all PASS.

## 3. Guarantees table

| # | What is guaranteed | Test file or command | Type | Result | Evidence |
|---|---|---|---|---|---|
| 1 | Column mapping missing a required field fails fast | test_importer.py::test_mapping_missing_field_fails_fast | unit | PASS | pytest 28/28 green |
| 2 | Mapped header absent from CSV fails fast | test_importer.py::test_mapped_header_absent_fails_fast | unit | PASS | pytest 28/28 green |
| 3 | Non-injective mapping fails fast and names the duplicated header | test_importer.py::test_non_injective_mapping_fails_fast, test_non_injective_mapping_names_the_header | unit | PASS | pytest 28/28 green |
| 4 | Bad rows become Rejections with stable reason codes, never exceptions | test_importer.py::test_rejected_rows_diagnosed | unit | PASS | pytest + fresh dirty-CSV probe (3 rejections, 3 codes) |
| 5 | UTF-8 BOM stripped at CSV entry | test_importer.py::test_utf8_bom_stripped | unit | PASS | pytest 28/28 green |
| 6 | source_rows == accepted + rejected on clean, empty, and demo imports | test_importer.py::test_clean_import_reconciles, test_empty_csv_reconciles, test_demo_csv_end_to_end | unit | PASS | pytest + fresh receipt (300/300) |
| 7 | Extra CSV columns tolerated, required fields constant checked | test_importer.py::test_extra_columns_tolerated, test_required_fields_constant | unit | PASS | pytest 28/28 green |
| 8 | publish() blocks on rejections or unreconciled totals; clean imports publish | test_importer.py::test_publish_blocked_on_rejections, test_publish_clean_import | unit | PASS | pytest + fresh blocked-publish probe |
| 9 | Headline attendance rate is weighted Σpresent/Σenrolled, null on zero denominator | test_dashboard.py::test_headline_rate_is_weighted, test_attendance.py::test_weighted_rate_not_average, test_zero_and_empty | unit | PASS | pytest 28/28 green |
| 10 | Filters cover all schools/periods; 12 metric rows carry data-school/data-period | test_dashboard.py::test_filters_cover_all_schools_and_periods, test_twelve_metric_rows_with_filter_attributes | unit | PASS | pytest 28/28 green |
| 11 | No student identifiers reach the dashboard; synthetic banner present | test_dashboard.py::test_no_student_ids_leak, test_synthetic_label_present | unit | PASS | pytest 28/28 green |
| 12 | Aggregation is scoped by district + allowed schools before summarizing; duplicates and bad counts rejected | test_attendance.py (all 8) | unit | PASS | pytest 28/28 green |
| 13 | Source selection hash is deterministic across runs | test_attendance.py::test_deterministic_source_hash | unit | PASS | pytest 28/28 green |

Command: `python3 -m pytest test_attendance.py test_importer.py test_dashboard.py -v`
Outcome: `28 passed, 5 subtests passed in 0.10s` (run fresh on branch tip
`e5e676b` for this report).

## 4. Coverage and known gaps

Honest gaps — none of these are covered by tests:

1. **Dashboard filter JS is not browser-tested.** Tests assert the
   `data-school`/`data-period` attributes and `<select>` options exist in
   the HTML string; the `applyFilters()` JavaScript has never run in a real
   browser. A Playwright smoke test would close this.
2. **No RED checkpoint commits.** The branch history has no failing-test
   commit stages; RED is demonstrated only behaviorally (dirty-input probes
   above). If the branch is squash-merged, this report carries the proof.
3. **No real-file ingestion test.** All CSV inputs are in-memory strings via
   `demo_csv()` or inline text. The `__main__` path writing
   `attendance-dashboard.html` is exercised only manually (and is
   git-ignored per Rosa round 1).
4. **Duplicate CSV header names** in the source file (DictReader collision
   behavior) are untested; the injectivity check covers the *mapping*, not
   the *file*.
5. **No concurrency test.** `import_csv` is single-threaded by design; the
   `seen` set is per-call, so there is no shared-state risk, but no test
   asserts that.
6. **Extremely large integers** in count columns are untested (`_parse_count`
   accepts any non-negative int).
7. **Accessibility** of the dashboard HTML (contrast, labels, keyboard nav)
   is untested.

## 5. Plan-safety notes

- No embedded instructions, override phrases, or suspicious content found in
  any file on the branch (importer.py, dashboard.py, attendance.py, tests,
  README). No network calls, subprocesses, or file writes outside the demo
  `__main__` HTML writer.
- The two Rosa round-1 fixes (injectivity check naming dupes, B023 explicit
  binding, typed `RowRejection` replacing message substring-sniffing, BOM
  strip) are sound and covered by new tests; reviewed in the diff.
- Scope boundary respected: synthetic data only, stdlib only, $0 spend, no
  real student records, no invented client references anywhere in the code.
