"""HTML report generator.

Converts ExplainParallelReport (and optionally CompareReport list) into a
self-contained multi-tab HTML page with charts and tables.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .report_data import ExplainParallelReport, ParallelGroupReport, CompareReport
from .analyzer import build_explain_parallel_report, summarize_test_statuses, _repeated_change_tests
from .file_registry import report_label


# ── HTML template helpers ─────────────────────────────────────────────────────

def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


def _bar(value: float, max_value: float, color: str = "#4f8ef7", height: int = 16) -> str:
    pct = min(value / max_value * 100, 100) if max_value else 0
    return (
        f'<div class="bar-wrap" title="{value:.1f}">'
        f'<div class="bar" style="width:{pct:.1f}%;background:{color};height:{height}px"></div>'
        f'<span class="bar-label">{value:.1f}</span>'
        f'</div>'
    )


def _tab_btn(tab_id: str, label: str, active: bool = False) -> str:
    cls = "tab-btn active" if active else "tab-btn"
    return f'<button class="{cls}" onclick="showTab(\'{tab_id}\')">{_esc(label)}</button>'


def _tab_panel(tab_id: str, content: str, active: bool = False) -> str:
    display = "block" if active else "none"
    return f'<div id="{tab_id}" class="tab-panel" style="display:{display}">{content}</div>'


# ── section builders ──────────────────────────────────────────────────────────

def _section(title: str, content: str) -> str:
    return f'<section class="card"><h2>{_esc(title)}</h2>{content}</section>'


def _table(headers: list[str], rows: list[list[str]], cls: str = "") -> str:
    th = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = ""
    for row in rows:
        tds = "".join(f"<td>{cell}</td>" for cell in row)
        body += f"<tr>{tds}</tr>"
    return f'<table class="report-table {cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def _kv_grid(pairs: list[tuple[str, str]]) -> str:
    items = "".join(
        f'<div class="kv-item"><span class="kv-key">{_esc(k)}</span>'
        f'<span class="kv-val">{v}</span></div>'
        for k, v in pairs
    )
    return f'<div class="kv-grid">{items}</div>'


# ── parallel group tab ────────────────────────────────────────────────────────

def _render_group_tab(grp: ParallelGroupReport) -> str:
    sections: list[str] = []

    # Overview KV
    sections.append(_section("Overview", _kv_grid([
        ("Parallel count", f"<strong>par{grp.parallel_count}</strong>"),
        ("Runs in group", str(grp.run_count)),
        ("Unique tests", f"{grp.total_unique_tests:,}"),
        ("Flaky tests", f"<strong class='warn'>{grp.flaky_count:,}</strong> ({grp.flaky_pct:.1f}%)"),
        ("Avg failures / run", f"<strong class='fail'>{grp.norm(grp.total_fail_raw):.1f}</strong>"),
        ("Avg passed / run", f"<strong class='pass'>{grp.norm(grp.total_pass_raw):.1f}</strong>"),
        ("Avg skipped / run", str(f"{grp.norm(grp.total_skip_raw):.1f}")),
    ])))

    # Flaky tests table
    if grp.flaky_tests:
        max_fail = max(r.fail_count for r in grp.flaky_tests) or 1
        rows = []
        for row in grp.flaky_tests[:30]:
            rows.append([
                _esc(row.label),
                str(row.pass_count),
                str(row.fail_count),
                _bar(row.fail_rate, 100, "#e05d5d"),
            ])
        sections.append(_section(
            f"Top Flaky Tests (showing up to 30 of {grp.flaky_count})",
            _table(["Test", "Pass", "Fail", "Fail Rate"], rows)
        ))

    # Flaky Publisher / Subscriber
    if grp.flaky_pub:
        max_pub = max(grp.flaky_pub.values()) or 1
        rows_pub = [
            [_esc(pub),
             str(grp.flaky_pub_test_count.get(pub, 0)),
             _bar(grp.norm(v), grp.norm(max_pub), "#e05d5d")]
            for pub, v in sorted(grp.flaky_pub.items(), key=lambda x: -x[1])[:10]
        ]
        max_sub = max(grp.flaky_sub.values()) or 1
        rows_sub = [
            [_esc(sub),
             str(grp.flaky_sub_test_count.get(sub, 0)),
             _bar(grp.norm(v), grp.norm(max_sub), "#e05d5d")]
            for sub, v in sorted(grp.flaky_sub.items(), key=lambda x: -x[1])[:10]
        ]
        sections.append(_section("Flaky by DDS Implementation", (
            "<h3>Publishers</h3>"
            + _table(["Publisher", "Flaky tests", "Flaky failures/run"], rows_pub)
            + "<h3>Subscribers</h3>"
            + _table(["Subscriber", "Flaky tests", "Flaky failures/run"], rows_sub)
        )))

    # Flaky QoS areas
    if grp.flaky_feat:
        max_feat = max(grp.flaky_feat.values()) or 1
        rows_feat = [
            [_esc(feat), _bar(grp.norm(v), grp.norm(max_feat), "#e07d2d")]
            for feat, v in sorted(grp.flaky_feat.items(), key=lambda x: -x[1])[:10]
        ]
        sections.append(_section("Flaky Areas (QoS / Feature)",
                                 _table(["Feature", "Flaky failures/run"], rows_feat)))

    # Overall failure areas
    if grp.feature_fails:
        max_ff = max(grp.feature_fails.values()) or 1
        rows_ff = [
            [_esc(feat), _bar(grp.norm(v), grp.norm(max_ff), "#4f8ef7")]
            for feat, v in sorted(grp.feature_fails.items(), key=lambda x: -x[1])[:10]
        ]
        sections.append(_section("Overall Failure Areas (QoS / Feature)",
                                 _table(["Feature", "Failures/run"], rows_ff)))

    # Overall pub/sub
    if grp.pub_fails:
        max_p = max(grp.pub_fails.values()) or 1
        max_s = max(grp.sub_fails.values()) or 1
        rows_p = [
            [_esc(p), _bar(grp.norm(v), grp.norm(max_p), "#4f8ef7")]
            for p, v in sorted(grp.pub_fails.items(), key=lambda x: -x[1])[:10]
        ]
        rows_s = [
            [_esc(s), _bar(grp.norm(v), grp.norm(max_s), "#7b4ff7")]
            for s, v in sorted(grp.sub_fails.items(), key=lambda x: -x[1])[:10]
        ]
        sections.append(_section("Overall Failures by DDS Implementation", (
            "<h3>Publishers</h3>" + _table(["Publisher", "Failures/run"], rows_p)
            + "<h3>Subscribers</h3>" + _table(["Subscriber", "Failures/run"], rows_s)
        )))

    return "\n".join(sections)


# ── compare reports tab ───────────────────────────────────────────────────────

def _render_compare_tab(reports: list[CompareReport], files: list[Path]) -> str:
    sections: list[str] = []

    repeated = _repeated_change_tests(reports)
    status_summary = summarize_test_statuses(files)

    # Summary table
    summary_rows = []
    for r in reports:
        status_ch = sum("status" in item.differences for item in r.changed)
        summary_rows.append([
            _esc(report_label(r.first_file)),
            _esc(report_label(r.second_file)),
            str(r.first_count),
            str(r.second_count),
            str(len(r.added)),
            str(len(r.removed)),
            f"<strong class='{'fail' if status_ch else ''}'>{status_ch}</strong>",
        ])
    sections.append(_section("Run-to-Run Comparison Summary", _table(
        ["From", "To", "Cases (A)", "Cases (B)", "Added", "Removed", "Status changes"],
        summary_rows
    )))

    # Repeated changes
    if repeated:
        rows = [[_esc(t), str(c)] for t, c in sorted(repeated.items(), key=lambda x: -x[1])[:30]]
        sections.append(_section(
            f"Repeatedly Changing Tests ({len(repeated)} total)",
            _table(["Test", "# comparisons changed"], rows)
        ))

    # Failure frequency
    if status_summary:
        max_fail = max(c.get("failure", 0) + c.get("error", 0) for _, c in status_summary) or 1
        rows_sf = []
        for label, counts in status_summary[:50]:
            tf = counts.get("failure", 0) + counts.get("error", 0)
            rows_sf.append([
                _esc(label),
                str(counts.get("passed", 0)),
                str(counts.get("failure", 0)),
                str(counts.get("error", 0)),
                str(counts.get("skipped", 0)),
                _bar(tf, max_fail, "#e05d5d"),
            ])
        sections.append(_section(
            f"Failure Frequency Across All Reports (top 50 of {len(status_summary)})",
            _table(["Test", "Passed", "Failed", "Errors", "Skipped", "Total failures"], rows_sf)
        ))

    return "\n".join(sections)


# ── full HTML page ────────────────────────────────────────────────────────────

_CSS = """
:root {
  --bg: #0f1117; --card: #1a1d2e; --border: #2a2d3e;
  --text: #e2e8f0; --muted: #8892a4; --accent: #4f8ef7;
  --pass: #4ade80; --fail: #f87171; --warn: #fbbf24;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif;
       font-size: 14px; line-height: 1.6; }
a { color: var(--accent); }
h1 { font-size: 1.6rem; font-weight: 700; margin-bottom: .25rem; }
h2 { font-size: 1.1rem; font-weight: 600; margin-bottom: .75rem; color: var(--accent); }
h3 { font-size: .95rem; font-weight: 600; margin: 1rem 0 .5rem; color: var(--muted); }
.header { background: var(--card); border-bottom: 1px solid var(--border);
          padding: 1.25rem 2rem; }
.subtitle { color: var(--muted); font-size: .85rem; }
.tabs { display: flex; gap: .5rem; padding: 1rem 2rem .25rem;
        background: var(--card); border-bottom: 1px solid var(--border);
        flex-wrap: wrap; }
.tab-btn { background: transparent; border: 1px solid var(--border);
           color: var(--muted); padding: .4rem 1rem; border-radius: 6px;
           cursor: pointer; font-size: .85rem; transition: all .15s; }
.tab-btn:hover { border-color: var(--accent); color: var(--accent); }
.tab-btn.active { background: var(--accent); border-color: var(--accent);
                  color: #fff; font-weight: 600; }
.tab-panel { padding: 1.5rem 2rem; }
.card { background: var(--card); border: 1px solid var(--border);
        border-radius: 10px; padding: 1.25rem 1.5rem; margin-bottom: 1.25rem; }
.kv-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: .5rem; }
.kv-item { background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
           padding: .5rem .75rem; display: flex; flex-direction: column; }
.kv-key { font-size: .75rem; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
.kv-val { font-size: 1.1rem; font-weight: 600; margin-top: .1rem; }
.report-table { width: 100%; border-collapse: collapse; font-size: .82rem; }
.report-table th { text-align: left; padding: .5rem .75rem; background: var(--bg);
                   color: var(--muted); font-weight: 600; border-bottom: 1px solid var(--border); }
.report-table td { padding: .4rem .75rem; border-bottom: 1px solid var(--border); vertical-align: middle; }
.report-table tr:last-child td { border-bottom: none; }
.report-table tr:hover td { background: rgba(79,142,247,.06); }
.bar-wrap { display: flex; align-items: center; gap: .5rem; min-width: 120px; }
.bar { border-radius: 3px; min-width: 2px; transition: width .3s; }
.bar-label { font-size: .8rem; color: var(--muted); white-space: nowrap; }
.pass { color: var(--pass); }
.fail { color: var(--fail); }
.warn { color: var(--warn); }
"""

_JS = """
function showTab(id) {
  document.querySelectorAll('.tab-panel').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).style.display = 'block';
  document.querySelector('[onclick="showTab(\\''+id+'\\')"]').classList.add('active');
}
"""


def render_html_report(
    ep: ExplainParallelReport,
    reports: list[CompareReport] | None = None,
    files: list[Path] | None = None,
    title: str = "DDS Interoperability – Analysis Report",
) -> str:
    """Render a complete self-contained HTML page."""

    tabs_btns: list[str] = []
    tabs_panels: list[str] = []

    # One tab per parallel group
    for i, grp in enumerate(ep.groups):
        tab_id = f"tab_par{grp.parallel_count}"
        label = f"par{grp.parallel_count} ({grp.run_count} runs)"
        tabs_btns.append(_tab_btn(tab_id, label, i == 0))
        tabs_panels.append(_tab_panel(tab_id, _render_group_tab(grp), i == 0))

    # Comparisons tab
    if reports and files:
        tabs_btns.append(_tab_btn("tab_compare", "Run Comparisons"))
        tabs_panels.append(_tab_panel("tab_compare", _render_compare_tab(reports, files)))

    # Ungrouped files note
    if ep.ungrouped_files:
        note = (
            f'<div class="card"><p style="color:var(--warn)">'
            f'{len(ep.ungrouped_files)} file(s) without parallel-count metadata excluded.</p></div>'
        )
        tabs_btns.append(_tab_btn("tab_ungrouped", "Excluded files"))
        tabs_panels.append(_tab_panel("tab_ungrouped", note))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>
<div class="header">
  <h1>{_esc(title)}</h1>
  <p class="subtitle">9×9 publish/subscribe interoperability test suite — grouped by parallel-run count, normalised per run</p>
</div>
<div class="tabs">{''.join(tabs_btns)}</div>
{''.join(tabs_panels)}
<script>{_JS}</script>
</body>
</html>"""
    return html


# ── CLI entry-point ───────────────────────────────────────────────────────────

def generate_html_report(
    files: list[Path],
    reports: list[CompareReport] | None = None,
    output_dir: Path | None = None,
) -> Path | None:
    """Build ExplainParallelReport from files, render HTML, save."""
    if not files:
        print("No XML files for HTML report.", file=sys.stderr)
        return None

    ep = build_explain_parallel_report(files)
    html = render_html_report(ep, reports=reports, files=files)

    dest_dir = output_dir or files[0].parent
    output_path = dest_dir / "report.html"
    try:
        output_path.write_text(html, encoding="utf-8")
        print(f"HTML report written to: {output_path.name}")
        return output_path
    except OSError as error:
        print(f"Error writing HTML report: {error}", file=sys.stderr)
        return None
