"""Synthetic attendance mart. Trusted scope must come from an auth adapter, not UI input."""

from dataclasses import asdict, dataclass
import hashlib
import json


@dataclass(frozen=True)
class Attendance:
    district: str
    school: str
    student: str
    period: str
    enrolled_days: int
    present_days: int


def summarize(rows: list[Attendance], *, district: str,
              allowed_schools: frozenset[str]) -> dict:
    """Validate before publishing; scope before aggregation; never average percentages."""
    if not district.strip() or not allowed_schools:
        raise ValueError("explicit district and school scope required")
    selected = [r for r in rows if r.district == district and r.school in allowed_schools]
    seen = set()
    totals = {}
    for row in selected:
        if not all((row.district.strip(), row.school.strip(), row.student.strip(),
                    row.period.strip())):
            raise ValueError("missing identifier")
        key = (row.district, row.school, row.student, row.period)
        if key in seen:
            raise ValueError("duplicate attendance grain")
        seen.add(key)
        if (type(row.enrolled_days) is not int or type(row.present_days) is not int or
                not 0 <= row.present_days <= row.enrolled_days):
            raise ValueError("invalid attendance counts")
        bucket = totals.setdefault((row.school, row.period), [0, 0, 0])
        bucket[0] += row.enrolled_days
        bucket[1] += row.present_days
        bucket[2] += 1
    metrics = [
        {"school": school, "period": period, "enrolled_days": days,
         "present_days": present, "student_period_records": count,
         "attendance_rate": present / days if days else None}
        for (school, period), (days, present, count) in sorted(totals.items())
    ]
    canonical = json.dumps(
        [asdict(r) for r in sorted(selected, key=lambda r: (
            r.district, r.school, r.student, r.period))],
        sort_keys=True, separators=(",", ":"))
    return {"sample_data": True, "district": district, "metrics": metrics,
            "selected_records": len(selected),
            "selected_source_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            "definition": "present days / enrolled days; zero denominator is null"}


def demo() -> dict:
    rows = [
        Attendance("DEMO", "North", "fictional-1", "2026-09", 20, 18),
        Attendance("DEMO", "North", "fictional-2", "2026-09", 10, 10),
        Attendance("DEMO", "South", "fictional-3", "2026-09", 20, 19),
        Attendance("OTHER", "North", "fictional-4", "2026-09", 20, 1),
    ]
    return summarize(rows, district="DEMO", allowed_schools=frozenset({"North", "South"}))


if __name__ == "__main__":
    print(json.dumps(demo(), indent=2, sort_keys=True))
