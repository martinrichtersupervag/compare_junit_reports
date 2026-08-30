# DDS Interoperability Report Comparator

`compare_junit_reports.py` compares JUnit XML reports produced by DDS vendor interoperability tests. It compares testcase presence and pass/fail/error status while ignoring runtime and verbose communication details by default.

## Requirements

- Python 3.9 or newer
- No external packages are required

## Basic Usage

Run the script from this directory:

```powershell
python compare_junit_reports.py
```

Without XML arguments, the script selects the two newest `junit_*.xml` files and compares them.

To compare specific reports:

```powershell
python compare_junit_reports.py first.xml second.xml
```

The first file is treated as the earlier run and the second file as the later run.

## Output Modes

Concise summary:

```powershell
python compare_junit_reports.py --simple
```

Show changed testcase outcomes as two-sided differences:

```powershell
python compare_junit_reports.py --show-differences
```

The output looks like this:

```text
CHANGED: vendor_a---vendor_b / testcase_name
- first: passed
+ second: failure
```

Machine-readable JSON:

```powershell
python compare_junit_reports.py --json
```

Default detailed report:

```powershell
python compare_junit_reports.py
```

## Compare All Reports

Compare every XML report with the next chronological report:

```powershell
python compare_junit_reports.py --compare-all --simple
```

For four reports, this creates comparisons for:

```text
report1 -> report2
report2 -> report3
report3 -> report4
```

`--compare-all` cannot be combined with explicit XML file arguments.

## Optional Comparison Details

Include testcase runtime changes:

```powershell
python compare_junit_reports.py --include-times
```

Include verbose failure and error details from the XML:

```powershell
python compare_junit_reports.py --include-details
```

These options can be combined with the output modes and `--compare-all`.

## Choosing Another Folder

Use `--directory` when the XML files are in another folder:

```powershell
python compare_junit_reports.py --directory path\to\reports --simple
```

The directory must contain at least two files matching `junit_*.xml`.

## Saved Output Files

Every successful comparison is printed to the console and saved as a text file in the directory of the first XML report. The filename format is:

```text
{mode}_{timestamp1}_{timestamp2}.txt
```

Examples:

```text
simple_2026-08-30-06_18_47_2026-08-30-16_15_12.txt
show-differences_2026-08-30-06_18_47_2026-08-30-16_15_12.txt
json_2026-08-30-06_18_47_2026-08-30-16_15_12.txt
```

The timestamps are extracted from the source filenames. Existing output `.txt` files are not considered XML input because only `junit_*.xml` files are selected.
