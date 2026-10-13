"""Synthetic attendance dashboard — NKC bid demonstrator (TW-490).

Renders the published attendance mart as a self-contained HTML page.
Stdlib only, no external assets — works offline. Aggregate only: no
student-level data ever reaches the page. Synthetic data is labeled on
every render.

Design brief: read like a serious internal analytics tool built by a
senior data engineer. Every number labeled, every chart honest, the
math documented on the page. No decorative gradients, no emoji-as-UI,
no card-grid slop.
"""

import html

from attendance import summarize
from importer import (
    DISTRICT_SCHOOL_NAMES,
    demo_district_csv,
    demo_mapping,
    import_csv,
    publish,
)

PAGE_CSS = """
:root{
  --paper:#f7f6f4; --surface:#ffffff; --ink:#16181d; --muted:#5d6470;
  --faint:#646a76; --hairline:#e6e2d9; --accent:#0f766e; --accent-deep:#0b5f59;
  --warn:#b45309; --bad:#b91c1c; --ok:#15803d; --line:#c9c4b6;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
.utility{background:#16181d;color:#f3efe6;font-size:12.5px;letter-spacing:.02em;
  padding:8px 24px;text-align:center}
.utility strong{font-weight:700;letter-spacing:.08em}
.wrap{max-width:1060px;margin:0 auto;padding:0 24px 72px}
.masthead{padding:36px 0 8px;border-bottom:1px solid var(--hairline)}
.masthead h1{font-size:30px;line-height:1.2;margin:0 0 6px;letter-spacing:-.01em}
.masthead .lede{color:var(--muted);margin:0;font-size:15px}
.hero{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);
  gap:40px;padding:28px 0;border-bottom:1px solid var(--hairline)}
@media(max-width:720px){.hero{grid-template-columns:1fr}}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;
  color:var(--muted);margin-bottom:6px}
.hero-num{font-size:64px;font-weight:750;letter-spacing:-.02em;line-height:1;
  font-variant-numeric:tabular-nums;color:var(--ink)}
.hero-delta{margin-top:8px;font-size:14px;font-weight:600}
.hero-delta.up{color:var(--ok)} .hero-delta.down{color:var(--bad)}
.hero-def{margin:14px 0 0;font-size:13.5px;color:var(--muted);max-width:44ch}
.hero-def code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:12.5px;background:#efede8;padding:1px 6px;border-radius:4px;color:var(--ink)}
.hero-side{align-self:start}
.stat-row{display:grid;grid-template-columns:1fr 1fr;gap:0;border-top:1px solid var(--hairline)}
.stat{padding:12px 0;border-bottom:1px solid var(--hairline)}
.stat .k{font-size:12px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.07em;margin-bottom:2px}
.stat .v{font-size:21px;font-weight:700;font-variant-numeric:tabular-nums}
.stat .v small{font-size:13px;font-weight:400;color:var(--muted)}
section.block{padding:28px 0;border-bottom:1px solid var(--hairline)}
section.block h2{font-size:19px;margin:0 0 4px;letter-spacing:-.005em}
section.block .note{color:var(--muted);font-size:13.5px;margin:0 0 18px;max-width:72ch}
.filters{display:flex;gap:16px;margin:0 0 14px;flex-wrap:wrap;align-items:end}
.filters label{font-size:13px;color:var(--muted);display:block}
.filters label span{display:block;margin-bottom:4px}
.filters select{font-size:14.5px;padding:7px 10px;border-radius:6px;
  border:1px solid #d8d3c6;background:#fff;color:var(--ink);min-width:200px}
.filters select:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
table{width:100%;border-collapse:collapse;background:var(--surface);
  border:1px solid var(--hairline);border-radius:8px;overflow:hidden;font-size:14px}
thead th{background:#f1efe9;text-align:left;font-size:11.5px;text-transform:uppercase;
  letter-spacing:.07em;color:var(--muted);padding:10px 14px;border-bottom:1px solid var(--hairline);
  white-space:nowrap}
tbody td{padding:9px 14px;border-bottom:1px solid #f0ede6;vertical-align:middle}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:#faf9f6}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.school{font-weight:600}
.rate-cell{display:flex;align-items:center;gap:10px;justify-content:flex-end}
.meter{width:88px;height:6px;background:#ece9e1;border-radius:3px;overflow:hidden;flex:none}
.meter>i{display:block;height:100%;background:var(--accent);border-radius:3px}
.meter>i.low{background:var(--warn)} .meter>i.crit{background:var(--bad)}
.delta-up{color:var(--ok);font-weight:600} .delta-down{color:var(--bad);font-weight:600}
.delta-flat{color:var(--faint)}
.flag{display:inline-block;font-size:12px;font-weight:600;padding:2px 8px;border-radius:4px;
  background:#fdf3e7;color:var(--warn);border:1px solid #f0dcc0;white-space:nowrap}
.flag.gap{background:#fbeaea;color:var(--bad);border-color:#f3c8c8}
.nodata{color:var(--faint);font-style:italic}
tr.hidden{display:none}
.count{font-size:13px;color:var(--muted);margin-top:10px}
.chart{background:var(--surface);border:1px solid var(--hairline);border-radius:8px;
  padding:20px 16px 8px;margin-top:6px}
.chart svg{display:block;width:100%;height:auto}
.chart-cap{font-size:13px;color:var(--muted);margin:10px 4px 0;max-width:76ch}
.method{background:var(--surface);border:1px solid var(--hairline);border-radius:8px;
  padding:20px 24px}
.method dl{margin:0;display:grid;grid-template-columns:180px 1fr;gap:10px 20px;font-size:14px}
@media(max-width:640px){.method dl{grid-template-columns:1fr}}
.method dt{font-weight:700}
.method dd{margin:0;color:#3a3f47}
.method dd code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;
  background:#efede8;padding:1px 6px;border-radius:4px;color:var(--ink)}
.foot{margin-top:28px;font-size:12.5px;color:var(--faint)}
.foot .hash{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
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


def _pct(x, digits=1):
    return f"{x * 100:.{digits}f}%" if x is not None else "n/a"


def _points(delta):
    """Format a percentage-point delta: +0.6 pts / -1.2 pts / n/a."""
    if delta is None:
        return '<span class="delta-flat">n/a</span>'
    cls = (
        "delta-up"
        if delta > 0.0005
        else ("delta-down" if delta < -0.0005 else "delta-flat")
    )
    sign = "+" if delta > 0 else ""
    return f'<span class="{cls}">{sign}{delta * 100:.1f} pts</span>'


def _trend_svg(school_series, district_series, periods):
    """Hand-built SVG line chart: attendance rate by period.

    school_series: {school: {period: rate|None}}. district_series:
    {period: rate|None}. Gaps (None) break the line — never interpolated.
    """
    W, H = 660, 280
    pad_l, pad_r, pad_t, pad_b = 46, 90, 14, 30
    iw, ih = W - pad_l - pad_r, H - pad_t - pad_b

    rates = [r for s in school_series.values() for r in s.values() if r is not None]
    rates += [r for r in district_series.values() if r is not None]
    lo = max(0, int(min(rates) * 100) - 2)
    hi = 100

    def x(i):
        if len(periods) > 1:
            return pad_l + iw * i / (len(periods) - 1)
        return pad_l + iw / 2

    def y(rate):
        return pad_t + ih * (1 - (rate * 100 - lo) / (hi - lo))

    parts = [
        (
            f'<svg viewBox="0 0 {W} {H}" role="img" '
            'aria-label="Attendance rate trend by period">'
        ),
        "<title>Attendance rate trend by period</title>",
        (
            "<desc>Line per school across reporting periods; bold teal line "
            "is the district weighted average. Breaks mark periods with no data.</desc>"
        ),
    ]
    step = 5
    tick = ((lo + step - 1) // step) * step
    while tick <= hi:
        yy = y(tick / 100)
        parts.append(
            f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{W - pad_r}" y2="{yy:.1f}" '
            f'stroke="#e6e2d9" stroke-width="1"/>'
            f'<text x="{pad_l - 8}" y="{yy + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="#646a76">{tick}%</text>'
        )
        tick += step
    for i, p in enumerate(periods):
        parts.append(
            f'<text x="{x(i):.1f}" y="{H - 8}" text-anchor="middle" '
            f'font-size="11" fill="#646a76">{html.escape(p)}</text>'
        )
    for school in sorted(school_series):
        runs, run = [], []
        prev_i = None
        for i, p in enumerate(periods):
            r = school_series[school].get(p)
            if r is None:
                if run:
                    runs.append(run)
                    run = []
            else:
                if prev_i is not None and i != prev_i + 1 and run:
                    runs.append(run)
                    run = []
                run.append((x(i), y(r)))
                prev_i = i
        if run:
            runs.append(run)
        for run_pts in runs:
            d = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in run_pts)
            parts.append(
                f'<path d="{d}" fill="none" stroke="#c9c4b6" stroke-width="1.2"/>'
            )
    dpts = [
        (x(i), y(r))
        for i, p in enumerate(periods)
        if (r := district_series.get(p)) is not None
    ]
    if dpts:
        d = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in dpts)
        parts.append(
            f'<path d="{d}" fill="none" stroke="#0f766e" '
            f'stroke-width="2.6" stroke-linejoin="round"/>'
        )
        for a, b in dpts:
            parts.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.6" fill="#0f766e"/>')
    for j, school in enumerate(_labeled_schools(school_series, periods)):
        vals = [(p, r) for p, r in school_series[school].items() if r is not None]
        if not vals:
            continue
        p, r = vals[-1]
        i = periods.index(p)
        # Stagger alternate labels so neighboring lines don't collide.
        dy = 4 if j % 2 == 0 else -10
        parts.append(
            f'<text x="{x(i) + 8:.1f}" y="{y(r) + dy:.1f}" font-size="11.5" '
            f'fill="#5d6470">{html.escape(school)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _labeled_schools(school_series, periods):
    """Top-2 and bottom-2 schools by latest available period — the four
    lines that define the chart's spread. TW-492: with real variation in
    the data, four labels read the story; two left the middle anonymous."""
    latest = {}
    for s, d in school_series.items():
        for p in reversed(periods):
            if d.get(p) is not None:
                latest[s] = d[p]
                break
    if not latest:
        return []
    ranked = sorted(latest, key=latest.get)
    picks = []
    for s in (ranked[-1], ranked[-2], ranked[0], ranked[1]):
        if s not in picks:
            picks.append(s)
        if len(picks) == 4:
            break
    return picks


def _options(values, element_id, label):
    opts = [f'<option value="all">All {html.escape(label)}</option>']
    for v in values:
        e = html.escape(v)
        opts.append(f'<option value="{e}">{e}</option>')
    return (
        f'<label for="{element_id}"><span>{html.escape(label)}</span>'
        f'<select id="{element_id}">' + "".join(opts) + "</select></label>"
    )


def render(
    rows,
    *,
    district: str,
    allowed_schools: frozenset,
    title: str = "Attendance overview",
) -> str:
    """Render the dashboard HTML for a published attendance scope."""
    summary = summarize(rows, district=district, allowed_schools=allowed_schools)
    metrics = summary["metrics"]
    by_key = {(m["school"], m["period"]): m for m in metrics}
    schools = sorted({m["school"] for m in metrics})
    periods = sorted({m["period"] for m in metrics})

    # Expected grid: every in-scope school x every period. A missing cell is
    # a data gap — rendered explicitly, never silently dropped.
    expected = [(s, p) for s in schools for p in periods]

    # District aggregates per period + overall (weighted; never averaged).
    per_period = {}
    for p in periods:
        pm = [m for m in metrics if m["period"] == p]
        e = sum(m["enrolled_days"] for m in pm)
        pr = sum(m["present_days"] for m in pm)
        per_period[p] = pr / e if e else None
    total_enrolled = sum(m["enrolled_days"] for m in metrics)
    total_present = sum(m["present_days"] for m in metrics)
    overall = (total_present / total_enrolled) if total_enrolled else None

    delta = None
    if (
        len(periods) >= 2
        and per_period[periods[-1]] is not None
        and per_period[periods[-2]] is not None
    ):
        delta = per_period[periods[-1]] - per_period[periods[-2]]
    delta_html = ""
    if delta is not None:
        word = "up" if delta > 0.0005 else ("down" if delta < -0.0005 else "flat")
        arrow = {"up": "+", "down": "", "flat": "\u00b1"}[word]
        delta_html = (
            f'<div class="hero-delta {word}">{arrow}'
            f"{delta * 100:.1f} pts vs {html.escape(periods[-2])}</div>"
        )

    school_series = {
        s: {
            p: (by_key[(s, p)]["attendance_rate"] if (s, p) in by_key else None)
            for p in periods
        }
        for s in schools
    }

    body_rows = []
    for s, p in expected:
        m = by_key.get((s, p))
        if m is None:
            body_rows.append(
                f'<tr data-school="{html.escape(s)}" data-period="{html.escape(p)}">'
                f'<td class="school">{html.escape(s)}</td><td>{html.escape(p)}</td>'
                '<td class="num nodata" colspan="2">No data reported</td>'
                '<td class="num nodata">&mdash;</td>'
                '<td class="num nodata">&mdash;</td>'
                '<td class="num nodata">n/a</td>'
                '<td><span class="flag gap">Data gap</span></td></tr>'
            )
            continue
        rate = m["attendance_rate"]
        d_rate = per_period[p]
        vs = (rate - d_rate) if (rate is not None and d_rate is not None) else None
        bar_cls = (
            "crit"
            if (rate is not None and rate < 0.90)
            else ("low" if (rate is not None and rate < 0.93) else "")
        )
        note = ""
        if m["student_period_records"] < 20:
            note = f'<span class="flag">Small n ({m["student_period_records"]})</span>'
        body_rows.append(
            '<tr data-school="{s}" data-period="{p}">'
            '<td class="school">{s}</td><td>{p}</td>'
            '<td class="num"><span class="rate-cell">'
            '<span class="meter"><i class="{bc}" style="width:{w}%"></i></span>'
            "{r}</span></td>"
            '<td class="num">{vs}</td>'
            '<td class="num">{e:,}</td><td class="num">{pr:,}</td>'
            '<td class="num">{n:,}</td>'
            "<td>{note}</td></tr>".format(
                s=html.escape(s),
                p=html.escape(p),
                bc=bar_cls,
                w=f"{rate * 100:.1f}" if rate is not None else 0,
                r=_pct(rate),
                vs=_points(vs),
                e=m["enrolled_days"],
                pr=m["present_days"],
                n=m["student_period_records"],
                note=note,
            )
        )

    period_label = f"{periods[0]} &ndash; {periods[-1]}" if periods else "no periods"
    chart_html = ""
    if periods and school_series:
        chart_html = (
            '<section class="block"><h2>Trend by period</h2>'
            '<p class="note">Attendance rate per reporting period. Breaks in a '
            "line mark periods with no reported data &mdash; never "
            "interpolated.</p>"
            f'<div class="chart">{_trend_svg(school_series, per_period, periods)}</div>'
            '<p class="chart-cap">Bold teal line: district weighted average. '
            "Gray lines: individual schools. The November dip reflects the "
            "seasonal absence bump in the synthetic data.</p></section>"
        )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>{PAGE_CSS}</style></head>
<body>
<div class="utility"><strong>SYNTHETIC SAMPLE DATA</strong> &mdash; no real student
records. Generated for proposal demonstration only.</div>
<div class="wrap">
<header class="masthead">
<h1>{html.escape(title)}</h1>
<p class="lede">District scope: {html.escape(district)} &middot; {period_label} &middot;
{summary["selected_records"]:,} student-period records</p>
</header>
<section class="hero" aria-label="District headline metrics">
<div>
<div class="eyebrow">District attendance rate</div>
<div class="hero-num">{_pct(overall)}</div>
{delta_html}
<p class="hero-def">Weighted across every enrolled day:
<code>&Sigma;present &divide; &Sigma;enrolled</code>. Rates are never averaged
across schools or periods; a zero denominator is reported as null.</p>
</div>
<div class="hero-side">
<div class="stat-row">
<div class="stat"><div class="k">Enrolled days</div><div class="v">{total_enrolled:,}</div></div>
<div class="stat"><div class="k">Present days</div><div class="v">{total_present:,}</div></div>
<div class="stat"><div class="k">Schools</div><div class="v">{len(schools)}</div></div>
<div class="stat"><div class="k">Periods</div><div class="v">{len(periods)}</div></div>
</div>
</div>
</section>
{chart_html}
<section class="block">
<h2>School performance</h2>
<p class="note">One row per school per reporting period. &ldquo;Vs district&rdquo;
compares the school&rsquo;s period rate to the district weighted rate for the
same period, in percentage points.</p>
<div class="filters">{_options(schools, "f-school", "Schools")}
{_options(periods, "f-period", "Periods")}</div>
<table id="m">
<thead><tr><th scope="col">School</th><th scope="col">Period</th>
<th scope="col" class="num">Rate</th><th scope="col" class="num">Vs district</th>
<th scope="col" class="num">Enrolled days</th><th scope="col" class="num">Present days</th>
<th scope="col" class="num">Records</th><th scope="col">Note</th></tr></thead>
<tbody>{"".join(body_rows)}</tbody></table>
<div class="count" id="count">Showing {len(body_rows)} of {len(body_rows)} rows</div>
</section>
<section class="block">
<h2>How these numbers are built</h2>
<div class="method"><dl>
<dt>Formula</dt><dd><code>attendance_rate = &Sigma;present_days &divide;
&Sigma;enrolled_days</code>, weighted across every enrolled day in scope. School
and district rates are never computed by averaging percentages.</dd>
<dt>Grain</dt><dd>One record per district &times; school &times; student &times;
period. Duplicates are rejected at import.</dd>
<dt>Null handling</dt><dd>A zero enrolled-day denominator yields a null rate,
shown as &ldquo;n/a&rdquo;. Periods with no reported rows are flagged as data
gaps, not zero-filled.</dd>
<dt>Scope</dt><dd>District <code>{html.escape(district)}</code>;
{len(schools)} school(s) in the trusted scope. Records outside the scope are
excluded before aggregation.</dd>
<dt>Provenance</dt><dd>Source fingerprint
<code class="hash">{summary["selected_source_sha256"][:16]}&hellip;</code> over the
canonical record set. Reruns over the same source reproduce byte-identical output.</dd>
</dl></div>
</section>
<div class="foot">Prepared by Twistor Holdings LLC &middot; synthetic demonstration
for proposal purposes only.</div>
</div><script>{PAGE_JS}</script></body></html>"""


def demo() -> str:
    """Full pipeline on the rich synthetic district: CSV -> import ->
    publish -> dashboard."""
    result = import_csv(demo_district_csv(), demo_mapping())
    publish(
        result,
        district="NKC-DEMO",  # validates
        allowed_schools=DISTRICT_SCHOOL_NAMES,
    )
    return render(
        result.accepted,
        district="NKC-DEMO",
        allowed_schools=DISTRICT_SCHOOL_NAMES,
        title="Student attendance overview — synthetic district demo",
    )


if __name__ == "__main__":
    page = demo()
    with open("attendance-dashboard.html", "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"wrote attendance-dashboard.html ({len(page):,} bytes)")
