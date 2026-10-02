# DDS Interoperability – Defect Taxonomy and Analysis Notes

> Generated from real test data: 10 × `junit_interoperability_report-*-par16-*.xml`
> covering the 9×9 publish/subscribe matrix of DDS vendor implementations.
> Each testcase result contains a structured HTML table with `Expected Code` and
> `Code Produced` per participant role (Publisher_1, Subscriber_1, …).

---

## How the result table works

Every non-passing testcase carries a `message` attribute on its `<failure>` or
`<skipped>` XML element. The message contains an HTML table:

```html
<table>
  <tr><th/><th>Expected Code</th><th>Code Produced</th></tr>
  <tr><th>Publisher_1</th><th>INCOMPATIBLE_QOS</th><th>OK</th></tr>
  <tr><th>Subscriber_1</th><th>INCOMPATIBLE_QOS</th><th>INCOMPATIBLE_QOS</th></tr>
</table>
```

The **test passes** when *every role's* `Code Produced` matches its `Expected Code`.
The **XML tag** (`<failure>` vs `<skipped>`) encodes the framework's verdict, not
necessarily the semantic result — see anomalies below.

---

## All result codes observed

| Code | Count (3 files) | Meaning |
|------|---------------:|---------|
| `OK` | 45 089 | Participant behaved as expected |
| `INCOMPATIBLE_QOS` | 25 689 | QoS policies are mutually incompatible |
| `SUB_UNSUPPORTED_FEATURE` | 3 969 | Subscriber's vendor does not implement this feature |
| `PUB_UNSUPPORTED_FEATURE` | 3 753 | Publisher's vendor does not implement this feature |
| `DATA_NOT_CORRECT` | 2 864 | Data received but content wrong |
| `DATA_NOT_RECEIVED` | 1 787 | Expected data never arrived |
| `READER_NOT_MATCHED` | 1 085 | Writer and reader did not discover each other |
| `RECEIVING_FROM_ONE` | 746 | Received from only one of multiple publishers |
| `RECEIVING_FROM_BOTH` | 694 | Received from both when only one was expected |
| `DEADLINE_MISSED` | 677 | Deadline QoS violated |
| `ORDERED_ACCESS_INSTANCE` | 490 | Ordered-access by instance violated |
| `ORDERED_ACCESS_TOPIC` | 485 | Ordered-access by topic violated |
| `DATA_NOT_SENT` | 47 | Writer failed to send data |
| `READER_NOT_CREATED` | 9 | DataReader creation failed |
| `TOPIC_NOT_CREATED` | 1 | Topic creation failed |
| `WRITER_NOT_CREATED` | 1 | DataWriter creation failed |

---

## Defect taxonomy (per testcase)

The classification is derived from parsing the per-role `(expected, produced)` pairs.

### Category 1 — `passed`
*Test ran and every role matched its expected outcome.*

The `<testcase>` has no child `<failure>` / `<skipped>` / `<error>` element, **or**
all roles satisfy `expected == produced`.

> **Includes the case where `expected=INCOMPATIBLE_QOS` and `produced=INCOMPATIBLE_QOS`**
> with the `<skipped>` tag — this is correct, intended behaviour.  
> These should **not** be counted as skipped; they are semantically passing.

---

### Category 2 — `skipped_unsupported`
*Vendor does not implement the tested feature — test was never meaningfully run.*

**Rule:** `<skipped>` AND any role has `produced ∈ {SUB_UNSUPPORTED_FEATURE, PUB_UNSUPPORTED_FEATURE}`

Count (1 file): **2 037 testcases**

> This is the primary "not run" signal. The participant reported that it cannot
> execute the test because the feature is not implemented.
> These must be excluded from flaky and failure rate calculations.

---

### Category 3 — `failure_qos_unexpected`
*Vendor reports QoS incompatibility where it should not.*

**Rule:** `<failure>` AND any role has `expected ≠ INCOMPATIBLE_QOS` but `produced = INCOMPATIBLE_QOS`

Count (1 file): **3 320 testcases** (largest failure category)

Subcases from real data:

| expected | produced | Interpretation |
|----------|----------|----------------|
| `OK` | `INCOMPATIBLE_QOS` | Vendor refuses connection that should work |
| `DATA_NOT_RECEIVED` | `INCOMPATIBLE_QOS` | Expected timeout, got QoS rejection instead |
| `READER_NOT_MATCHED` | `INCOMPATIBLE_QOS` | Expected discovery failure, got QoS rejection |
| `RECEIVING_FROM_ONE/BOTH` | `INCOMPATIBLE_QOS` | Expected partial receive, got QoS rejection |
| `DEADLINE_MISSED` | `INCOMPATIBLE_QOS` | Expected deadline violation, got QoS rejection |
| `ORDERED_ACCESS_*` | `INCOMPATIBLE_QOS` | Expected ordering result, got QoS rejection |

---

### Category 4 — `failure_false_pass`
*Vendor passes a test that is supposed to demonstrate a QoS violation or isolation.*

**Rule:** `<failure>` AND any role has `expected ≠ OK` (e.g. `INCOMPATIBLE_QOS`, `READER_NOT_MATCHED`, `DATA_NOT_RECEIVED`) but `produced = OK`

Count (1 file): **991 testcases**

> This is a real interoperability defect: the vendor successfully communicated
> when the test expects the communication to fail. Classic example:
> Publisher expected `INCOMPATIBLE_QOS`, produced `OK` — vendor ignored the QoS constraint.

---

### Category 5 — `failure_data`
*Test ran, connection established, but data quality wrong.*

**Rule:** `<failure>` AND dominant mismatch produced ∈ `{DATA_NOT_CORRECT, DATA_NOT_RECEIVED, DATA_NOT_SENT}`

Count (1 file): **613 testcases**

| produced | Count | Meaning |
|----------|------:|---------|
| `DATA_NOT_CORRECT` | 515 | Content integrity failure |
| `DATA_NOT_RECEIVED` | 98 | Delivery failure |
| `DATA_NOT_SENT` | 16 | Writer-side send failure |

---

### Category 6 — `failure_ordering`
*QoS ordering or timing semantics violated.*

**Rule:** `<failure>` AND dominant produced ∈ `{ORDERED_ACCESS_INSTANCE, ORDERED_ACCESS_TOPIC, RECEIVING_FROM_ONE, RECEIVING_FROM_BOTH, DEADLINE_MISSED}`

Count (1 file): **6 testcases** (rare but semantically important)

---

### Category 7 — `failure_infrastructure`
*Test framework or DDS infrastructure could not initialize.*

**Rule:** `<failure>` AND any produced ∈ `{READER_NOT_CREATED, WRITER_NOT_CREATED, TOPIC_NOT_CREATED, READER_NOT_MATCHED}`

Count (1 file): **42 testcases**

> These are not interoperability defects — they indicate environment or
> configuration problems during the test run.

---

### Category 8 — `skipped_other`
*Test was skipped for an unclassified reason.*

**Rule:** `<skipped>` AND none of the above patterns match.

Includes cases like `skipped | INCOMPATIBLE_QOS → INCOMPATIBLE_QOS` where the
expected QoS mismatch was correctly detected, but the framework tagged it as skipped
(likely because the vendor returned a vendor-specific "unsupported" code instead of
standard INCOMPATIBLE_QOS).

---

### Category 9 — `error`
*Test framework raised a system-level exception.*

**Rule:** `<error>` XML tag present.

---

## Summary: status reclassification table — measured counts (1 file, 8 505 testcases)

| New status | Count | % | Old status | Key rule |
|---|---:|---:|---|---|
| `passed` | 1 479 | 17.4 % | passed | no child element |
| `passed_as_skipped` | 0\* | — | skipped | `<skipped>` with all `expected==produced` |
| `skipped_unsupported` | 2 037 | 24.0 % | skipped | any role produced `*_UNSUPPORTED_FEATURE` |
| `skipped_other` | 0\* | — | skipped | other skipped patterns |
| `failure_qos_unexpected` | 3 320 | 39.0 % | failure | dominant produced = `INCOMPATIBLE_QOS` |
| `failure_false_pass` | 991 | 11.7 % | failure | dominant produced = `OK` |
| `failure_data` | 629 | 7.4 % | failure | dominant produced ∈ data error codes |
| `failure_infrastructure` | 43 | 0.5 % | failure | produced ∈ `*_NOT_CREATED`, `READER_NOT_MATCHED` |
| `failure_ordering` | 6 | 0.1 % | failure | dominant produced ∈ ordering/timing codes |
| `error` | 0 | — | error | `<error>` tag |

\* `passed_as_skipped` and `skipped_other` may be 0 in this dataset because all
skipped testcases have at least one `*_UNSUPPORTED_FEATURE` produced code.

> **Key insight:** Of the 8 505 testcases, only **1 479 (17.4%)** truly passed.
> **24.0%** were never run (vendor doesn't support the feature).
> The remaining **58.6%** are genuine failures — dominated by unexpected QoS
> incompatibilities (**39.0%**) and false passes (**11.7%**).

---

## Impact on flaky analysis

With the refined status model, **flakiness detection changes significantly**:

- `skipped_unsupported` must be **excluded** from flaky detection
  (a vendor that doesn't support a feature will consistently skip it — not flaky)
- `passed` (reclassified from `<skipped>`) must be **included** in flaky detection
- A test oscillating between `failure_qos_unexpected` and `failure_false_pass`
  is a **different kind of flakiness** than one oscillating between `passed` and `failure_data`

---

## Anomalies found

### A — `<skipped>` with `expected == produced` (all roles)
Occurs 478+ times per file. The vendor correctly detected the expected QoS
incompatibility, but returned `INCOMPATIBLE_QOS` via a `<skipped>` element.  
**Verdict:** Should be reclassified as `passed`.

### B — `<failure>` with mixed-role results
Most failures are multi-role and have at least one role where `expected == produced`
and another where it does not. The dominant mismatch type drives the category.  
**Example:** Publisher=`INCOMPATIBLE_QOS→OK` (false pass), Subscriber=`INCOMPATIBLE_QOS→INCOMPATIBLE_QOS` (ok).

### C — `skipped` with `INCOMPATIBLE_QOS → OK`
411 per-role occurrences: the test was skipped but the vendor actually
communicated successfully where it was not expected to.  
**Verdict:** Suspicious — may indicate a vendor bug masked by the skip.

### D — `failure` with `expected=DATA_NOT_RECEIVED, produced=INCOMPATIBLE_QOS`
The test expects a delivery timeout (latency/deadline behavior), but the vendor
rejects the connection at the QoS level instead. Both are failures, but for
different reasons — the QoS rejection prevents the delivery scenario from even starting.

---

## Implementation plan

Changes to `junit_compare/`:

1. **`loader.py`** — parse the `message` HTML table into structured
   `(role, expected, produced)` tuples; expose `outcome_rows` on `TestResult`
2. **`report_data.py`** — add `RichStatus` enum with all categories above;
   extend `StatusSummaryRow` to track counts per `RichStatus`
3. **`analyzer.py`** — `classify_outcome()` function mapping
   `(xml_tag, rows)` → `RichStatus`
4. **`renderer.py` / `html_report.py`** — add rich-status breakdowns to output
