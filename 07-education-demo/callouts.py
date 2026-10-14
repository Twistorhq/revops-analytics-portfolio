# Prepared by Twistor Holdings LLC
"""Dynamic insight engine for the NKC dashboard.

Callouts are DYNAMIC, not static: the frame/template is fixed, only the
numbers change, driven by change detection over the data. Every callout
answers "why is this on screen" — something CHANGED or something NEEDS
attention. No vanity callouts.

Rules (all thresholds configurable):
  - movement:        |period-over-period delta| >= move_pts
  - threshold_cross: crossing into/out of chronic-warning territory
  - flat:            flat_periods consecutive periods with |delta| < flat_eps
  - early_warning:   on-pace chronic share >= early_warning_pct
  - mf_ratio:        Monday/Friday absence ratio >= mf_ratio
  - recovery:        recovery rate >= recovery_pct (good news)
  - concentration:   one school's share of district days-lost >= share

Direction-aware: up / down / flat each get their tone, but the template
structure never changes — only values and direction words.
"""

from dataclasses import dataclass
from itertools import pairwise


@dataclass(frozen=True)
class Thresholds:
    move_pts: float = 2.0
    big_move_pts: float = 4.0
    flat_eps_pts: float = 0.5
    flat_periods: int = 3
    warn_rate: float = 0.90
    early_warning_pct: float = 0.50
    mf_ratio: float = 1.25
    recovery_pct: float = 0.90
    days_lost_share: float = 0.15
    max_callouts: int = 6
    max_per_template: int = 2  # diversity: the band should surface distinct
    # insight types, not N variations of one story


@dataclass(frozen=True)
class Callout:
    template_id: str  # movement | threshold_cross | flat | early_warning
    # | mf_ratio | recovery | concentration
    school: str | None  # None = district-wide
    metric: str  # machine key, e.g. 'attendance_rate'
    metric_label: str  # human label, e.g. 'attendance rate'
    direction: str  # up | down | flat
    delta_pts: float | None
    value: float | None
    severity: str  # high | medium | info
    weight: float  # ranking magnitude within a severity band
    kicker: str  # plain text; dashboard escapes on render
    big: str
    line: str


_SEV_RANK = {"high": 0, "medium": 1, "info": 2}


def _pop(series, school, periods):
    """Latest two non-null (period, rate) pairs, newest last."""
    vals = [(p, series[school].get(p)) for p in periods]
    vals = [(p, r) for p, r in vals if r is not None]
    return vals[-2:] if len(vals) >= 2 else []


def detect_movements(series, periods, t: Thresholds):
    out = []
    for school in sorted(series):
        vals = _pop(series, school, periods)
        if len(vals) < 2:
            continue
        (p_prev, r_prev), (_, r_cur) = vals
        delta = (r_cur - r_prev) * 100
        if abs(delta) < t.move_pts:
            continue
        direction = "up" if delta > 0 else "down"
        if direction == "down":
            severity = "high" if abs(delta) >= t.big_move_pts else "medium"
            line = (
                f"{school}'s attendance rate slipped {abs(delta):.1f} points "
                f"vs {p_prev} — worth a look before it compounds."
            )
        else:
            severity = "medium"
            line = (
                f"{school}'s attendance rate climbed {delta:.1f} points "
                f"vs {p_prev} — what's working here?"
            )
        out.append(
            Callout(
                template_id="movement",
                school=school,
                metric="attendance_rate",
                metric_label="attendance rate",
                direction=direction,
                delta_pts=round(delta, 2),
                value=r_cur,
                severity=severity,
                weight=round(abs(delta), 2),
                kicker=f"{school} — attendance {direction}",
                big=f"{delta:+.1f} pts",
                line=line,
            )
        )
    return out


def detect_threshold_crosses(series, periods, t: Thresholds):
    out = []
    for school in sorted(series):
        vals = _pop(series, school, periods)
        if len(vals) < 2:
            continue
        (_, r_prev), (_, r_cur) = vals
        was_below = r_prev < t.warn_rate
        is_below = r_cur < t.warn_rate
        if was_below == is_below:
            continue
        if is_below:
            # +0.5 boost: crossing into warning territory outranks a plain
            # movement of identical magnitude (detect_movements weights by
            # |delta| alone) — the regime change is the stronger signal.
            out.append(
                Callout(
                    template_id="threshold_cross",
                    school=school,
                    metric="attendance_rate",
                    metric_label="attendance rate",
                    direction="down",
                    delta_pts=round((r_cur - r_prev) * 100, 2),
                    value=r_cur,
                    severity="high",
                    weight=round(abs((r_cur - r_prev) * 100) + 0.5, 2),
                    kicker=f"{school} — warning territory",
                    big=f"{r_cur * 100:.1f}%",
                    line=(
                        f"{school} fell below {t.warn_rate * 100:.0f}% "
                        f"attendance — chronic-warning territory."
                    ),
                )
            )
        else:
            out.append(
                Callout(
                    template_id="threshold_cross",
                    school=school,
                    metric="attendance_rate",
                    metric_label="attendance rate",
                    direction="up",
                    delta_pts=round((r_cur - r_prev) * 100, 2),
                    value=r_cur,
                    severity="info",
                    weight=round(abs((r_cur - r_prev) * 100) + 0.5, 2),
                    kicker=f"{school} — out of warning",
                    big=f"{r_cur * 100:.1f}%",
                    line=(
                        f"{school} climbed back above "
                        f"{t.warn_rate * 100:.0f}% attendance."
                    ),
                )
            )
    return out


def detect_flatlines(series, periods, t: Thresholds):
    out = []
    for school in sorted(series):
        vals = [(p, series[school].get(p)) for p in periods]
        vals = [(p, r) for p, r in vals if r is not None]
        if len(vals) < t.flat_periods:
            continue
        tail = vals[-t.flat_periods :]
        deltas = [abs(b - a) * 100 for (_, a), (_, b) in pairwise(tail)]
        if any(d >= t.flat_eps_pts for d in deltas):
            continue
        r_cur = tail[-1][1]
        out.append(
            Callout(
                template_id="flat",
                school=school,
                metric="attendance_rate",
                metric_label="attendance rate",
                direction="flat",
                delta_pts=0.0,
                value=r_cur,
                severity="info",
                weight=0.0,
                kicker=f"{school} — holding steady",
                big=f"{r_cur * 100:.1f}%",
                line=(
                    f"No meaningful movement in {t.flat_periods} periods — "
                    f"stability, or stagnation?"
                ),
            )
        )
    return out


def detect_early_warnings(cew_schools, t: Thresholds):
    out = []
    for s in cew_schools:
        pct = s.get("pct")
        if pct is None or pct < t.early_warning_pct:
            continue
        n = s["on_pace_chronic"]
        students = s["students"]
        in_ten = round(pct * 10)
        out.append(
            Callout(
                template_id="early_warning",
                school=s["school"],
                metric="early_warning",
                metric_label="chronic early-warning pace",
                direction="down",
                delta_pts=None,
                value=pct,
                severity="high",
                weight=round(pct * 100, 2),
                kicker=f"{s['school']} — early warning",
                big=f"{pct * 100:.1f}%",
                line=(
                    f"{in_ten} in 10 students on pace for chronic absenteeism "
                    f"after 30 days ({n:,}/{students:,}) — intervene now."
                ),
            )
        )
    return out


def detect_mf_ratios(mfr_schools, t: Thresholds):
    out = []
    for s in mfr_schools:
        ratio = s.get("mf_ratio")
        if ratio is None or ratio < t.mf_ratio:
            continue
        hotter = (ratio - 1) * 100
        out.append(
            Callout(
                template_id="mf_ratio",
                school=s["school"],
                metric="mf_ratio",
                metric_label="Monday/Friday absence ratio",
                direction="up",
                delta_pts=None,
                value=ratio,
                severity="medium",
                weight=round((ratio - 1) * 100, 2),
                kicker=f"{s['school']} — weekend edge",
                big=f"{ratio:.2f}\u00d7",
                line=(
                    f"Mon/Fri absences run {hotter:.0f}% hotter than midweek "
                    f"({s['mf_absence_rate'] * 100:.1f}% vs "
                    f"{s['midweek_absence_rate'] * 100:.1f}%) — a scheduling "
                    f"signal, not a truancy lecture."
                ),
            )
        )
    return out


def detect_recoveries(rec_schools, t: Thresholds):
    out = []
    for s in rec_schools:
        pct = s.get("pct")
        if pct is None or pct < t.recovery_pct:
            continue
        out.append(
            Callout(
                template_id="recovery",
                school=s["school"],
                metric="recovery",
                metric_label="recovery rate",
                direction="up",
                delta_pts=None,
                value=pct,
                severity="info",
                weight=round(pct * 100, 2),
                kicker=f"{s['school']} — interventions working",
                big=f"{pct * 100:.1f}%",
                line=(
                    f"{s['recovered_p2']:,}/{s['chronic_p1']:,} chronic "
                    f"students back under 10% — interventions working."
                ),
            )
        )
    return out


def detect_days_lost_concentration(idl, t: Thresholds):
    out = []
    total = idl.get("district_days_lost") or 0
    if not total:
        return out
    for s in idl.get("schools", []):
        share = s["days_lost"] / total
        if share < t.days_lost_share:
            continue
        out.append(
            Callout(
                template_id="concentration",
                school=s["school"],
                metric="days_lost",
                metric_label="instructional days lost",
                direction="down",
                delta_pts=None,
                value=s["days_lost"],
                severity="medium",
                weight=round(share * 100, 2),
                kicker=f"{s['school']} — days lost",
                big=f"{s['days_lost']:,}",
                line=(
                    f"{share * 100:.0f}% of the district's {total:,} lost "
                    f"instructional days come from one school — "
                    f"attendance funding not earned."
                ),
            )
        )
    return out


def detect_callouts(
    school_series,
    periods,
    *,
    cew_schools=(),
    mfr_schools=(),
    rec_schools=(),
    idl=None,
    thresholds=None,
):
    """Run every rule, rank by severity then magnitude, cap the count.

    Deterministic: ties break on (template_id, school).
    """
    t = thresholds or Thresholds()
    found = []
    found += detect_movements(school_series, periods, t)
    found += detect_threshold_crosses(school_series, periods, t)
    found += detect_flatlines(school_series, periods, t)
    found += detect_early_warnings(cew_schools, t)
    found += detect_mf_ratios(mfr_schools, t)
    found += detect_recoveries(rec_schools, t)
    found += detect_days_lost_concentration(idl or {}, t)

    # One callout per school per metric — a drop and a threshold cross on
    # the same school tell one story; keep the stronger signal.
    best = {}
    for c in found:
        key = (c.school, c.metric)
        if key not in best or (c.weight, c.template_id) > (
            best[key].weight,
            best[key].template_id,
        ):
            best[key] = c

    def rank(c):
        return (_SEV_RANK[c.severity], -c.weight, c.template_id, c.school or "")

    ranked = sorted(best.values(), key=rank)
    selected = []
    per_template = {}
    for c in ranked:
        if per_template.get(c.template_id, 0) >= t.max_per_template:
            continue
        selected.append(c)
        per_template[c.template_id] = per_template.get(c.template_id, 0) + 1
        if len(selected) >= t.max_callouts:
            break
    return selected
