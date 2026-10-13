"""Synthetic attendance dashboard. Renders the published attendance mart as a
self-contained HTML page with school/period filters. Stdlib only, no
external assets — works offline. Aggregate only: no student-level data
ever reaches the page. Synthetic data is labeled on every render.
"""

import html

from attendance import summarize
from importer import demo_csv, demo_mapping, import_csv, publish

PAGE_CSS = """
body{font-family:-apple-system,'Segoe UI',Arial,sans-serif;background:#f4f1ea;
color:#2b2b2b;margin:0;padding:24px}
.wrap{max-width:960px;margin:0 auto}
.banner{background:#1f2937;color:#fbbf24;padding:10px 16px;border-radius:8px;
font-weight:700;margin-bottom:16px}
h1{margin:0 0 4px}.sub{color:#6b7280;margin-bottom:20px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
gap:12px;margin-bottom:20px}
.card{background:#fff;border:1px solid #e5e0d5;border-radius:10px;padding:14px}
.card .k{font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.04em}
.card .v{font-size:28px;font-weight:700;color:#c2410c}
.filters{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap}
.filters label{font-size:13px;color:#6b7280}
.filters select{font-size:15px;padding:6px 10px;border-radius:6px;
border:1px solid #d6d0c2;background:#fff}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;
overflow:hidden}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #eee9dc}
th{background:#292524;color:#faf7f2;font-size:13px;text-transform:uppercase;
letter-spacing:.04em}
tr.hidden{display:none}
.count{font-size:13px;color:#6b7280;margin-top:10px}
.bar{height:8px;background:#eee9dc;border-radius:4px;min-width:80px}
.bar>i{display:block;height:8px;border-radius:4px;background:#c2410c}
.foot{margin-top:24px;font-size:12px;color:#9a958a}
"""

PAGE_JS = """
function applyFilters(){
  var s=document.getElementById('f-school').value;
  var p=document.getElementById('f-period').value;
  var shown=0,total=0;
  document.querySelectorAll('#m tbody tr').forEach(function(tr){
    total++;
    var ok=(s==='all'||tr.dataset.school===s)&&(p==='all'||tr.dataset.period===p);
    tr.classList.toggle('hidden',!ok);
    if(ok)shown++;
  });
  document.getElementById('count').textContent='Showing '+shown+' of '+total+' rows';
}
document.getElementById('f-school').addEventListener('change',applyFilters);
document.getElementById('f-period').addEventListener('change',applyFilters);
"""


def _options(values, element_id, label):
    opts = [f'<option value="all">All {html.escape(label)}</option>']
    for v in values:
        e = html.escape(v)
        opts.append(f'<option value="{e}">{e}</option>')
    return (f'<label>{html.escape(label)} <select id="{element_id}">'
            + "".join(opts) + "</select></label>")


def render(rows, *, district: str, allowed_schools: frozenset,
           title: str = "Attendance overview") -> str:
    """Render the dashboard HTML for a published attendance scope."""
    summary = summarize(rows, district=district, allowed_schools=allowed_schools)
    metrics = summary["metrics"]
    schools = sorted({m["school"] for m in metrics})
    periods = sorted({m["period"] for m in metrics})

    total_enrolled = sum(m["enrolled_days"] for m in metrics)
    total_present = sum(m["present_days"] for m in metrics)
    overall = (total_present / total_enrolled) if total_enrolled else None

    def pct(x):
        return f"{x * 100:.1f}%" if x is not None else "n/a"

    body_rows = []
    for m in metrics:
        rate = m["attendance_rate"]
        body_rows.append(
            "<tr data-school=\"{s}\" data-period=\"{p}\">"
            "<td>{s}</td><td>{p}</td>"
            "<td>{e:,}</td><td>{pr:,}</td><td>{n:,}</td>"
            "<td><div class=\"bar\"><i style=\"width:{w}%\"></i></div></td>"
            "<td>{r}</td></tr>".format(
                s=html.escape(m["school"]), p=html.escape(m["period"]),
                e=m["enrolled_days"], pr=m["present_days"],
                n=m["student_period_records"],
                w=f"{rate * 100:.1f}" if rate is not None else 0,
                r=pct(rate)))

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>{PAGE_CSS}</style></head>
<body><div class="wrap">
<div class="banner">SYNTHETIC SAMPLE DATA &mdash; no real student records</div>
<h1>{html.escape(title)}</h1>
<div class="sub">District scope: {html.escape(district)} &middot;
{summary["selected_records"]:,} student-period records &middot;
definition: present days / enrolled days (weighted; zero denominator is null)</div>
<div class="cards">
<div class="card"><div class="k">Attendance rate</div><div class="v">{pct(overall)}</div></div>
<div class="card"><div class="k">Enrolled days</div><div class="v">{total_enrolled:,}</div></div>
<div class="card"><div class="k">Present days</div><div class="v">{total_present:,}</div></div>
<div class="card"><div class="k">Schools</div><div class="v">{len(schools)}</div></div>
<div class="card"><div class="k">Periods</div><div class="v">{len(periods)}</div></div>
</div>
<div class="filters">{_options(schools, "f-school", "Schools")}
{_options(periods, "f-period", "Periods")}</div>
<table id="m"><thead><tr><th>School</th><th>Period</th><th>Enrolled days</th>
<th>Present days</th><th>Records</th><th></th><th>Rate</th></tr></thead>
<tbody>{''.join(body_rows)}</tbody></table>
<div class="count" id="count">Showing {len(body_rows)} of {len(body_rows)} rows</div>
<div class="foot">Prepared by Twistor Holdings LLC &middot; synthetic demonstration
for proposal purposes only. Source hash {summary["selected_source_sha256"][:16]}&hellip;</div>
</div><script>{PAGE_JS}</script></body></html>"""


def demo() -> str:
    """Full pipeline on synthetic data: CSV -> import -> publish -> dashboard."""
    result = import_csv(demo_csv(), demo_mapping())
    schools = frozenset({"North", "South", "East", "West"})
    publish(result, district="DEMO", allowed_schools=schools)  # validates
    return render(result.accepted, district="DEMO", allowed_schools=schools,
                  title="Attendance overview — synthetic district demo")


if __name__ == "__main__":
    page = demo()
    with open("attendance-dashboard.html", "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"wrote attendance-dashboard.html ({len(page):,} bytes)")
