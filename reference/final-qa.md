# Phase 8: Final QA — The Eight Checks

The final gate. Checks 1–3 are mechanized by ported 199-biotech validators;
checks 4–8 add the "is X actually true" layer that quote-verification alone
cannot supply. Every check produces a pass/fail + findings, recorded in
`qa/qa_report.md`. A report ships only when every check passes or its failure
is disclosed as a limitation in both the report and the QA report.

```bash
python scripts/validate_report.py        --report <run>/report/report.md
python scripts/verify_citations.py       --report <run>/report/report.md
python scripts/extract_claims.py extract --report <run>/report/report.md --dir <run>/evidence
python scripts/link_claims.py link-claims --dir <run>/evidence --run-dir <run>
python scripts/verify_claim_support.py   verify --dir <run>/evidence --strict
```

## Check 1 — Citation / quote verification

`verify_citations.py` catches fabricated citations: DOI resolution, URL
accessibility, title/year matching, hallucination patterns. Then manually
spot-check that quoted strings in the report match their `evidence.jsonl`
rows verbatim and that each `[N]` maps to the intended source via
`assign-display-numbers`. "Did the source actually say X" is verified here.

## Check 2 — Source-independence verification

For every major claim, recount the distinct `independence_group_id`s among its
cited sources (≥3 groups standard+, ≥2 quick). Re-check triage's clustering
for the specific cited sources — a manual override or late delta-wave source
may sit in the wrong group. Two cited URLs from one origin cluster
corroborate nothing.

## Check 3 — Claim-support verification

`extract_claims.py` + `verify_claim_support.py --strict`: every factual claim
must be backed by stored evidence (entity, number, date, and lexical-overlap
checks). Deterministic and cheap — it runs against `evidence.jsonl`, so it
also catches citation drift introduced during editing. Unsupported factual
claims are hard failures: back them or delete them.

## Check 4 — Contradiction resolution

Every contradiction registered in phase 5 is resolved or explicitly disclosed.
Audit both directions: no conflict appears in the report without appearing in
the record, and no recorded conflict disappeared silently. Interpretation and
paradigm conflicts may remain open — but visibly, with both sides presented.

## Check 5 — Numerical sanity check

For every load-bearing number in the report, verify against its `data_point`
evidence row and recompute what's derivable (use `terminal` with python for
the arithmetic — never mental math): percentages, sums, differences, per-capita
values, growth rates. Confirm: units present; denominator defined; timeframe
and geography explicit; currency-year normalized or flagged; order of
magnitude plausible against sibling figures; conflicting numbers reconciled
or the range disclosed. This catches what quote-verification cannot: a
perfectly quoted source whose number is itself wrong, or a derivation the
author bungled.

## Check 6 — Temporal / date arithmetic check

Recompute every duration and interval claim from its endpoint dates: "the
program has run for 26 years" — take the two dates from evidence and subtract
(`terminal`, python). Verify: no arithmetic drift between source and report;
no vague relative time ("recently", "last year") carrying load-bearing weight
— replace with explicit dates; publication dates are internally consistent
(not before the events described, not in the future); trend claims state
their window. Cheap, mechanical, and orthogonal to every other check — this
is the check that would have caught the Guardian's "26 years" error.

## Check 7 — Counterevidence pass

Every major finding's strongest counterargument appears in the report
(Counterevidence Register / Limitations), stated at full strength and cited —
not strawmanned, not buried. Hypothesis outcomes are reported: what was
supported, disconfirmed, inconclusive. A report whose findings face no
recorded opposition has skipped this check.

## Check 8 — Final synthesis review

Read the assembled report once, whole: required sections present and
non-trivial; recommendations trace to registered claims (no unsupported
recommendations); confidence/uncertainty labeling wherever evidence is thin;
scope drift absent; prose standards met (≥80% prose, no placeholders);
limitations honest — including documented triage gaps.

## Validation loop protocol

1. Run the four scripted validators above.
2. Any failure → read the error, fix the specific issue, re-run ALL validators.
3. Max 3 fix cycles. Still failing → STOP and report the issues to the user
   with options. Never ship a report that failed validation silently.

## Packaging

- Bibliography: `python scripts/citation_manager.py export-bibliography
  --dir <run>` renders from the curated corpus — every cited source, no
  ranges, no placeholders. Paste into the report's Bibliography section.
- `qa/qa_report.md`: one line per check — pass/fail, findings, what was fixed.
- Set `finished_at` and complete `phases_completed` in `run_manifest.json`.
- Tell the user where everything is: report path, QA report, bundle.

## Long reports (> ~18,000 words)

Generate progressively (≤2,000 words per write). If the report must exceed
what one session can produce, record continuation state in the manifest
(`continuation` block: sections completed, next sections) and hand a
continuation `delegate_task` agent the report path + manifest + bundle paths —
it resumes from disk with stable source_ids, exactly like any other phase.
