"""Datové struktury pro výstupy analýzy.

Každá dataclass odpovídá jednomu "pohledu" na data.
Renderer ani explain moduly neprodukují text přímo –
nejprve naplní tyto struktury, teprve pak renderer generuje výstup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── výsledky jednoho srovnání dvou reportů ────────────────────────────────────

@dataclass
class ChangedTest:
    """Jeden testcase, jehož výsledek se mezi dvěma reporty lišil."""
    test: str
    differences: dict[str, dict[str, str]]   # field -> {first, second}


@dataclass
class CompareReport:
    """Výstup funkce compare() – srovnání dvou XML souborů."""
    first_file: str
    second_file: str
    first_summary: dict[str, str]
    second_summary: dict[str, str]
    first_count: int
    second_count: int
    added: list[str]
    removed: list[str]
    changed: list[ChangedTest]

    def to_dict(self) -> dict[str, Any]:
        """Zpětná kompatibilita – vrátí původní dict formát."""
        return {
            "first": {"file": self.first_file, "summary": self.first_summary},
            "second": {"file": self.second_file, "summary": self.second_summary},
            "counts": {"first": self.first_count, "second": self.second_count},
            "added": self.added,
            "removed": self.removed,
            "changed": [
                {"test": c.test, "differences": c.differences}
                for c in self.changed
            ],
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "CompareReport":
        return CompareReport(
            first_file=d["first"]["file"],
            second_file=d["second"]["file"],
            first_summary=d["first"]["summary"],
            second_summary=d["second"]["summary"],
            first_count=d["counts"]["first"],
            second_count=d["counts"]["second"],
            added=d["added"],
            removed=d["removed"],
            changed=[
                ChangedTest(test=c["test"], differences=c["differences"])
                for c in d["changed"]
            ],
        )


# ── agregované statistiky napříč více soubory ─────────────────────────────────

@dataclass
class StatusSummaryRow:
    """Počty výsledků jednoho testcase agregované přes N souborů."""
    label: str
    passed: int = 0
    failure: int = 0
    error: int = 0
    skipped: int = 0

    @property
    def total_fail(self) -> int:
        return self.failure + self.error

    @property
    def is_flaky(self) -> bool:
        """Flaky = v některých bězích prošel, v jiných selhal."""
        return self.passed > 0 and self.total_fail > 0

    @property
    def fail_rate(self) -> float:
        total = self.passed + self.total_fail
        return self.total_fail / total * 100 if total else 0.0


# ── explain report (časová řada srovnání) ─────────────────────────────────────

@dataclass
class ExplainReport:
    """Agregovaný výsledek generate_explanation()."""
    first_label: str
    last_label: str
    comparison_count: int
    xml_file_count: int

    total_unique_tests: int
    perm_pass_count: int
    perm_fail_count: int
    mixed_count: int

    truly_flaky: list[tuple[str, int]]     # (test_label, change_count)
    partially_flaky: list[tuple[str, int]]

    feature_fails: dict[str, int]          # feature -> raw fail count
    pub_fails: dict[str, int]              # publisher -> raw fail count
    sub_fails: dict[str, int]              # subscriber -> raw fail count


# ── explain_parallel report ───────────────────────────────────────────────────

@dataclass
class FlakyTestRow:
    """Jeden flaky test v rámci skupiny paralelních běhů."""
    label: str
    pass_count: int
    fail_count: int

    @property
    def fail_rate(self) -> float:
        total = self.pass_count + self.fail_count
        return self.fail_count / total * 100 if total else 0.0


@dataclass
class ParallelGroupReport:
    """Statistiky pro jednu skupinu souborů se stejným par-count."""
    parallel_count: int
    run_count: int                         # počet XML souborů v skupině
    file_paths: list[str]

    # celkové počty (raw = součet přes všechny soubory skupiny)
    total_fail_raw: int
    total_pass_raw: int
    total_skip_raw: int
    total_unique_tests: int

    # flaky
    flaky_tests: list[FlakyTestRow]        # seřazeno: nejvíce oscilující první
    flaky_pub: dict[str, int]             # publisher -> raw flaky fail count
    flaky_sub: dict[str, int]             # subscriber -> raw flaky fail count
    flaky_pub_test_count: dict[str, int]  # publisher -> počet distinct flaky testů
    flaky_sub_test_count: dict[str, int]  # subscriber -> počet distinct flaky testů
    flaky_feat: dict[str, int]            # QoS feature -> raw flaky fail count

    # celková chybovost (raw)
    feature_fails: dict[str, int]
    pub_fails: dict[str, int]
    sub_fails: dict[str, int]

    def norm(self, value: int) -> float:
        """Normalizuje raw hodnotu na průměr na jeden běh."""
        return value / self.run_count if self.run_count else 0.0

    @property
    def flaky_count(self) -> int:
        return len(self.flaky_tests)

    @property
    def flaky_pct(self) -> float:
        return self.flaky_count / self.total_unique_tests * 100 if self.total_unique_tests else 0.0


@dataclass
class ExplainParallelReport:
    """Výstup generate_explain_parallel() – skupiny dle par-count."""
    groups: list[ParallelGroupReport]      # seřazeno dle parallel_count
    ungrouped_files: list[str]             # soubory bez nového formátu názvu
