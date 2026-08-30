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


def choose_all_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("junit_*.xml"), key=lambda path: path.stat().st_mtime)


def print_report(report: dict[str, Any], include_times: bool) -> None:
    first = Path(report["first"]["file"]).name
    second = Path(report["second"]["file"]).name
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
    print(
        f"Differences: {_report_label(report['first']['file'])} -> "
        f"{_report_label(report['second']['file'])}"
    )
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
        print(f"CHANGED: {item['test']}")
        print(f"- first: {status['first']}")
        print(f"+ second: {status['second']}")


def output_filename(first: Path, second: Path, mode: str) -> Path:
    return first.parent / f"{mode}_{_report_label(str(first))}_{_report_label(str(second))}.txt"


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
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", nargs="?", type=Path, help="Earlier XML report")
    parser.add_argument("second", nargs="?", type=Path, help="Later XML report")
    parser.add_argument("--directory", type=Path, help="Directory from which to select the two newest reports")
    parser.add_argument("--include-times", action="store_true", help="Report testcase runtime changes")
    parser.add_argument("--include-details", action="store_true", help="Compare verbose failure/error details")
    parser.add_argument("--simple", action="store_true", help="Print a concise comparison summary")
    parser.add_argument("--show-differences", action="store_true", help="Show changed testcase outcomes as two-sided differences")
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
            pairs = zip(files, files[1:])
        elif args.first or args.second:
            if not (args.first and args.second):
                parser.error("provide both first and second XML reports")
            pairs = [(args.first, args.second)]
        else:
            pairs = [choose_files(args.directory or Path(__file__).parent)]
        for first, second in pairs:
            report = compare(first, second, args.include_times, args.include_details)
            if render_and_save(report, first, second, args):
                return 1
    except (ET.ParseError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())