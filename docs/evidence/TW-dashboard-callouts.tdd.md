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

---

## 6. Addendum — redesign round (plain-language + card layout)

Justynn's direction, post-review: the dashboard "reads like an
engineer's notebook." Formulas were good to prove the work, but the
demo dashboard must be content-first — a non-technical administrator
gains value instantly. Commit `67db93e` ("Card layout: chart hero, KPI
cards with callouts, single vertical stream").

### What changed
- **Hero leads with the chart.** The trend-by-period chart is the
  centerpiece at the top of the page (`.chart-hero`); trend callouts
  ride with it in a "What changed" strip.
- **KPI cards house the metrics.** The five custom-metric blocks are now
  cards in an auto-fit grid (`.kpi-grid`). Each card carries: the
  plain-language metric name, the headline number, its routed metric
  callout, a severity color class, and the formula behind a
  `<details>` "How this is calculated" dropdown. Formulas are one
  click away, never front and center.
- **Callout routing.** Trend callouts (movement/flatline/threshold
  cross) go to the hero strip; metric callouts (early-warning, MF
  ratio, recovery, concentration) land inside their KPI card. Routing
  is enforced by tests in both directions.
- **Plain-language rewrite.** `_plain_kicker()` maps engine templates
  to human kickers ("weekends hit hardest", "improving", "early
  warning"). Technical terms (C-index, isotonic, Concordance index)
  live inside `<details>` dropdowns only — tested to never lead the
  page.
- **Severity color language.** `_sev_class()` maps callout
  severity/direction to `sev-high` / `sev-med` / `sev-good` /
  `sev-info` classes; good-news recoveries render green.
- **One vertical stream.** The page never scrolls sideways; wide tables
  sit in a `.table-scroll` region. Section order is now: hero chart →
  KPI cards → model overlays → school table → methodology.
- **Model overlays** stacked below the cards, plain-language summaries
  visible, technicals in dropdowns.

### Test changes
Render suite grew from 13 to **26 tests** (`test_dashboard_full.py`,
all green). Superseded: `test_callouts_are_bands_not_cards` (bands no
longer exist — cards are the design), `test_all_blocks_render_with_formula`
(formulas moved behind `<details>`), `test_callouts_render_named_school_and_number`
(absorbed into card/strip tests). `test_sections_present_in_order`
updated to the new section order. `test_formula_text_is_escaped`,
`test_logistic_overlay_shows_auc_and_tiers`,
`test_survival_overlay_labels_provenance`,
`test_no_student_ids_in_overlays`,
`test_synthetic_banner_and_attribution`,
`test_model_honest_framing`, `test_no_student_ids_leak`,
`test_trend_chart_present`, `test_mobile_viewport` unchanged.

### Guarantees — render, `test_dashboard_full.py` (26 tests)

**Callout routing + plain language — `CalloutTests` (7)**

| # | What is guaranteed | Test | Type | Result |
|---|---|---|---|---|
| 36 | Hero strip shows only trend callouts; metric callouts routed elsewhere | test_trend_strip_shows_trend_callouts_only | unit | PASS |
| 37 | No empty strip section when there are no trend callouts | test_trend_strip_empty_without_trend_callouts | unit | PASS |
| 38 | Engine templates map to plain-language kickers ("weekends hit hardest", "improving", "early warning") | test_plain_kicker_mapping | unit | PASS |
| 39 | Unknown templates fall back to engine text without breaking | test_plain_kicker_falls_back_to_engine_text | unit | PASS |
| 40 | Severity/direction map to the right color class (high→sev-high, good-news→sev-good) | test_severity_color_classes | unit | PASS |
| 41 | Callout dict carries severity + template and HTML-escapes school names | test_callout_dict_carries_sev_template_and_escapes | unit | PASS |
| 42 | Trend-strip items carry their severity class for color coding | test_trend_strip_item_has_severity_class | unit | PASS |

**KPI cards — `KpiCardTests` (5)**

| # | What is guaranteed | Test | Type | Result |
|---|---|---|---|---|
| 43 | Cards show name + number; formula behind a `<details>` "How this is calculated" dropdown | test_cards_render_with_number_formula_and_dropdown | unit | PASS |
| 44 | Each metric's callout renders inside its own card | test_card_claims_its_metric_callout | unit | PASS |
| 45 | Trend callouts never leak into cards (routing integrity) | test_trend_callouts_do_not_land_in_cards | unit | PASS |
| 46 | Card carries its severity color class | test_card_tag_carries_severity_color | unit | PASS |
| 47 | Formula text is HTML-escaped (no markup injection via dropdown) | test_formula_text_is_escaped | unit | PASS |

**Full-page render — `RenderFullTests` (11)**

| # | What is guaranteed | Test | Type | Result |
|---|---|---|---|---|
| 48 | Sections in the new order: hero chart → KPI cards → overlays → table → methodology | test_sections_present_in_order | unit | PASS |
| 49 | Jargon (C-index, isotonic, Concordance index) never leads the page; technicals only inside `<details>` | test_no_jargon_leads_the_page | unit | PASS |
| 50 | Chart hero renders before the KPI cards | test_hero_leads_with_chart | unit | PASS |
| 51 | Trend callouts render alongside the hero chart, ahead of the cards | test_trend_callouts_ride_with_hero_chart | unit | PASS |
| 52 | Metric callout lands in its card in the full render | test_metric_callout_lands_in_its_card | unit | PASS |
| 53 | Wide tables get a scroll region; the page itself never scrolls sideways | test_wide_table_has_scroll_region | unit | PASS |
| 54 | Synthetic banner + Twistor attribution present | test_synthetic_banner_and_attribution | unit | PASS |
| 55 | Honest framing: synthetic-trained, retrains on district data | test_model_honest_framing | unit | PASS |
| 56 | No student IDs anywhere in the page | test_no_student_ids_leak | unit | PASS |
| 57 | Trend chart section present | test_trend_chart_present | unit | PASS |
| 58 | Mobile viewport meta present | test_mobile_viewport | unit | PASS |

(`ModelOverlayTests`: rows 27–29 of the original guarantees table —
logistic AUC + tiers, survival provenance, no IDs in overlays — are
unchanged and still green; original row numbers 27–35 above retained.)

### Full-suite validation (redesign round, fresh run, this session)
97 passed + 5 subtests across `test_callouts`, `test_dashboard_full`,
`test_dashboard`, `test_metrics`, `test_attendance`, `test_importer`
(23.8s). `ruff check` + `ruff format --check` clean on the touched
files. `test_predict` (needs sklearn) and `test_survival` (needs
lifelines) cannot import in this sandbox — pre-existing environment
limitations, unrelated to this diff; both were green in their own
environments per TW-494/TW-495 evidence.

### Impeccable exception (kept on purpose)
The KPI card grid (`.kpi-grid`, auto-fit cards) trips the
"no identical card grids" tell. Kept on purpose: the card layout was
**explicitly directed by Justynn** (KPI callouts in cards, hero for
the main chart). These are not decorative cards — each carries a
distinct metric with its own number, routed callout, severity color,
and formula dropdown. The tell is about generic AI card-wall
aesthetics; this is the requested information architecture. File-scan
+ manual 15-tell audit is the supported path in this sandbox
(detector CLI unavailable — known DNS limitation).
