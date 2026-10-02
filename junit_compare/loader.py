"""Načítání XML JUnit reportů."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .models import TestResult, _test_label


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
