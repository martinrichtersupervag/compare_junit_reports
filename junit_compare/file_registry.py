"""Správa souborů – rozpoznání formátu názvů, řazení, výběr."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Nový formát: junit_interoperability_report[-_]DDMMYYYY-HHmm-parNN[-XXXXsec].xml
_NEW_FNAME_RE = re.compile(
    r"[-_](\d{2})(\d{2})(\d{4})-(\d{4})-par(\d+)(?:-(\d+)sec)?"
)


def parse_filename_meta(path: Path) -> dict[str, Any] | None:
    """Vrátí metadata z nového formátu názvu souboru, nebo None.

    Vrácený dict obsahuje klíče:
      date        – DDMMYYYY jako řetězec
      time        – HHmm jako řetězec
      parallel    – počet paralelních běhů (int)
      duration_sec – trvání v sekundách (int)
      sort_key    – YYYYMMDD-HHmm (pro chronologické řazení)
    """
    m = _NEW_FNAME_RE.search(path.stem)
    if not m:
        return None
    day, month, year, hhmm, parallel, duration = m.groups()
    return {
        "date": f"{day}{month}{year}",
        "time": hhmm,
        "parallel": int(parallel),
        "duration_sec": int(duration) if duration else 0,
        "sort_key": f"{year}{month}{day}-{hhmm}",
    }


def _file_sort_key(path: Path) -> tuple[str, str]:
    meta = parse_filename_meta(path)
    if meta:
        return (meta["sort_key"], path.name)
    # Fallback na starý formát
    match = re.search(r"(\d{4}-\d{2}-\d{2}-\d{2}_\d{2}_\d{2})", path.stem)
    return (match.group(1), path.name) if match else (path.name, "")


def report_label(path: str) -> str:
    """Krátký label pro výpis (datum+čas z názvu souboru)."""
    p = Path(path)
    meta = parse_filename_meta(p)
    if meta:
        return f"{meta['date']}-{meta['time']}"
    filename = p.stem
    match = re.search(r"(\d{4}-\d{2}-\d{2}-\d{2}_\d{2}_\d{2})$", filename)
    return match.group(1) if match else filename


# backward-compatible alias
_report_label = report_label


def choose_all_files(directory: Path) -> list[Path]:
    """Vrátí všechny junit_*.xml soubory v adresáři, chronologicky."""
    return sorted(directory.glob("junit_*.xml"), key=_file_sort_key)


def choose_files(directory: Path) -> tuple[Path, Path]:
    """Vrátí dva nejnovější soubory."""
    files = choose_all_files(directory)
    if len(files) < 2:
        raise ValueError(f"Need at least two junit_*.xml files in {directory}")
    return files[-2], files[-1]
