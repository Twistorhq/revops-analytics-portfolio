# Prepared by Twistor Holdings LLC
"""Custom attendance metrics for the NKC bid (TW-493).

Lesser-known, decision-driving metrics schools rarely compute — each with
one precise definition, implemented on the daily grain, aggregate-only
output. No student IDs ever leave this module.

Grain: one row per (student, instructional day). All metrics scope by
explicit district + allowed schools before aggregating.
"""

import csv
import io
from dataclasses import dataclass

CHRONIC_THRESHOLD = 0.10  # 10%+ absence = chronic absenteeism (US DOE standard)


@dataclass(frozen=True)
class DailyRecord:
    district: str
    school: str
    student: str
    date: str  # ISO
    period: str
    present: bool
    dow: int  # 0=Mon .. 6=Sun


def parse_daily_csv(text: str) -> list[DailyRecord]:
    """Parse the daily-grain CSV from importer.demo_district_daily_csv."""
    records = []
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    for row in reader:
        records.append(
            DailyRecord(
                district=row["District"].strip(),
                school=row["SchoolName"].strip(),
                student=row["StudentID"].strip(),
                date=row["Date"].strip(),
                period=row["Period"].strip(),
                present=row["Present"].strip() == "1",
                dow=int(row["DayOfWeek"]),
            )
        )
    return records


def _scope(records, district: str, allowed_schools: frozenset) -> list[DailyRecord]:
    if not district.strip() or not allowed_schools:
        raise ValueError("explicit district and school scope required")
    return [
        r for r in records if r.district == district and r.school in allowed_schools
    ]


def _by_student(records: list[DailyRecord]) -> dict:
    """(school, student) -> records sorted by date."""
    out: dict = {}
    for r in records:
        out.setdefault((r.school, r.student), []).append(r)
    for rows in out.values():
        rows.sort(key=lambda r: r.date)
    return out


def _pct(numer: int, denom: int):
    return numer / denom if denom else None


# ---------------------------------------------------------------------------
# 1. Chronic absenteeism early warning.
#
# Definition: pace_s = absent_s(W) / enrolled_s(W) over the first W
# instructional days of the term (W=30 default); on_pace_s = pace_s >= 0.10;
# metric = SUM(on_pace) / SUM(students), students = those enrolled for at
# least half the window. Null when no qualifying students.
#
# Why it matters: schools usually discover chronic absenteeism after the
# fact. This is the predictive version — who is ON PACE for chronic status
# while there is still time to intervene.
def chronic_early_warning(
    records: list[DailyRecord],
    *,
    district: str,
    allowed_schools: frozenset,
    window_days: int = 30,
) -> dict:
    scoped = _scope(records, district, allowed_schools)
    term_dates = sorted({r.date for r in scoped})[:window_days]
    window = {r for r in scoped if r.date in set(term_dates)}
    schools = []
    for school in sorted({r.school for r in window}):
        students = on_pace = 0
        for rows in _by_student([r for r in window if r.school == school]).values():
            enrolled = len(rows)
            if enrolled < window_days // 2:
                continue
            absent = sum(1 for r in rows if not r.present)
            students += 1
            if absent / enrolled >= CHRONIC_THRESHOLD:
                on_pace += 1
        schools.append(
            {
                "school": school,
                "students": students,
                "on_pace_chronic": on_pace,
                "pct": _pct(on_pace, students),
            }
        )
    return {
        "sample_data": True,
        "district": district,
        "window_days": window_days,
        "definition": (
            "pace = absent/enrolled over the first 30 instructional days; "
            "on pace = pace >= 10%; metric = on-pace students / qualifying students"
        ),
        "schools": schools,
    }


# ---------------------------------------------------------------------------
# 2. Monday/Friday ratio.
#
# Definition: r_MF = absent_MF / enrolled_MF (Mon+Fri days);
# r_mid = absent_mid / enrolled_mid (Tue+Wed+Thu days);
# metric = r_MF / r_mid. Null when the midweek denominator is zero.
#
# Why it matters: weekend-adjacent absences run hotter almost everywhere,
# but nobody quantifies it. A ratio of 1.4 means Mon/Fri absence runs 40%
# hotter than midweek — a scheduling and engagement signal, not a truancy
# lecture.
def monday_friday_ratio(
    records: list[DailyRecord], *, district: str, allowed_schools: frozenset
) -> dict:
    scoped = _scope(records, district, allowed_schools)
    schools = []
    for school in sorted({r.school for r in scoped}):
        rows = [r for r in scoped if r.school == school]
        mf = [r for r in rows if r.dow in (0, 4)]
        mid = [r for r in rows if r.dow in (1, 2, 3)]
        r_mf = _pct(sum(1 for r in mf if not r.present), len(mf))
        r_mid = _pct(sum(1 for r in mid if not r.present), len(mid))
        ratio = (r_mf / r_mid) if (r_mf is not None and r_mid) else None
        schools.append(
            {
                "school": school,
                "mf_absence_rate": r_mf,
                "midweek_absence_rate": r_mid,
                "mf_ratio": ratio,
            }
        )
    return {
        "sample_data": True,
        "district": district,
        "definition": (
            "r_MF = absent/enrolled on Mon+Fri; r_mid = absent/enrolled on "
            "Tue-Thu; metric = r_MF / r_mid (null when midweek is zero)"
        ),
        "schools": schools,
    }


# ---------------------------------------------------------------------------
# 3. Consecutive-absence streaks (3+ days).
#
# Definition: streak_s = longest run of consecutive absent instructional
# days for student s (consecutive in the instructional-day sequence —
# Friday followed by Monday counts as consecutive); flagged_s = streak_s
# >= 3; metric = SUM(flagged) / SUM(students). Null when no students.
#
# Why it matters: a single 3-day streak predicts disengagement better than
# the same 3 absences spread across a month. This is the intervention
# trigger most districts don't have.
def streak3_students(
    records: list[DailyRecord], *, district: str, allowed_schools: frozenset
) -> dict:
    scoped = _scope(records, district, allowed_schools)
    schools = []
    for school in sorted({r.school for r in scoped}):
        students = flagged = 0
        for rows in _by_student([r for r in scoped if r.school == school]).values():
            students += 1
            best = run = 0
            for r in rows:
                run = run + 1 if not r.present else 0
                best = max(best, run)
            if best >= 3:
                flagged += 1
        schools.append(
            {
                "school": school,
                "students": students,
                "students_with_streak3": flagged,
                "pct": _pct(flagged, students),
            }
        )
    return {
        "sample_data": True,
        "district": district,
        "definition": (
            "streak = longest run of consecutive absent instructional days; "
            "flagged = streak >= 3; metric = flagged students / all students"
        ),
        "schools": schools,
    }


# ---------------------------------------------------------------------------
# 4. Recovery rate.
#
# Definition: chronic_s(p) = absent_s(p)/enrolled_s(p) >= 0.10 in period p
# (needs >= 10 enrolled days in p to qualify); recovered_s =
# chronic_s(p1) AND NOT chronic_s(p2); metric =
# SUM(recovered) / SUM(chronic_p1). Null when no chronic students in p1.
#
# Why it matters: districts track who is absent; almost none track who
# came BACK. Recovery rate measures whether interventions work — the
# metric that justifies the attendance team's budget.
def recovery_rate(
    records: list[DailyRecord],
    *,
    district: str,
    allowed_schools: frozenset,
    p1: str = "2026-09",
    p2: str = "2026-10",
) -> dict:
    scoped = _scope(records, district, allowed_schools)
    schools = []
    for school in sorted({r.school for r in scoped}):
        chronic = recovered = 0
        for rows in _by_student([r for r in scoped if r.school == school]).values():
            r1 = [r for r in rows if r.period == p1]
            r2 = [r for r in rows if r.period == p2]
            if len(r1) < 10 or len(r2) < 10:
                continue
            c1 = sum(1 for r in r1 if not r.present) / len(r1) >= CHRONIC_THRESHOLD
            c2 = sum(1 for r in r2 if not r.present) / len(r2) >= CHRONIC_THRESHOLD
            if c1:
                chronic += 1
                if not c2:
                    recovered += 1
        schools.append(
            {
                "school": school,
                "chronic_p1": chronic,
                "recovered_p2": recovered,
                "pct": _pct(recovered, chronic),
            }
        )
    return {
        "sample_data": True,
        "district": district,
        "periods": [p1, p2],
        "definition": (
            "chronic(p) = absent/enrolled >= 10% in period p; "
            "recovered = chronic(p1) and not chronic(p2); "
            "metric = recovered / chronic(p1)"
        ),
        "schools": schools,
    }


# ---------------------------------------------------------------------------
# 5. Instructional days lost.
#
# Definition: days_lost = SUM over students and days of (1 - present).
# Aggregate count, per school and district-wide.
#
# Why it matters: Missouri funds districts on attendance — every lost day
# is a day of attendance-based funding not earned. This turns an abstract
# rate into the number the CFO feels.
def instructional_days_lost(
    records: list[DailyRecord], *, district: str, allowed_schools: frozenset
) -> dict:
    scoped = _scope(records, district, allowed_schools)
    schools = []
    total = 0
    for school in sorted({r.school for r in scoped}):
        lost = sum(1 for r in scoped if r.school == school and not r.present)
        total += lost
        schools.append({"school": school, "days_lost": lost})
    return {
        "sample_data": True,
        "district": district,
        "district_days_lost": total,
        "definition": (
            "days_lost = SUM(1 - present) over all student-days; "
            "each lost day is a day of attendance-based funding not earned"
        ),
        "schools": schools,
    }
