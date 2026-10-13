# Prepared by Twistor Holdings LLC

# TDD evidence: NKC dashboard callout engine + full render

## 1. Source
Ticket: NKC dashboard rebuild (Justynn, 2026-10-13). Build the larger
dashboard with callouts: dynamic insight engine, custom metrics, model
overlays. This report covers the review-fix round (Rosa: REQUEST_CHANGES)
on the already-built work.

Branch: `sofia/nkc-dashboard-callouts` on
Twistorhq/revops-analytics-portfolio, based on main at PR #5 merge
(TW-495). Worktree: `~/workspace/worktrees/nkc-callouts/`.

Files touched by this round: `07-education-demo/dashboard.py`,
`07-education-demo/callouts.py`, `07-education-demo/test_callouts.py`.
This report (blocker item) added at
`docs/evidence/TW-dashboard-callouts.tdd.md`.

## 2. Task report

**What was built (prior to this round).** `callouts.py`: a dynamic insight
engine. Seven detection rules over school×period attendance series plus
the five TW-493 custom metrics — movements (±2pts), threshold crosses
(falling below / climbing above the 90% warn rate), flatlines (3 periods
within 0.5pts), early-warning pace (>=50% on-pace chronic), MF ratio
(>=1.25), recovery (>=90% recovered), days-lost concentration (>=15%
district share). `detect_callouts()` runs every rule, dedupes to one
callout per school×metric (keeping the stronger weight), ranks by
severity then weight, caps at 6 total with max 2 per template so the
band surfaces distinct insight types. Templates are fixed; only numbers
fill in. `dashboard.py` gained `render_full()` (hero, callout bands,
custom-metric blocks with formulas, logistic + survival overlays, trend
chart, methodology) and `demo_full()` wiring import → publish → metrics
→ callout engine → render.

**This round (Rosa review fixes):**
1. `[major]` `__main__` called `demo()` — the OLD dashboard. One-line
   fix: calls `demo_full()`. Verified: running the module writes a
   41,184-byte page containing the callouts section, all five custom
   metrics, both model overlays, and the trend chart.
2. `[blocker]` This evidence report.
3. `[nit]` `_callouts_html` copy said "Three findings worth quoting"
   while the engine caps at 6 — number dropped from the copy.
4. `[nit]` `test_ignores_data_gaps` → `test_fires_across_data_gaps`
   (it verifies firing ACROSS gaps, not ignoring them).
5. `[nit]` One-line comment on the +0.5 weight boost in
   `detect_threshold_crosses`: crossing into warning territory outranks a
   plain movement of identical magnitude (detect_movements weights by
   |delta| alone) — the regime change is the stronger signal.

**RED/GREEN.** `test_callouts.py` (22 engine tests) and
`test_dashboard_full.py` (13 render tests) were written with the build;
all green. This round added no new tests (fixes were copy/naming/docs).

**Full-suite validation** (fresh run, this session): 84/84 PASS across
`test_callouts`, `test_dashboard_full`, `test_dashboard`,
`test_metrics`, `test_predict`, `test_attendance`, `test_importer`
(25.5s). `test_survival` (15 tests) cannot import here: `lifelines` is
not installed in this worktree's environment and `pip install` fails
(No space left on device). Pre-existing environment limitation —
unrelated to this diff (no survival file touched); TW-495 verified
75/75 green in its own environment.

## 3. Guarantees

### Engine — `test_callouts.py` (22 tests)

| # | What is guaranteed | Test | Type | Result |
|---|---|---|---|---|
| 1 | Fires on a big attendance drop (high severity) | test_fires_on_big_drop | unit | PASS |
| 2 | Fires on a rise (good-news callout, not only bad) | test_fires_on_rise | unit | PASS |
| 3 | Silent on sub-threshold movement (no noise) | test_silent_below_threshold | unit | PASS |
| 4 | Fires across data gaps (gapped schools still surfaced) | test_fires_across_data_gaps | unit | PASS |
| 5 | Fires when a school falls below the 90% warn rate | test_fires_falling_into_warning | unit | PASS |
| 6 | Fires when a school climbs back out of warning | test_fires_climbing_out | unit | PASS |
| 7 | Silent when always below (no fake "crossing") | test_silent_when_always_below | unit | PASS |
| 8 | Silent when always above | test_silent_when_always_above | unit | PASS |
| 9 | Fires on 3 flat periods ("no movement" is news) | test_fires_on_three_flat_periods | unit | PASS |
| 10 | Silent on flatline when values are moving | test_silent_when_moving | unit | PASS |
| 11 | Silent with too few periods for a flatline verdict | test_silent_with_too_few_periods | unit | PASS |
| 12 | Early-warning metric fires when >=50% on pace | test_early_warning_fires | unit | PASS |
| 13 | MF-ratio metric fires when >=1.25 | test_mf_ratio_fires | unit | PASS |
| 14 | Recovery metric fires good-news callouts | test_recovery_fires_good_news | unit | PASS |
| 15 | Days-lost concentration fires at >=15% share | test_concentration_fires | unit | PASS |
| 16 | Null metric outputs never produce callouts | test_nulls_never_fire | unit | PASS |
| 17 | high severity ranks before info; total capped | test_ranks_high_before_info_and_caps | unit | PASS |
| 18 | Max 2 per template — diverse insight types, not repeats | test_caps_per_template_for_diversity | unit | PASS |
| 19 | Deterministic output; ties break alphabetically | test_deterministic_tiebreak | unit | PASS |
| 20 | One callout per school×metric — stronger signal wins | test_dedupes_same_school_metric | unit | PASS |
| 21 | Empty list when nothing notable (no vanity callouts) | test_empty_when_nothing_notable | unit | PASS |
| 22 | Callout text is plain (no pre-escaped entities) | test_callout_objects_carry_plain_text | unit | PASS |

### Render — `test_dashboard_full.py` (13 tests)

| # | What is guaranteed | Test | Type | Result |
|---|---|---|---|---|
| 23 | Callouts render named school + number | test_callouts_render_named_school_and_number | unit | PASS |
| 24 | Callouts are full-width bands, not cards | test_callouts_are_bands_not_cards | unit | PASS |
| 25 | All 5 custom-metric blocks render with formula text | test_all_blocks_render_with_formula | unit | PASS |
| 26 | Formula text is HTML-escaped (no markup injection) | test_formula_text_is_escaped | unit | PASS |
| 27 | Logistic overlay shows AUC + risk tiers | test_logistic_overlay_shows_auc_and_tiers | unit | PASS |
| 28 | Survival overlay labels synthetic provenance | test_survival_overlay_labels_provenance | unit | PASS |
| 29 | No student IDs in model overlays | test_no_student_ids_in_overlays | unit | PASS |
| 30 | Sections present in editorial order | test_sections_present_in_order | unit | PASS |
| 31 | Synthetic banner + Twistor attribution present | test_synthetic_banner_and_attribution | unit | PASS |
| 32 | Honest framing: synthetic-trained, retrains on district data | test_model_honest_framing | unit | PASS |
| 33 | No student IDs anywhere in the page | test_no_student_ids_leak | unit | PASS |
| 34 | Trend chart section present | test_trend_chart_present | unit | PASS |
| 35 | Mobile viewport meta present | test_mobile_viewport | unit | PASS |

Additional: `python3 -m ruff check` + `ruff format --check` clean on all
three touched files. `python3 dashboard.py` end-to-end verified:
41,184-byte page, callouts/custom-metrics/overlays/trend all present.

## 4. Coverage and known gaps
- Engine edge cases (empty series, single period, null denominators)
  covered via the null-safety tests; per-school RNG not re-asserted here
  (TW-493 covers determinism).
- Threshold values (2pts movement, 90% warn rate, 6-callout cap) are
  product choices, not calibrated to real NKC data — labeled as
  configurable in `Thresholds`.
- No browser/screenshot test of the rendered bands (file-scan per the
  Impeccable sandbox path; manual 15-tell audit is the builder's lane).
- `test_survival` unverifiable in this environment (missing lifelines,
  no disk space to install) — pre-existing, documented above.

## 5. Plan-safety notes
- Synthetic data only; aggregate-only outputs; zero `synth-` IDs reach
  the page (tested twice: overlays + full page).
- Real school names are public district roster info (Justynn-requested).
- No embedded instructions or suspicious content encountered.
- Scope respected: FOSS/$0, stdlib only, no new dependencies.
- Prior-ticket behavior preserved: `demo()` still exists for the old
  dashboard; `__main__` now ships the full one.
