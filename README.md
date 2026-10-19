# Deep Research for Hermes

A multi-source research skill combining broad acquisition, durable evidence,
source triage and a **fail-closed fact-checking release contract**. No paid
verification API, hosted service or additional model subscription is required.
Use the available search tools and models; Python validation runs locally.

## Two tasks, optional two sessions

The skill keeps its two original research workflows separate:

- **Information gathering (phases 1–2):** the standardhuman acquisition engine
  scopes the question, searches and fetches broadly, then merges its source
  material into the durable acquisition bundle. It produces no conclusions.
- **Information processing (phases 3–8):** source triage prepares that bundle
  for the 199-biotechnologies evidence laboratory, which evaluates evidence,
  analyzes, writes the report and completes independent verification and QA.

**Gathering always stops before processing.** The agent saves the full research
contract and a checked bundle snapshot, asks whether to continue in the same
session, and supplies a literal handoff prompt for a fresh session. It waits
for the user's choice. The new session starts at source triage with the same
original material and quality requirements; no work is replaced with a summary
and no verification step is removed. This makes a fresh context available for
models that become unreliable during long research sessions.

The helper commands are:

```bash
# After scope/acquisition gates are met and recorded; then present the prompt and stop:
python scripts/session_handoff.py prepare --run-dir <run>
# Only after the user chooses continuation here:
python scripts/session_handoff.py resume --run-dir <run> --choice same-session
# Or, in the user-requested fresh session:
python scripts/session_handoff.py resume --run-dir <run> --choice new-session
```

The saved prompt is `handoff/processing_prompt.md`. The boundary check confirms
saved inputs and their integrity, not their truth or research completeness.
Processing retains the existing targeted gap-filling loops and all final-QA
gates. See [the session boundary protocol](reference/session-boundary.md).

## Fact-checking

The previous strict checker could approve a missing ledger, negated claims,
wrong magnitudes and incomplete review. The hardened implementation removes
word overlap as evidence of support and requires:

- Original retrieval responses and provenance, plus faithful extracted text
  and exact quotation offsets, all bound by SHA-256.
- A disposition for every nonblank report line, including tables, footnotes,
  short statements and sections previously skipped. Manual atomic claims must
  match the coverage inventory and rendered citations.
- Separate actual verifier and red-team sessions reviewing every claim, every
  evidence link and the verifier's fact checks, with claim/input-bound records.
- Independent-origin corroboration, recorded countersearches, reviewed contrary
  evidence, exact Decimal arithmetic and calendar-aware date calculations.
- A current machine-readable release result. Missing, stale, uncertain or
  failed reviews block release; there is no waiver or force-pass option.

This makes the evidence trail and required judgments checkable. It **cannot
make research bulletproof**: sources and reviewers can be wrong, searches can
miss evidence, and an operator can fabricate a consistent bundle. Hashes prove
local integrity, not remote authenticity or truth. A `contract_pass` result
means the audit requirements passed. Domain expertise and honest uncertainty
remain necessary. See [the audit](reference/hardening-audit.md) for findings,
regression coverage and residual limits.

## Install

Python 3.10+ and pip or uv are required. The only added dependency is the free
local `jsonschema` validator, pinned in `requirements.txt`.

```bash
python -m pip install -r requirements.txt
# Or: uv pip install -r requirements.txt
mkdir -p ~/.hermes/skills/research
cp -r <this-repo> ~/.hermes/skills/research/deep-research
# Restart the Hermes session so it reloads the skill.
```

Then ask Hermes to deep research a topic. Read [SKILL.md](SKILL.md) and the
[normative fact-checking contract](reference/fact-checking.md). Verification is
mandatory in quick, standard, deep and ultradeep modes; reduce scope to fit the
budget rather than skipping checks.

## Final verification

After acquiring original responses, triaging sources, persisting evidence and
finishing the report and generated bibliography:

```bash
python scripts/validate_report.py --report <run>/report/report.md
python scripts/fact_check.py prepare --run-dir <run>
# Complete atomic coverage and perform separate real verifier + red-team work.
python scripts/fact_check.py inspect --run-dir <run>
python scripts/fact_check.py verify --run-dir <run>
```

`prepare` never creates approvals and refuses to overwrite prior review.
`inspect` prints digests and query IDs, not a release decision. Only `verify`
exit 0 with `status: contract_pass`, matching the current report/bundle, plus
passing format validation and the final synthesis read, permits reviewed
release. It writes `qa/fact_check_result.json`, including failures.

Reports must stand alone on paper. State the actual verdict, reason and
remaining uncertainty in the report; `Verdict: see qa/fact_check_result.json`
is rejected. Each bibliography source gets its own entry line, separated by
a blank line so Markdown renders separate paragraphs. The clickable page
title is retained, followed by the complete visible URL for printed copies.
Both format validation and the release gate enforce these presentation checks;
independent reviewers must still assess whether the verdicts are justified.

Review tasks: [verifier prompt](templates/verification_prompt.md) and
[red-team prompt](templates/red_team_prompt.md). JSON structure is specified in
[the schema](schemas/fact_check.schema.json), with procedures and field meanings
in [the contract](reference/fact-checking.md). Archive old reviews and repeat
verification after substantive changes. Old bundles need original retrieval
provenance and new reviews; they are not silently grandfathered in.

Legacy `verify_claim_support.py ... --strict` and `verify_citations.py --strict`
commands route to this same gate. Non-strict lexical/accessibility diagnostics
cannot approve a report. Candidate extraction is only a drafting aid; the final
contract has its own complete inventory and atomic claims.

## Pipeline and layout

Scope → acquire/merge → **stop and offer session choice** → triage → evidence →
triangulate → synthesize → critique and delta-acquisition → independent
verification and red team → release gate.

State lives in a resumable acquisition/evidence bundle. Source IDs survive
continuation; report-local display numbers must be regenerated after corpus
changes. Review snapshots detect stale report, source, evidence and query-log
inputs. See [the acquisition contract](reference/contract.md).

Triage allocates eligible sources across planned angles before filling the
remaining corpus by rank. It retains the credibility threshold, duplicate
handling and verification requirements. `triage/triage_result.json`
distinguishes corpus-cap constraints from genuine acquisition shortfalls;
only the latter call for the single bounded triage delta wave. Unresolved
coverage still exits 2. See [source triage](reference/triage.md).

`reference/` contains protocols and the audit; `scripts/` contains tooling;
`schemas/` defines records; `templates/` contains the report and review prompts;
`tests/` contains local adversarial regression and pipeline tests.

```bash
python -m unittest discover -s tests
```

Tests make no network calls and include synthetic review fixtures. Those
fixtures are not a method for manufacturing real review approvals.

## Attribution and license

Acquisition architecture derives from
[standardhuman/deep-research-skill](https://github.com/standardhuman/deep-research-skill).
Evidence architecture and legacy validators derive from
[199-biotechnologies/claude-deep-research-skill](https://github.com/199-biotechnologies/claude-deep-research-skill).
The merged pipeline, triage, bundle contract and hardening are local additions.
See [architecture](reference/architecture.md) and [MIT license](LICENSE).
