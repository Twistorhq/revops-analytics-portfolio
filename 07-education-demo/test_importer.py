import unittest

from importer import REQUIRED_FIELDS, demo_csv, demo_mapping, import_csv, publish


def csv_with(
    rows,
    header=(
        "District",
        "SchoolName",
        "StudentID",
        "Period",
        "EnrolledDays",
        "PresentDays",
    ),
):
    lines = [",".join(header)]
    lines += [",".join(str(c) for c in r) for r in rows]
    return "\n".join(lines) + "\n"


GOOD = [("D", "S", "s1", "2026-09", 20, 18), ("D", "S", "s2", "2026-09", 20, 20)]


class ImporterTests(unittest.TestCase):
    def test_clean_import_reconciles(self):
        result = import_csv(csv_with(GOOD), demo_mapping())
        self.assertEqual(result.source_rows, 2)
        self.assertEqual(result.accepted_rows, 2)
        self.assertEqual(result.rejected_rows, 0)
        self.assertTrue(result.reconciled)
        self.assertEqual(result.report()["reconciled"], True)

    def test_publish_clean_import(self):
        result = import_csv(csv_with(GOOD), demo_mapping())
        out = publish(result, district="D", allowed_schools=frozenset({"S"}))
        self.assertEqual(out["selected_records"], 2)
        metric = out["metrics"][0]
        self.assertAlmostEqual(metric["attendance_rate"], 38 / 40)

    def test_mapping_missing_field_fails_fast(self):
        mapping = {k: v for k, v in demo_mapping().items() if k != "period"}
        with self.assertRaisesRegex(ValueError, "missing fields"):
            import_csv(csv_with(GOOD), mapping)

    def test_mapped_header_absent_fails_fast(self):
        mapping = dict(demo_mapping(), school="Nope")
        with self.assertRaisesRegex(ValueError, "not found in CSV"):
            import_csv(csv_with(GOOD), mapping)

    def test_non_injective_mapping_fails_fast(self):
        # Two canonical fields reading the same header would silently
        # merge columns and corrupt aggregates — fail before any row.
        mapping = dict(demo_mapping(), student="SchoolName")
        with self.assertRaisesRegex(ValueError, "not injective"):
            import_csv(csv_with(GOOD), mapping)

    def test_non_injective_mapping_names_the_header(self):
        mapping = dict(demo_mapping(), student="SchoolName")
        with self.assertRaisesRegex(ValueError, "SchoolName"):
            import_csv(csv_with(GOOD), mapping)

    def test_utf8_bom_stripped(self):
        text = "\ufeff" + csv_with(GOOD)
        result = import_csv(text, demo_mapping())
        self.assertEqual(result.accepted_rows, 2)
        self.assertTrue(result.reconciled)

    def test_rejected_rows_diagnosed(self):
        rows = [
            ("D", "S", "ok1", "2026-09", 20, 18),  # accepted
            ("D", "S", "", "2026-09", 20, 18),  # missing identifier
            ("D", "S", "bad1", "2026-09", 20, "many"),  # bad_count
            ("D", "S", "bad2", "2026-09", 20, 21),  # invalid_counts
            ("D", "S", "bad3", "2026-09", -1, 0),  # bad_count negative
            ("D", "S", "ok1", "2026-09", 20, 18),  # duplicate_grain
        ]
        result = import_csv(csv_with(rows), demo_mapping())
        self.assertEqual(result.source_rows, 6)
        self.assertEqual(result.accepted_rows, 1)
        self.assertEqual(result.rejected_rows, 5)
        self.assertTrue(result.reconciled)
        by_row = {r.row_number: r for r in result.rejected}
        self.assertEqual(by_row[2].reason, "missing_identifier")
        self.assertEqual(by_row[3].reason, "bad_count")
        self.assertEqual(by_row[4].reason, "invalid_counts")
        self.assertEqual(by_row[5].reason, "bad_count")
        self.assertEqual(by_row[6].reason, "duplicate_grain")
        for r in result.rejected:  # diagnostics carry the evidence
            self.assertTrue(r.detail)
            self.assertTrue(r.raw)
        self.assertEqual(
            result.rejections_by_reason(),
            {
                "missing_identifier": 1,
                "bad_count": 2,
                "invalid_counts": 1,
                "duplicate_grain": 1,
            },
        )

    def test_publish_blocked_on_rejections(self):
        rows = GOOD + [("D", "S", "bad", "2026-09", 20, 99)]
        result = import_csv(csv_with(rows), demo_mapping())
        with self.assertRaisesRegex(ValueError, "rejected row"):
            publish(result, district="D", allowed_schools=frozenset({"S"}))

    def test_empty_csv_reconciles(self):
        result = import_csv(csv_with([]), demo_mapping())
        self.assertEqual(result.source_rows, 0)
        self.assertTrue(result.reconciled)
        out = publish(result, district="D", allowed_schools=frozenset({"S"}))
        self.assertEqual(out["metrics"], [])

    def test_demo_csv_end_to_end(self):
        text = demo_csv()
        result = import_csv(text, demo_mapping())
        self.assertTrue(result.reconciled)
        self.assertEqual(result.rejected_rows, 0)
        self.assertEqual(result.accepted_rows, 4 * 25 * 3)
        out = publish(
            result,
            district="DEMO",
            allowed_schools=frozenset({"North", "South", "East", "West"}),
        )
        self.assertEqual(len(out["metrics"]), 12)  # 4 schools x 3 periods

    def test_extra_columns_tolerated(self):
        header = (
            "District",
            "SchoolName",
            "StudentID",
            "Period",
            "EnrolledDays",
            "PresentDays",
            "Notes",
        )
        text = csv_with([("D", "S", "s1", "2026-09", 20, 18, "hi")], header)
        result = import_csv(text, demo_mapping())
        self.assertEqual(result.accepted_rows, 1)
        self.assertTrue(result.reconciled)

    def test_required_fields_constant(self):
        self.assertEqual(
            set(REQUIRED_FIELDS),
            {
                "district",
                "school",
                "student",
                "period",
                "enrolled_days",
                "present_days",
            },
        )


if __name__ == "__main__":
    unittest.main()
