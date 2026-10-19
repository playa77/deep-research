# Fact-checking hardening audit

Audit date: 19 October 2026. Scope: the local deep-research skill, its release
contract, acquisition provenance, verification scripts, prompts and regression
suite. This was a code/protocol audit and local adversarial test exercise, not
a factual-accuracy benchmark on real research reports or an independent
external certification.

## Findings reproduced in the previous implementation

The baseline suite passed all 67 tests while these false approvals remained:

| Attack | Observed old behavior | Change |
|---|---|---|
| Run strict verification against a directory with no claims/evidence | Exit 0; zero claims reported as passing | Missing/nonempty bundle checks and required atomic claims |
| Claim: “The treatment reduces mortality.” Evidence: “The treatment does not reduce mortality.” | `supported`, similarity score 0.867 | Lexical tools never assign semantic support; separate polarity/entailment and adversarial checks |
| Claim says 25 million dollars; source says 25 billion dollars | `supported`, score 0.9 | Signed literal/magnitude veto, explicit calculations, separate unit/denominator review |
| “Cats chase dogs.” vs “Dogs chase cats.” | `supported`, score 0.8 | Overlap cannot approve; separate entity/relation and reversal review |
| A claim becomes `partial` or `needs_review` | Strict exit still 0; only `unsupported` counted | Release requires complete approved verifier and red-team records |
| Put facts in tables, short sentences, methodology or selected other sections | Extractor skips them | Full physical-line inventory, manual atomic decomposition and separate coverage review |
| Put speculation wording or a softer claim type around an assertion | No meaningful hard gate; speculation could be auto-supported | Every type reviewed; nonfactual conclusions require labeled, reviewed premises |
| Invent an evidence quote with no persisted source match | Evidence text accepted as a reasoning input | Preserve original response, verify identity, hash inputs, require exact quote offsets |
| Give a claim every evidence quote from its cited source | Best lexical match can “support” an unrelated assertion | Explicit claim-to-evidence links; each link independently reviewed twice |
| Reorder corpus or rerun linker after an unresolved citation | Old links retained; temporary unresolved numbers discarded | Recompute citations from current text, invalidate changed links, unresolved citations fail every run |
| Edit/delete report text after claim extraction | Old append-only candidate claims linger | Candidate reconciliation plus final report/input-bound review snapshot |
| Disclose a failed check in Limitations | Protocol allowed release with disclosed failures | No release waiver; narrow/remove assertions or retain blocked/unverified draft |
| Use persona critiques or a report-level checklist | No per-claim/per-check independent review artifact | Separate real sessions and records for every claim and evidence relationship |

The former year regex also returned century prefixes rather than whole years.
The replacement diagnostic uses complete years, while the release gate uses
source-bound literals, review judgments and actual calendar operations.

## What the new release gate enforces mechanically

- Strict JSON/schema validation, including duplicate-key/ID detection, unknown
  fields, blank records, input identities and nonempty artifacts.
- Original response/document bytes, a retrieval provenance record and faithful
  extracted text, saved separately. Their hashes bind the review snapshot.
- Every nonblank report line is dispositioned; claim locations/excerpts agree
  with the inventory. No section or claim type is automatically exempt.
- Exact quote offsets outside identity frontmatter and inserted key-passage
  annotations, with correct source IDs and current source-byte hashes.
- Claim-specific evidence links and exact agreement between cited numbers,
  corpus identities and generated bibliography titles/URLs.
- Recorded source-quality/identity/context/correction checks, explicit ultimate
  origin lineage, conservative connected-component corroboration counts, and
  recorded challenge-search references for each claim.
- Separate verifier and red-team roles, distinct execution-reference strings,
  every required check, every evidence-link verdict, and input/claim digests
  that invalidate stale approvals. No automatic approval generator is shipped.
- Signed numeric/magnitude/percent vetoes, bounded Decimal calculations from
  exact evidence tokens, declared rounding, ISO-date interval operations and
  acyclic premise graphs.
- A blocked result before verification starts, atomic result replacement,
  invalidation of stale success on errors, output-path protections and a
  final check that inputs did not change during verification.
- Both legacy strict entry points use the same gate. The citation compatibility
  command rejects alternate report filenames rather than checking another
  report accidentally. Non-strict legacy tools are explicitly diagnostic.

The verifier result includes current input hashes, a contract digest, check
time and verifier/schema hashes. Report-format validation and the final
whole-report synthesis read remain additional release requirements.

## Validation performed

```bash
python3 -m unittest discover -s tests
python3 -m compileall -q scripts
git diff --check
```

Result: **145 tests passed**, up from 67, with Python compilation and tracked
patch whitespace checks passing. The 78 added tests include 74 dedicated
release-contract/arithmetic cases and four extraction/linking regressions.
Tests use synthetic local fixtures and make no network calls. Existing tests
that assumed lexical or speculation auto-approval were tightened to require
unverified diagnostic outcomes. The old permissive partial-support assertion
was replaced by an exact `needs_review` expectation.

Adversarial coverage includes missing/stale reviews, omitted coverage lines,
report/source/original-response edits, changed claim text, failed or uncertain
verdicts, author self-approval, reused reviewer sessions, missing link reviews,
fabricated or ambiguous quote offsets, metadata/annotation quote laundering,
path/symlink escapes, wrong source identity, failed HTTP responses, original
response hash mismatches, duplicate IDs/JSON keys, unknown citations/queries,
cyclic premises, changed bibliography URLs, single/shared origins masquerading
as corroboration, malformed manifests, interrupted-run result handling,
incorrect arithmetic, zero denominators, nonfinite outputs, numeric substring
confusion, anniversary boundaries, leap days and unsafe operation strings.

One deliberate boundary test fabricates apparently complete approvals for a
reversed relation. It receives `contract_pass` with the explicit “not proof of
truth” assurance. This documents why syntactically valid reviewer attestations
cannot be treated as a semantic truth oracle. Production never generates those
synthetic approvals; real reviewers must actually perform the checks.

## Guarantees that remain outside the program

A program can validate recorded work, but cannot infer that a reviewer honestly
performed it, that every atomic assertion was recognized, or that a locally
saved response genuinely came from the claimed remote publisher. Hashes are
not publisher signatures. Distinct execution-reference strings are checkable
metadata, not cryptographic proof of independent cognition.

Semantic entailment, complete source lineage, correct operand meaning,
methodological validity, applicability, authenticity, relevance of challenge
searches and the strongest available counterevidence still require substantive
review. A weak model can repeat its error in another session. Several genuine
independent sources can share an error, and an operator can fabricate a fully
consistent bundle. No free or paid Python package eliminates these limits.

The contract therefore distinguishes verified artifact integrity from source
accuracy and valid inference; requires honest uncertainty and separate
adversarial work; and blocks reviewed release when adequate checking is
unavailable. It does not claim “bulletproof” research or a measured accuracy
improvement that has not been evaluated on real reports.

## Dependency and migration

No paid service was introduced. The added runtime dependency is the free,
locally executed `jsonschema`, pinned in `requirements.txt`; arithmetic and
hashing use Python's standard library. Existing search/browser tools and
available model sessions perform acquisition and judgment.

Use Python 3.10+ and pip/uv to install requirements. Existing bundles require
original retrieval provenance and a newly prepared, actually reviewed contract;
legacy `support_status` fields cannot grandfather them into release. Separate
review sessions add cost in time/context even without purchasing a new service.
Reduce report scope to fit the available review budget. See
[fact-checking.md](fact-checking.md) and [README](../README.md) for the procedure.
