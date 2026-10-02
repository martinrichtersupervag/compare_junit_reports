"""Analytické funkce – srovnání reportů, agregace statistik."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models import TestResult, _test_label, _key_label
from .loader import load_results
from .report_data import (
    ChangedTest,
    CompareReport,
    StatusSummaryRow,
    FlakyTestRow,
    ParallelGroupReport,
    ExplainParallelReport,
)
from .file_registry import parse_filename_meta


# ── srovnání dvou souborů ─────────────────────────────────────────────────────

def compare(
    first: Path,
    second: Path,
    include_times: bool = False,
    include_details: bool = False,
) -> CompareReport:
    """Srovná dva JUnit XML soubory a vrátí CompareReport."""
    first_summary, first_results = load_results(first)
    second_summary, second_results = load_results(second)

    added = sorted(set(second_results) - set(first_results), key=str)
    removed = sorted(set(first_results) - set(second_results), key=str)
    changed: list[ChangedTest] = []

    for key in sorted(set(first_results) & set(second_results), key=str):
        old = first_results[key]
        new = second_results[key]
        differences: dict[str, dict[str, str]] = {}
        fields: tuple[str, ...] = ("status",)
        if include_details:
            fields += ("detail",)
        if include_times:
            fields += ("time",)
        for field in fields:
            if getattr(old, field) != getattr(new, field):
                differences[field] = {
                    "first": getattr(old, field),
                    "second": getattr(new, field),
                }
        if differences:
            changed.append(ChangedTest(test=_test_label(new), differences=differences))

    return CompareReport(
        first_file=str(first),
        second_file=str(second),
        first_summary=first_summary,
        second_summary=second_summary,
        first_count=len(first_results),
        second_count=len(second_results),
        added=[_key_label(key) for key in added],
        removed=[_key_label(key) for key in removed],
        changed=changed,
    )


# ── agregace napříč více soubory ──────────────────────────────────────────────

def _aggregate_statuses(files: list[Path]) -> dict[str, StatusSummaryRow]:
    """Vnitřní agregace – vrátí dict label -> StatusSummaryRow."""
    totals: dict[str, StatusSummaryRow] = {}
    for path in files:
        _, results = load_results(path)
        for result in results.values():
            label = _test_label(result)
            if label not in totals:
                totals[label] = StatusSummaryRow(label=label)
            row = totals[label]
            if result.status == "passed":
                row.passed += 1
            elif result.status == "failure":
                row.failure += 1
            elif result.status == "error":
                row.error += 1
            elif result.status == "skipped":
                row.skipped += 1
    return totals


def summarize_test_statuses(files: list[Path]) -> list[tuple[str, dict[str, int]]]:
    """Vrátí seznam (label, counts) pouze pro testy s alespoň jedním selháním.

    Zachovává původní dict formát pro zpětnou kompatibilitu.
    """
    totals = _aggregate_statuses(files)
    rows = [
        (label, {"passed": r.passed, "failure": r.failure,
                 "error": r.error, "skipped": r.skipped})
        for label, r in totals.items()
        if r.total_fail > 0
    ]
    return sorted(rows, key=lambda item: (-item[1]["failure"] - item[1]["error"], item[0]))


def summarize_all_statuses(files: list[Path]) -> list[tuple[str, dict[str, int]]]:
    """Jako summarize_test_statuses, ale vrátí i vždy-procházející testy.

    Potřebné pro detekci flaky testů.
    """
    totals = _aggregate_statuses(files)
    return [
        (label, {"passed": r.passed, "failure": r.failure,
                 "error": r.error, "skipped": r.skipped})
        for label, r in sorted(totals.items())
    ]


def _repeated_change_tests(reports: list[CompareReport]) -> dict[str, int]:
    """Testy, které změnily stav ve více než jednom srovnání."""
    counts: dict[str, int] = {}
    for report in reports:
        for item in report.changed:
            if "status" not in item.differences:
                continue
            counts[item.test] = counts.get(item.test, 0) + 1
    return {test: count for test, count in sorted(counts.items()) if count > 1}


# ── analýza paralelních skupin ────────────────────────────────────────────────

def _extract_pub_sub(label: str) -> tuple[str, str] | None:
    m = re.match(r"\s*([^-]+-[^-]+)---([^-]+-[^\s]+)\s+/", label)
    return (m.group(1), m.group(2)) if m else None


def _extract_feature(label: str) -> str:
    m = re.search(r"/ rtps_test_suite_\d+_Test_([A-Za-z0-9]+)_\d+", label)
    return m.group(1) if m else "Ostatní"


def build_parallel_group_report(
    parallel_count: int,
    group_files: list[Path],
) -> ParallelGroupReport:
    """Postaví ParallelGroupReport pro jednu skupinu souborů se stejným par-count."""
    run_count = len(group_files)

    status_summary = summarize_test_statuses(group_files)   # jen failing
    all_summary = summarize_all_statuses(group_files)       # všechny

    total_unique = len(all_summary)

    # flaky
    flaky_rows: list[FlakyTestRow] = []
    for label, counts in all_summary:
        pass_n = counts.get("passed", 0)
        fail_n = counts.get("failure", 0) + counts.get("error", 0)
        if pass_n > 0 and fail_n > 0:
            flaky_rows.append(FlakyTestRow(label=label, pass_count=pass_n, fail_count=fail_n))
    flaky_rows.sort(key=lambda r: -(r.pass_count + r.fail_count))

    flaky_pub: dict[str, int] = {}
    flaky_sub: dict[str, int] = {}
    flaky_pub_tests: dict[str, int] = {}
    flaky_sub_tests: dict[str, int] = {}
    flaky_feat: dict[str, int] = {}
    for row in flaky_rows:
        ps = _extract_pub_sub(row.label)
        if ps:
            pub, sub = ps
            flaky_pub[pub] = flaky_pub.get(pub, 0) + row.fail_count
            flaky_sub[sub] = flaky_sub.get(sub, 0) + row.fail_count
            flaky_pub_tests[pub] = flaky_pub_tests.get(pub, 0) + 1
            flaky_sub_tests[sub] = flaky_sub_tests.get(sub, 0) + 1
        feat = _extract_feature(row.label)
        flaky_feat[feat] = flaky_feat.get(feat, 0) + row.fail_count

    # celkové fail / pass / skip
    total_fail_raw = sum(c.get("failure", 0) + c.get("error", 0) for _, c in status_summary)
    total_pass_raw = sum(c.get("passed", 0) for _, c in all_summary)
    total_skip_raw = sum(c.get("skipped", 0) for _, c in all_summary)

    # QoS + pub/sub celkové
    feature_fails: dict[str, int] = {}
    pub_fails: dict[str, int] = {}
    sub_fails: dict[str, int] = {}
    for label, counts in status_summary:
        total_fail = counts.get("failure", 0) + counts.get("error", 0)
        feature_fails[_extract_feature(label)] = feature_fails.get(_extract_feature(label), 0) + total_fail
        ps = _extract_pub_sub(label)
        if ps:
            pub, sub = ps
            pub_fails[pub] = pub_fails.get(pub, 0) + total_fail
            sub_fails[sub] = sub_fails.get(sub, 0) + total_fail

    return ParallelGroupReport(
        parallel_count=parallel_count,
        run_count=run_count,
        file_paths=[str(p) for p in group_files],
        total_fail_raw=total_fail_raw,
        total_pass_raw=total_pass_raw,
        total_skip_raw=total_skip_raw,
        total_unique_tests=total_unique,
        flaky_tests=flaky_rows,
        flaky_pub=flaky_pub,
        flaky_sub=flaky_sub,
        flaky_pub_test_count=flaky_pub_tests,
        flaky_sub_test_count=flaky_sub_tests,
        flaky_feat=flaky_feat,
        feature_fails=feature_fails,
        pub_fails=pub_fails,
        sub_fails=sub_fails,
    )


def build_explain_parallel_report(files: list[Path]) -> ExplainParallelReport:
    """Seskupí soubory dle par-count a vrátí ExplainParallelReport."""
    groups: dict[int, list[Path]] = {}
    ungrouped: list[Path] = []
    for path in files:
        meta = parse_filename_meta(path)
        if meta:
            groups.setdefault(meta["parallel"], []).append(path)
        else:
            ungrouped.append(path)

    group_reports = [
        build_parallel_group_report(par_count, group_files)
        for par_count, group_files in sorted(groups.items())
    ]
    return ExplainParallelReport(
        groups=group_reports,
        ungrouped_files=[str(p) for p in ungrouped],
    )
