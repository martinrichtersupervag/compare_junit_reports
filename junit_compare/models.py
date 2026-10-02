"""Data model: TestResult and label helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
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


# ── label helpers ──────────────────────────────────────────────────────────────

def test_label(result: TestResult) -> str:
    return key_label(result.key)


def key_label(key: tuple[str, str, tuple[tuple[str, str], ...]]) -> str:
    suite, name, attributes = key
    config = ", ".join(f"{k}={v}" for k, v in attributes)
    return f"{suite} / {name}" + (f" [{config}]" if config else "")


# kept as private aliases so internal callers that use _test_label / _key_label still work
_test_label = test_label
_key_label = key_label
