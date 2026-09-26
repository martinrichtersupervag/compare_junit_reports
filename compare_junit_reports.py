"""Compare two JUnit interoperability reports.

With no file arguments, the two newest ``junit_*.xml`` files in the script's
directory are compared.
"""

from __future__ import annotations

import argparse
import io
import difflib
import json
from contextlib import redirect_stdout
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TestResult:
    suite: str
    name: str
    attributes: tuple[tuple[str, str], ...]
    status: str
    detail: str
    time: str

    @property
    def key(self) -> tuple[str, str, tuple[tuple[str, str], ...]]:
        return self.suite, self.name, self.attributes


def load_results(path: Path) -> tuple[dict[str, str], dict[Any, TestResult]]:
    root = ET.parse(path).getroot()
    summary = dict(root.attrib)
    results: dict[Any, TestResult] = {}

    for suite in root.findall(".//testsuite"):
        suite_name = suite.get("name", "")
        for case in suite.findall("testcase"):
            attributes = tuple(
                sorted(
                    (key, value)
                    for key, value in case.attrib.items()
                    if key not in {"name", "time"}
                )
            )
            failure = case.find("failure")
            error = case.find("error")
            skipped = case.find("skipped")
            if failure is not None:
                status = "failure"
                detail = _node_detail(failure)
            elif error is not None:
                status = "error"
                detail = _node_detail(error)
            elif skipped is not None:
                status = "skipped"
                detail = _node_detail(skipped)
            else:
                status = "passed"
                detail = ""

            result = TestResult(
                suite=suite_name,
                name=case.get("name", ""),
                attributes=attributes,
                status=status,
                detail=detail,
                time=case.get("time", ""),
            )
            if result.key in results:
                raise ValueError(f"Duplicate testcase key in {path}: {result.key}")
            results[result.key] = result

    return summary, results


def _node_detail(node: ET.Element) -> str:
    text = "".join(node.itertext()).strip()
    message = node.get("message", "").strip()
    return f"{message}\n{text}".strip() if message and text else message or text


def compare(
    first: Path,
    second: Path,
    include_times: bool = False,
    include_details: bool = False,
) -> dict[str, Any]:
    first_summary, first_results = load_results(first)
    second_summary, second_results = load_results(second)
    added = sorted(set(second_results) - set(first_results), key=str)
    removed = sorted(set(first_results) - set(second_results), key=str)
    changed = []

    for key in sorted(set(first_results) & set(second_results), key=str):
        old = first_results[key]
        new = second_results[key]
        differences = {}
        fields = ("status",)
        if include_details:
            fields += ("detail",)
        if include_times:
            fields += ("time",)
        for field in fields:
            if getattr(old, field) != getattr(new, field):
                differences[field] = {"first": getattr(old, field), "second": getattr(new, field)}
        if differences:
            changed.append({"test": _test_label(new), "differences": differences})

    return {
        "first": {"file": str(first), "summary": first_summary},
        "second": {"file": str(second), "summary": second_summary},
        "counts": {"first": len(first_results), "second": len(second_results)},
        "added": [_key_label(key) for key in added],
        "removed": [_key_label(key) for key in removed],
        "changed": changed,
    }


def _test_label(result: TestResult) -> str:
    return _key_label(result.key)


def _key_label(key: tuple[str, str, tuple[tuple[str, str], ...]]) -> str:
    suite, name, attributes = key
    config = ", ".join(f"{key}={value}" for key, value in attributes)
    return f"{suite} / {name}" + (f" [{config}]" if config else "")


def choose_files(directory: Path) -> tuple[Path, Path]:
    files = choose_all_files(directory)
    if len(files) < 2:
        raise ValueError(f"Need at least two junit_*.xml files in {directory}")
    return files[-2], files[-1]


def _file_sort_key(path: Path) -> tuple[str, str]:
    match = re.search(r"(\d{4}-\d{2}-\d{2}-\d{2}_\d{2}_\d{2})", path.stem)
    return (match.group(1), path.name) if match else (path.name, "")


def choose_all_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("junit_*.xml"), key=_file_sort_key)


def print_report(report: dict[str, Any], include_times: bool) -> None:
    first = Path(report["first"]["file"]).name
    second = Path(report["second"]["file"]).name
    print(f"##Result for: Comparing: {first} -> {second}")
    print(f"Comparing: {first} -> {second}")
    print(
        f"Cases: {report['counts']['first']} -> {report['counts']['second']} | "
        f"added: {len(report['added'])}, removed: {len(report['removed'])}, "
        f"changed: {len(report['changed'])}"
    )
    if include_times:
        print("Timing differences are included.")
    for category in ("added", "removed"):
        for label in report[category]:
            print(f"{category.upper()}: {label}")
    for item in report["changed"]:
        print(f"CHANGED: {item['test']}")
        for field, values in item["differences"].items():
            if field == "detail":
                first_detail = values["first"] or "(none)"
                second_detail = values["second"] or "(none)"
                detail_diff = difflib.unified_diff(
                    first_detail.splitlines(), second_detail.splitlines(),
                    fromfile="first", tofile="second", lineterm="",
                )
                print("  detail:")
                print("\n".join(f"    {line}" for line in detail_diff))
            else:
                print(f"  {field}: {values['first']!r} -> {values['second']!r}")


def _report_label(path: str) -> str:
    filename = Path(path).stem
    match = re.search(r"(\d{4}-\d{2}-\d{2}-\d{2}_\d{2}_\d{2})$", filename)
    return match.group(1) if match else filename


def print_simple_report(report: dict[str, Any]) -> None:
    first_label = _report_label(report["first"]["file"])
    second_label = _report_label(report["second"]["file"])
    print(f"##Result for: Comparison: {first_label} vs. {second_label}")
    testcase_count = report["counts"]["first"]
    same_count = testcase_count == report["counts"]["second"]
    status_changes = sum(
        "status" in item["differences"] for item in report["changed"]
    )
    print("Current comparison shows:")
    if same_count:
        print(f"- `{testcase_count:,}` testcases in both runs")
    else:
        print(
            f"- `{report['counts']['first']:,}` testcases in the first run and "
            f"`{report['counts']['second']:,}` in the second run"
        )
    print(f"- `{status_changes}` pass/fail status changes between runs")
    if status_changes:
        print(f"- The results for the same case differ {status_changes}x")
    else:
        print("- No diverse results in same case")
    print(
        f"- reports `{_report_label(report['first']['file'])}` vs. "
        f"`{_report_label(report['second']['file'])}`"
    )


def print_differences(report: dict[str, Any]) -> None:
    """Print changed testcase outcomes as a compact two-sided diff."""
    first_label = _report_label(report["first"]["file"])
    second_label = _report_label(report["second"]["file"])
    print(f"##Result for: Differences: {first_label} -> {second_label}")
    print(f"Differences: {first_label} -> {second_label}")
    difference_count = len(report["added"]) + len(report["removed"])
    difference_count += sum(
        "status" in item["differences"] for item in report["changed"]
    )
    if not difference_count:
        print("No testcase result differences.")
        return

    for label in report["removed"]:
        print(f"CHANGED: {label}")
        print("- first: (empty)")
        print("+ second: removed")
    for label in report["added"]:
        print(f"CHANGED: {label}")
        print("- first: removed")
        print("+ second: (empty)")
    for item in report["changed"]:
        status = item["differences"].get("status")
        if status is None:
            continue
        first_label = _report_label(report["first"]["file"])
        second_label = _report_label(report["second"]["file"])
        print(f"CHANGED: {item['test']}")
        print(f"- {first_label}: {status['first']}")
        print(f"+ {second_label}: {status['second']}")


def _repeated_change_tests(reports: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for report in reports:
        for item in report["changed"]:
            if "status" not in item["differences"]:
                continue
            counts[item["test"]] = counts.get(item["test"], 0) + 1
    return {test: count for test, count in sorted(counts.items()) if count > 1}


def summarize_test_statuses(files: list[Path]) -> list[tuple[str, dict[str, int]]]:
    totals: dict[str, dict[str, int]] = {}
    for path in files:
        _, results = load_results(path)
        for result in results.values():
            label = _test_label(result)
            bucket = totals.setdefault(label, {"passed": 0, "failure": 0, "error": 0, "skipped": 0})
            bucket[result.status] = bucket.get(result.status, 0) + 1
    return [
        (label, counts)
        for label, counts in sorted(
            totals.items(),
            key=lambda item: (
                -(item[1].get("failure", 0) + item[1].get("error", 0)),
                item[0],
            ),
        )
        if counts.get("failure", 0) or counts.get("error", 0)
    ]


def print_failure_frequency_summary(files: list[Path]) -> None:
    print("##Result for: Failure frequency across all XML reports")
    summary = summarize_test_statuses(files)
    if not summary:
        print("Failure frequency across all XML reports: none")
        return
    print("Failure frequency across all XML reports:")
    for label, counts in summary:
        total_failures = counts.get("failure", 0) + counts.get("error", 0)
        print(
            f"  {label}: passed={counts.get('passed', 0)}, failed={counts.get('failure', 0)}, "
            f"errors={counts.get('error', 0)}, skipped={counts.get('skipped', 0)}, total_failures={total_failures}"
        )


def render_compare_all(
    pairs: list[tuple[Path, Path]],
    reports: list[dict[str, Any]],
    args: argparse.Namespace,
    files: list[Path] | None = None,
) -> int:
    first = pairs[0][0]
    last = pairs[-1][1]
    status_summary = summarize_test_statuses(files or []) if files is not None else []
    if args.as_json:
        mode = "json"
        payload = {
            "comparison_count": len(reports),
            "repeat_test_locations": _repeated_change_tests(reports),
            "status_counts_across_reports": {label: counts for label, counts in status_summary},
            "comparisons": reports,
        }
        text = json.dumps(payload, indent=2)
    elif args.simple:
        mode = "simple"
        output = io.StringIO()
        with redirect_stdout(output):
            print("Current comparison shows:")
            if status_summary:
                print_failure_frequency_summary(files or [])
            repeated = _repeated_change_tests(reports)
            if repeated:
                print("##Result for: Repeated testcase changes on the same location")
            print(f"- repeated testcase changes on the same location: {len(repeated)}")
            if repeated:
                for test, count in repeated.items():
                    print(f"  - {test}: {count} comparisons")
            for report in reports:
                print_simple_report(report)
        text = output.getvalue()
    elif args.show_differences:
        mode = "show-differences"
        output = io.StringIO()
        with redirect_stdout(output):
            if files:
                print_failure_frequency_summary(files)
                print()
            repeated = _repeated_change_tests(reports)
            if repeated:
                print("##Result for: Repeated testcase changes on the same location")
                print(f"Repeated testcase changes on the same location: {len(repeated)}")
                for test, count in repeated.items():
                    print(f"  {test}: {count} comparisons")
                print()
            for report in reports:
                print_differences(report)
                print()
        text = output.getvalue()
    else:
        mode = "report"
        output = io.StringIO()
        with redirect_stdout(output):
            if files:
                print_failure_frequency_summary(files)
                print()
            repeated = _repeated_change_tests(reports)
            if repeated:
                print("##Result for: Repeated testcase changes on the same location")
                print(f"Repeated testcase changes on the same location: {len(repeated)}")
                for test, count in repeated.items():
                    print(f"  {test}: {count} comparisons")
                print()
            for report in reports:
                print_report(report, args.include_times)
                print()
        text = output.getvalue()

    print(text, end="")
    output_path = output_filename(first, last, mode)
    try:
        output_path.write_text(text, encoding="utf-8")
    except OSError as error:
        print(f"Error writing output file {output_path}: {error}", file=sys.stderr)
        return 1
    print(f"Output written to: {output_path.name}")
    generate_explanation(first, last, reports, files)
    return 0


def output_filename(first: Path, second: Path, mode: str) -> Path:
    return first.parent / f"{mode}_{_report_label(str(first))}_{_report_label(str(second))}.txt"


def generate_explanation(
    first: Path,
    last: Path,
    reports: list[dict[str, Any]],
    files: list[Path] | None = None,
) -> Path | None:
    first_label = _report_label(str(first))
    last_label = _report_label(str(last))
    output_path = output_filename(first, last, "explain")

    test_changes: dict[str, int] = {}
    for r in reports:
        for item in r.get("changed", []):
            if "status" in item.get("differences", {}):
                test = item["test"]
                test_changes[test] = test_changes.get(test, 0) + 1

    if len(reports) > 1:
        truly_flaky = [(t, c) for t, c in test_changes.items() if c >= 3]
        partially_flaky = [(t, c) for t, c in test_changes.items() if c == 2]
    else:
        truly_flaky = []
        partially_flaky = []
        if reports:
            for item in reports[0].get("changed", []):
                diff = item.get("differences", {}).get("status")
                if diff:
                    f, s = diff["first"], diff["second"]
                    if {f, s} <= {"passed", "failure", "error"}:
                        truly_flaky.append((item["test"], 1))
                    else:
                        partially_flaky.append((item["test"], 1))

    truly_flaky.sort(key=lambda x: (-x[1], x[0]))
    partially_flaky.sort(key=lambda x: (-x[1], x[0]))

    lines: list[str] = [
        "##Result for: Explanation and Analysis",
        f"Skutečně nestabilních (flaky) testů je {len(truly_flaky)}",
        f"částečně nestabilní testů je {len(partially_flaky)}",
        "",
        "=" * 80,
        "ZÁKLADNÍ PŘEHLED A STATISTIKA",
        "=" * 80,
        f"- Srovnávané období: {first_label} -> {last_label}",
        f"- Počet srovnání: {len(reports)}",
    ]

    if files:
        lines.append(f"- Počet analyzovaných XML reportů: {len(files)}")
        status_summary = summarize_test_statuses(files)
        all_test_labels: set[str] = set()
        for f in files:
            _, res = load_results(f)
            for r in res.values():
                all_test_labels.add(_test_label(r))

        total_unique_tests = len(all_test_labels)
        perm_fail = sum(
            1 for _, c in status_summary
            if c.get("passed", 0) == 0 and (c.get("failure", 0) or c.get("error", 0))
        )
        mixed = sum(
            1 for _, c in status_summary
            if c.get("passed", 0) > 0 and (c.get("failure", 0) or c.get("error", 0))
        )
        perm_pass = total_unique_tests - len(status_summary)
        pass_pct = (perm_pass / total_unique_tests * 100) if total_unique_tests else 0
        fail_pct = (perm_fail / total_unique_tests * 100) if total_unique_tests else 0
        mixed_pct = (mixed / total_unique_tests * 100) if total_unique_tests else 0

        lines.extend([
            f"- Celkový počet unikátních testů v sadách: {total_unique_tests:,}",
            f"- Trvale procházející testy (100% pass): {perm_pass:,} ({pass_pct:.1f} %)",
            f"- Trvale selhávající testy (100% fail): {perm_fail:,} ({fail_pct:.1f} %)",
            f"- Testy se střídavým výsledkem (pass i fail): {mixed:,} ({mixed_pct:.1f} %)",
        ])

    if truly_flaky:
        lines.extend([
            "",
            "=" * 80,
            "SKUTEČNĚ NESTABILNÍ (FLAKY) TESTY",
            "=" * 80,
        ])
        for t, c in truly_flaky:
            lines.append(f"  [{c}x změna stavu] {t}")

    if partially_flaky:
        lines.extend([
            "",
            "=" * 80,
            "ČÁSTEČNĚ NESTABILNÍ TESTY",
            "=" * 80,
        ])
        for t, c in partially_flaky:
            lines.append(f"  [{c}x změna stavu] {t}")

    if files:
        lines.extend([
            "",
            "=" * 80,
            "NEJČASTĚJŠÍ OBLASTI SELHÁNÍ PODLE QOS / FUNKCIONALITY",
            "=" * 80,
        ])
        feature_fails: dict[str, int] = {}
        for label, counts in status_summary:
            total_fail = counts.get("failure", 0) + counts.get("error", 0)
            m = re.search(r"/ rtps_test_suite_\d+_Test_([A-Za-z0-9]+)_\d+", label)
            feat = m.group(1) if m else "Ostatní"
            feature_fails[feat] = feature_fails.get(feat, 0) + total_fail

        for feat, count in sorted(feature_fails.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"  - {feat:20}: {count:5} selhání")

        lines.extend([
            "",
            "=" * 80,
            "CHYBOVOST DLE IMPLEMENTACÍ DDS (PUBLISHER / SUBSCRIBER)",
            "=" * 80,
        ])
        pub_fails: dict[str, int] = {}
        sub_fails: dict[str, int] = {}
        for label, counts in status_summary:
            total_fail = counts.get("failure", 0) + counts.get("error", 0)
            m = re.match(r"\s*([^-]+-[^-]+)---([^-]+-[^\s]+)\s+/", label)
            if m:
                pub, sub = m.group(1), m.group(2)
                pub_fails[pub] = pub_fails.get(pub, 0) + total_fail
                sub_fails[sub] = sub_fails.get(sub, 0) + total_fail

        lines.append("  TOP chybující Publisher:")
        for pub, count in sorted(pub_fails.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"    - {pub:25}: {count:5} chyb")
        lines.append("  TOP chybující Subscriber:")
        for sub, count in sorted(sub_fails.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"    - {sub:25}: {count:5} chyb")

    text = "\n".join(lines) + "\n"
    try:
        output_path.write_text(text, encoding="utf-8")
        print(f"Explanation written to: {output_path.name}")
        return output_path
    except OSError as error:
        print(f"Error writing explanation file {output_path}: {error}", file=sys.stderr)
        return None


def render_and_save(report: dict[str, Any], first: Path, second: Path, args: argparse.Namespace) -> int:
    if args.as_json:
        mode = "json"
        renderer = lambda: print(json.dumps(report, indent=2))
    elif args.simple:
        mode = "simple"
        renderer = lambda: print_simple_report(report)
    elif args.show_differences:
        mode = "show-differences"
        renderer = lambda: print_differences(report)
    else:
        mode = "report"
        renderer = lambda: print_report(report, args.include_times)

    output = io.StringIO()
    with redirect_stdout(output):
        renderer()
    text = output.getvalue()
    print(text, end="")
    output_path = output_filename(first, second, mode)
    try:
        output_path.write_text(text, encoding="utf-8")
    except OSError as error:
        print(f"Error writing output file {output_path}: {error}", file=sys.stderr)
        return 1
    print(f"Output written to: {output_path.name}")
    generate_explanation(first, second, [report], [first, second])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", nargs="?", type=Path, help="Earlier XML report")
    parser.add_argument("second", nargs="?", type=Path, help="Later XML report")
    parser.add_argument("--directory", type=Path, help="Directory from which to select the two newest reports")
    parser.add_argument("--include-times", action="store_true", help="Report testcase runtime changes")
    parser.add_argument("--include-details", action="store_true", help="Compare verbose failure/error details")
    parser.add_argument("--simple", action="store_true", help="Print a concise comparison summary")
    parser.add_argument(
        "--show-differences",
        "--show-difference",
        action="store_true",
        dest="show_differences",
        help="Show changed testcase outcomes as two-sided differences",
    )
    parser.add_argument("--compare-all", action="store_true", help="Compare every report with the next chronological report")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Write the comparison as JSON")
    args = parser.parse_args()

    try:
        if args.compare_all and (args.first or args.second):
            parser.error("--compare-all cannot be combined with explicit XML reports")
        if args.compare_all:
            files = choose_all_files(args.directory or Path(__file__).parent)
            if len(files) < 2:
                raise ValueError(f"Need at least two junit_*.xml files in {args.directory or Path(__file__).parent}")
            pairs = list(zip(files, files[1:]))
            reports = [
                compare(first, second, args.include_times, args.include_details)
                for first, second in pairs
            ]
            if render_compare_all(pairs, reports, args, files):
                return 1
        elif args.first or args.second:
            if not (args.first and args.second):
                parser.error("provide both first and second XML reports")
            pairs = [(args.first, args.second)]
            for first, second in pairs:
                report = compare(first, second, args.include_times, args.include_details)
                if render_and_save(report, first, second, args):
                    return 1
        else:
            first, second = choose_files(args.directory or Path(__file__).parent)
            report = compare(first, second, args.include_times, args.include_details)
            if render_and_save(report, first, second, args):
                return 1
    except (ET.ParseError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())