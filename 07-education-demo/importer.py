"""Synthetic attendance CSV import. Explicit column mapping, rejected-row
diagnostics, and reconciled totals. Stdlib only. Synthetic data only —
no real student records, ever.
"""

import csv
import hashlib
import io
import random
from dataclasses import dataclass

from attendance import Attendance, summarize

REQUIRED_FIELDS = (
    "district",
    "school",
    "student",
    "period",
    "enrolled_days",
    "present_days",
)


@dataclass(frozen=True)
class Rejection:
    """One source row that could not become an Attendance record."""

    row_number: int  # 1-based data-row number (header excluded)
    reason: str  # stable code: missing_identifier | bad_count |
    # invalid_counts | duplicate_grain
    detail: str  # human-readable explanation
    raw: dict  # the raw CSV row as read


@dataclass(frozen=True)
class ImportResult:
    accepted: list  # list[Attendance]
    rejected: list  # list[Rejection]
    source_rows: int
    mapping: dict  # canonical field -> CSV header actually used

    @property
    def accepted_rows(self) -> int:
        return len(self.accepted)

    @property
    def rejected_rows(self) -> int:
        return len(self.rejected)

    @property
    def reconciled(self) -> bool:
        """Every source row is accounted for: accepted + rejected == source."""
        return self.source_rows == self.accepted_rows + self.rejected_rows

    def rejections_by_reason(self) -> dict:
        counts: dict = {}
        for r in self.rejected:
            counts[r.reason] = counts.get(r.reason, 0) + 1
        return counts

    def report(self) -> dict:
        return {
            "sample_data": True,
            "source_rows": self.source_rows,
            "accepted_rows": self.accepted_rows,
            "rejected_rows": self.rejected_rows,
            "reconciled": self.reconciled,
            "rejections_by_reason": self.rejections_by_reason(),
            "column_mapping": dict(self.mapping),
        }


class RowRejection(ValueError):
    """A row-level import problem. Carries a stable reason code so the
    handler never has to substring-sniff the message."""

    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason


def _parse_count(value: str, field: str, row_number: int) -> int:
    text = (value or "").strip()
    try:
        number = int(text)
    except (TypeError, ValueError):
        raise ValueError(f"row {row_number}: {field}={text!r} is not an integer")
    if number < 0:
        raise ValueError(f"row {row_number}: {field}={number} is negative")
    return number


def import_csv(text: str, column_map: dict) -> ImportResult:
    """Import attendance rows from CSV text.

    column_map: canonical field name -> CSV header name. Every
    REQUIRED_FIELDS entry must be present, and every mapped header must
    exist in the CSV header row — mapping problems fail fast with
    ValueError. Row-level problems become Rejections, never exceptions.
    """
    missing = [f for f in REQUIRED_FIELDS if f not in column_map]
    if missing:
        raise ValueError(f"column mapping missing fields: {missing}")

    # The mapping must be injective: two canonical fields reading the same
    # CSV header would silently merge columns and corrupt aggregates.
    mapped_headers = list(column_map.values())
    dupes = sorted({h for h in mapped_headers if mapped_headers.count(h) > 1})
    if dupes:
        raise ValueError(
            f"column mapping is not injective — headers mapped twice: {dupes}"
        )

    text = text.lstrip("\ufeff")  # strip a UTF-8 BOM if the export added one
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    absent = [h for h in column_map.values() if h not in headers]
    if absent:
        raise ValueError(f"mapped headers not found in CSV: {absent}")

    accepted: list[Attendance] = []
    rejected: list[Rejection] = []
    seen: set = set()
    source_rows = 0

    for record in reader:
        source_rows += 1
        row_number = reader.line_num - 1  # 1-based, header excluded
        raw = {k: (v or "") for k, v in record.items() if k is not None}

        def field(name: str, _raw=raw) -> str:  # B023: bind raw explicitly
            return (_raw.get(column_map[name], "") or "").strip()

        try:
            district = field("district")
            school = field("school")
            student = field("student")
            period = field("period")
            if not all((district, school, student, period)):
                raise RowRejection(
                    "missing_identifier",
                    f"row {row_number}: missing identifier "
                    f"(district={district!r} school={school!r} "
                    f"student={student!r} period={period!r})",
                )
            enrolled = _parse_count(
                raw.get(column_map["enrolled_days"], ""), "enrolled_days", row_number
            )
            present = _parse_count(
                raw.get(column_map["present_days"], ""), "present_days", row_number
            )
            if present > enrolled:
                raise RowRejection(
                    "invalid_counts",
                    f"row {row_number}: present_days={present} "
                    f"exceeds enrolled_days={enrolled}",
                )
            key = (district, school, student, period)
            if key in seen:
                raise RowRejection(
                    "duplicate_grain",
                    f"row {row_number}: duplicate attendance grain {key}",
                )
            seen.add(key)
            accepted.append(
                Attendance(district, school, student, period, enrolled, present)
            )
        except RowRejection as exc:
            rejected.append(Rejection(row_number, exc.reason, str(exc), raw))
        except ValueError as exc:
            # _parse_count failures: not an integer, or negative.
            rejected.append(Rejection(row_number, "bad_count", str(exc), raw))

    return ImportResult(accepted, rejected, source_rows, dict(column_map))


def publish(result: ImportResult, *, district: str, allowed_schools: frozenset) -> dict:
    """Publish an import to the attendance mart.

    Blocks publication while any row is rejected — diagnostics must be
    resolved first. Returns attendance.summarize() output.
    """
    if not result.reconciled:
        raise ValueError(
            "import totals do not reconcile: "
            f"{result.source_rows} source vs "
            f"{result.accepted_rows} accepted + "
            f"{result.rejected_rows} rejected"
        )
    if result.rejected:
        raise ValueError(
            f"import has {result.rejected_rows} rejected row(s); resolve "
            f"diagnostics before publishing: "
            f"{result.rejections_by_reason()}"
        )
    return summarize(
        result.accepted, district=district, allowed_schools=allowed_schools
    )


def demo_csv(
    schools=("North", "South", "East", "West"),
    periods=("2026-09", "2026-10", "2026-11"),
    students_per_school=25,
    seed=20261013,
) -> str:
    """Deterministic synthetic attendance CSV. Fictional students only."""
    rng = random.Random(seed)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ["District", "SchoolName", "StudentID", "Period", "EnrolledDays", "PresentDays"]
    )
    for school in schools:
        for n in range(1, students_per_school + 1):
            student = f"synth-{school[:2].lower()}-{n:03d}"
            for period in periods:
                enrolled = 20
                absent = rng.randint(0, 4)
                writer.writerow(
                    ["DEMO", school, student, period, enrolled, enrolled - absent]
                )
    return out.getvalue()


def demo_mapping() -> dict:
    """The explicit column mapping used by the demo."""
    return {
        "district": "District",
        "school": "SchoolName",
        "student": "StudentID",
        "period": "Period",
        "enrolled_days": "EnrolledDays",
        "present_days": "PresentDays",
    }


def demo() -> dict:
    result = import_csv(demo_csv(), demo_mapping())
    published = publish(
        result,
        district="DEMO",
        allowed_schools=frozenset({"North", "South", "East", "West"}),
    )
    return {"import": result.report(), "published": published}


# ---------------------------------------------------------------------------
# TW-490: richer synthetic district. TW-492: each school gets its own
# trajectory — per-period absence-probability deltas ("trend") on top of the
# base rate, so the chart shows real variation instead of parallel lines:
# a steady top school, a climbing turnaround, a declining school, a
# volatile school, a worsening struggler, a data gap, a flu-hit high
# school, and a tiny noisy alternative school. All patterns a real
# district actually has. Strictly additive — demo_csv()/demo_mapping()
# above are untouched.

# (period, instructional days)
DISTRICT_PERIODS = (("2026-09", 20), ("2026-10", 21), ("2026-11", 15))

# (school name, enrollment, base daily absence probability, options)
# options["trend"]: per-period absence-probability deltas (sep, oct, nov)
#   applied on top of the base rate — this is what gives each school its
#   own trajectory. The shared NOVEMBER_DIP still applies in 2026-11.
DISTRICT_SCHOOLS = (
    # Steady: near-perfect, holds its level through flu season.
    ("Brookfield Elementary", 420, 0.015, {"trend": (0.0, -0.002, -0.010)}),
    # Climbing: turnaround story — intervention working, rate rising.
    ("Cedar Ridge Elementary", 380, 0.100, {"trend": (-0.015, -0.035, -0.055)}),
    # Declining: slipping month over month.
    ("Maple Grove Elementary", 350, 0.070, {"trend": (0.0, +0.015, +0.035)}),
    # Volatile: big swings — strong October, rough September and November.
    ("Riverside Elementary", 310, 0.060, {"trend": (+0.030, -0.030, +0.030)}),
    # Worsening: struggling school with a chronic-absence cluster,
    # drifting further down.
    (
        "Harlow Middle",
        520,
        0.115,
        {
            "trend": (+0.005, +0.015, +0.030),
            "chronic_share": 0.08,
            "chronic_rate": 0.35,
        },
    ),
    # Data gap: nothing reported in October; line breaks, never interpolated.
    (
        "Westfield Middle",
        460,
        0.080,
        {"trend": (0.0, 0.0, -0.020), "gap_period": "2026-10"},
    ),
    # Flu-hit: hit harder than average by the November seasonal bump.
    (
        "Northgate High",
        780,
        0.090,
        {"trend": (-0.005, -0.005, -0.005), "november_dip": 0.05},
    ),
    # Tiny and noisy: 14 students — small denominators swing the rate.
    (
        "Summit Alternative",
        14,
        0.100,
        {"trend": (+0.030, -0.030, +0.020), "partial_november": 4},
    ),
)

DISTRICT_SCHOOL_NAMES = frozenset(name for name, _, _, _ in DISTRICT_SCHOOLS)

NOVEMBER_DIP = 0.04  # district-wide flu-season absence bump in 2026-11
TRANSFER_SHARE = 0.05  # students whose enrollment starts in October


def _seeded_rng(master_seed: int, *parts: str) -> random.Random:
    """Deterministic RNG per (school, period, student) — reruns are
    byte-identical regardless of iteration order."""
    digest = hashlib.sha256(f"{master_seed}|{'|'.join(parts)}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def demo_district_csv(seed: int = 20261013) -> str:
    """Deterministic synthetic district CSV with real-world edge cases.

    Each enrolled day is a Bernoulli trial against a per-student daily
    absence propensity drawn from a Beta distribution around the school's
    base rate — so absence clusters the way it does in real schools
    (overdispersed), instead of spreading uniformly. Fictional students
    only; IDs never leave the import layer.
    """
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ["District", "SchoolName", "StudentID", "Period", "EnrolledDays", "PresentDays"]
    )
    for name, size, base_rate, opts in DISTRICT_SCHOOLS:
        slug = "".join(name.lower().split())
        n_transfer = max(1, int(size * TRANSFER_SHARE))
        trend = opts.get("trend", (0.0, 0.0, 0.0))
        for i in range(size):
            is_transfer = i >= size - n_transfer
            student = (
                f"synth-{slug}-xfer-{i:03d}" if is_transfer else f"synth-{slug}-{i:04d}"
            )
            chronic = "chronic_share" in opts and (i % 100) < int(
                opts["chronic_share"] * 100
            )
            for pi, (period, days) in enumerate(DISTRICT_PERIODS):
                if opts.get("gap_period") == period:
                    continue  # the data gap: nothing reported this period
                if is_transfer and period == "2026-09":
                    continue  # enrolled starting October
                enrolled = days
                if period == "2026-11" and i < opts.get("partial_november", 0):
                    enrolled = 6  # disenrolled mid-period
                # TW-492: the school's own trajectory, on top of the base rate.
                propensity = (opts["chronic_rate"] if chronic else base_rate) + trend[
                    pi
                ]
                if period == "2026-11":
                    propensity += NOVEMBER_DIP + opts.get("november_dip", 0.0)
                # Clamp: a probability, always. Trends never push it negative
                # or absurd — the generator stays honest at the edges.
                propensity = min(max(propensity, 0.001), 0.60)
                # Per-student propensity: Beta(mean=propensity), so some
                # students are rarely absent and a few are often absent.
                a = max(propensity * 30, 0.5)
                rng = _seeded_rng(seed, name, period, student)
                student_p = rng.betavariate(a, 30 - a + 0.5)
                absent = sum(1 for _ in range(enrolled) if rng.random() < student_p)
                writer.writerow(
                    ["NKC-DEMO", name, student, period, enrolled, enrolled - absent]
                )
    return out.getvalue()


if __name__ == "__main__":
    import json

    print(json.dumps(demo(), indent=2, sort_keys=True))
