# Phase 8: Final QA and release

The normative release procedure is [fact-checking.md](fact-checking.md).
Read it in full. It applies in every mode. No failed check can be waived by
disclosing it in Limitations. A report lacking completed checks is an
**unverified draft**. A strict-contract pass is not a guarantee of truth.

The eight QA areas remain, but every claim and evidence link is now subject
to separately recorded verifier and red-team review:

| Area | Mechanical checks | Required independent judgment |
|---|---|---|
| Citation and quote identity | Original response hashes, exact quote offsets, source IDs, rendered bibliography mapping | Actual retrieval/identity, extraction fidelity, context, metadata |
| Independence | Connected groups, domains, duplicate bodies and recorded origins | Common data/reporting lineage, ownership, circular citations |
| Claim support and coverage | All nonblank report lines dispositioned; locations and links reconciled | Atomic decomposition, entailment, roles, negation, modality, no omitted claims |
| Contradictions | Every recorded contradictory link reviewed and cited | No adverse evidence omitted; explicit evidence-based disposition |
| Numerical validity | Signed numeric/magnitude vetoes, Decimal calculations, exact rounding | Correct entity, unit, denominator, baseline and operand meaning |
| Temporal validity | ISO endpoints, elapsed days/completed years, stale-review detection | Event vs publication time, version, scope, observation window |
| Counterevidence | Executed query-log references for every claim; all review checks required | Actual challenge searches/results read, strongest counterexample addressed |
| Synthesis | Separate report-format validator, complete review records | Whole-report read, uncertainty, scope, recommendations grounded in premises |

## Procedure

1. Complete acquisition provenance, triage, evidence, current report and
   generated bibliography. Run `validate_report.py --report <run>/report/report.md`.
2. Run `fact_check.py prepare --run-dir <run>`. The initial contract is
   deliberately unreviewed. Complete the atomic inventory and coverage rows.
3. Assign a separate verifier and separate red-team session using the bundled
   prompts. Review sources, every claim, every evidence link, calculations,
   all coverage dispositions and all verifier fact checks. Retain real task
   references and findings. Use `fact_check.py inspect --run-dir <run>` for
   current input/claim digests and query-row IDs; it does not approve anything.
4. Fix actual findings through targeted delta-acquisition or report revision.
   Persist new retrievals in the same bundle and re-triage. After substantive
   inputs change, archive the prior contract/results and prepare a new snapshot;
   repeat the reviews. Do not merely change hashes or copy approvals.
5. Run `validate_report.py` and `fact_check.py verify --run-dir <run>`. Any
   nonzero exit, `blocked` result, unreviewed/uncertain/rejected judgment or
   unresolved substantive synthesis issue blocks reviewed release.
6. Stop after at most three repair cycles. Show unresolved claims/findings as
   blocked. The cycle limit does not authorize release with failures.

`verify_claim_support.py verify --dir <run>/evidence --strict` and
`verify_citations.py --report <run>/report/report.md --strict` are compatibility
entry points to the SAME gate. Their non-strict modes are diagnostics, not
alternative release checks. HTTP 200 and DOI resolution are not fact checking.

## Package only the current result

Keep `report/report.md`, `qa/fact_check.json`, `qa/fact_check_result.json`,
`qa/qa_report.md`, reviewer task references and the full acquisition/evidence
bundle. Record each of the eight areas above with findings, resolution and
remaining uncertainty in the QA report. State exactly what verification was
performed; do not claim that passing a local contract proves all facts true.

Run the release gate immediately before delivery. Confirm the current result
is `contract_pass` and corresponds to the delivered report and bundle hashes.
Only then mark QA complete and set `finished_at`; these housekeeping fields
are excluded from the research snapshot. All substantive manifest fields are
bound. Tell the user the report, audit and unresolved-limits paths.

For long reports, write progressively and resume from the same bundle. Length
and continuation do not reduce coverage or review requirements.
