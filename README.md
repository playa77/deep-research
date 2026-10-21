# Deep Research for Hermes

A multi-source research skill combining broad acquisition, durable evidence,
source triage and a **fail-closed fact-checking release contract**. No paid
verification API, hosted service or additional model subscription is required.
Use the available search tools and models; Python validation runs locally.

## Two skills, two mandatory sessions (0.5.0)

- **deep-research** gathers only (phases 1–2), seals its acquisition bundle,
  displays the literal fresh-session prompt and ends the turn.
- **deep-research-processing** processes only (phases 3–8) when the user submits
  that prompt in a different host session. It never initializes a run.

**Same-session processing is removed. There is no user choice and no override
flag.** The original gathering identity is captured at initialization and is
permanently barred by resume, every triage route, evidence/claim writes,
bibliography tools and the release gate. A later same-chat message, compaction
or new Python process cannot unlock it. Processing is bound to its own host
session and a frozen record of the user-submitted prompt. Missing identity,
manifest, handoff or decision fails closed.

The host must inject `HERMES_SESSION_ID` or `CODEX_THREAD_ID`; agents must never
set or replace those values. Local checks cannot stop a shell-authorized agent
from spoofing an environment or fabricating a transcript record. Authenticated
user events, protected session identity and tool gating must be enforced by the
host for an adversarial security guarantee. See [runtime integrity](reference/runtime-integrity.md).

Research consumes both skills read-only. Initialization rejects overlapping
skill/run paths and nonempty runs and fingerprints the engine and both entry
points. Proposed fixes stay inert in the run until separately requested skill
maintenance. See [the hardening audit](reference/boundary-hardening-audit.md).

## Acquisition quality and source retention

The search-quality gate runs before handoff, again on resume and during final
verification. Every search preserves its actual execution and original response.
Zero-result searches need successful known-item controls on the same search
route and scope. Failed/inconclusive executions remain visible and cannot
satisfy countersearch requirements. Planned indispensable native routes must
work before handoff. Retries survive query-log merging.

Triage treats matching titles/slugs as review leads. Full source bodies are
compared without the old 8,000-character truncation; only exact substantive
copies are removed. Reviewed common origins constrain corroboration while
retaining nonidentical documents. The single triage delta wave must be reserved
on disk before dispatch. See [search quality](reference/search-quality.md) and
[triage](reference/triage.md). The [rework audit](reference/acquisition-quality-audit.md)
records direct before/after reproductions and the limits of these checks.

Handoff snapshot version 3 binds these search artifacts and the workflow
fingerprint. Older runs need actual provenance recovered and an explicit
archived-snapshot migration; missing controls cannot be invented. This release
changes the acquisition contract; reinstall the updated skill before starting
or resuming research.

## Handoff commands

In the gathering session, after scope/acquisition gates are met:

```bash
python <engine>/scripts/session_handoff.py prepare --run-dir <run>
```

Display all of `handoff/processing_prompt.md` and end the turn. The user opens a
new session and submits it to the separate processor skill. In that new session,
record the actual submitted prompt using `schemas/user_decision.schema.json`:

```bash
python <engine>/scripts/session_handoff.py resume --run-dir <run> --decision <record.json>
```

There is no `--choice` or caller-supplied session-ID argument. Same-session
resume is rejected. See [the protocol](reference/session-boundary.md).

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
cp -r <this-repo>/processing-skill ~/.hermes/skills/research/deep-research-processing
# Configure host session identity injection; restart Hermes to load both skills.
```

Install both entry points from the same release; do not mix versions.
Then ask Hermes to deep research a topic. Read [SKILL.md](SKILL.md) and the
[normative fact-checking contract](reference/fact-checking.md). Verification is
mandatory in quick, standard, deep and ultradeep modes; reduce scope to fit the
budget rather than skipping checks.

## Final verification

After acquiring original responses, triaging sources, persisting evidence and
finishing the report and generated bibliography:

```bash
python scripts/validate_report.py --report <run>/report/report.md
python scripts/fact_check.py prepare --run-dir <run> --session-id <gathering-session>
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

Scope → acquire/merge → **stop; user opens a fresh session** → triage → evidence →
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
