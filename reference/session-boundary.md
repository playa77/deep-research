# Gathering → processing: mandatory session boundary

The two tasks follow the original skill composition exactly:

| Task | Pipeline phases | Responsibility |
|---|---|---|
| Information gathering | 1 scope/plan, 2 acquire, merge/map | standardhuman acquisition engine: collect and persist source material |
| Information processing | 3 triage through 8 final QA/package | source triage + 199-biotech laboratory: evaluate, analyze and write the reviewed report |

Use this boundary in every mode. Two sessions are optional; stopping to offer
the choice is mandatory. Both routes use identical artifacts and processing
requirements. Gathering must not triage, score the evidence, decide hypotheses,
construct findings, or draft the report. Its completion is not a research result.

## 1. Finish gathering and preserve its complete inputs

Meet the scope and acquisition gates in `acquisition.md`. Finish the acquisition
saturation/budget stop, merge sources and query logs, consolidate any agent lead
fragments into `acquisition/leads.jsonl`, and build the source map. Keep all
original responses, retrieval records and faithful raw extracts. No rewriting
sources into a compact handoff narrative.

Before acquisition, populate `run_manifest.json.research_contract` with the
use case, audience, scope (geography, timeframe, inclusions/exclusions), constraints
(sources, budgets, output format and user preferences), and definition of done.
These are nonempty strings; explicitly record unspecified/none values rather
than omitting context. Keep the original question in `query`, the selected mode,
assumptions and hypotheses in their manifest fields, and angles, seed queries,
budgets, stop reasons, known gaps, dead ends and remaining leads in the plan/log.
The processing session must receive every material user instruction through
these files. Hypotheses remain untested until the evidence laboratory evaluates
them. Distinguish acquisition coverage from evidence support.

Mark only `scope` and `acquire` complete, leaving `finished_at: null`, then run:

```bash
python <skill>/scripts/session_handoff.py prepare --run-dir <run>
```

The command checks the recorded task contract, source/query schemas, source
identities, extracted text and original-response provenance/hashes. It also
runs [search-quality.md](search-quality.md): working per-angle and required
native-route executions, preserved query responses, and compatible successful
known-item controls for every zero-result search. Failed/inconclusive queries
cannot satisfy coverage. Review remaining failures against the definition of
done; essential unanswered questions block acquisition completion. It writes
`handoff/acquisition.json` (version-2 input hashes/counts, search-quality summary
and workflow fingerprint) and
`handoff/processing_prompt.md` (the bundled template with the run path), and
sets `processing_handoff.status: awaiting_user`, `next_phase: triage`.
It creates no triage decisions, evidence judgments, claims, reviews or report.
Search-response hashes and the skill/scripts/schemas/references/templates
fingerprint are checked on both preparation and resumption. Changed workflow
files require explicit migration/repair, never silent continuation under old
assumptions.
An exit-0 handoff means the persisted inputs passed these mechanical checks;
it does not establish coverage completeness, source truth or source suitability.
The existing scope/acquisition gates still require review by the gathering agent.

Missing context, absent provenance or a failed check blocks this handoff. Repair
the files from actual records before declaring gathering complete. Never invent
retrievals, fill missing user instructions from a guess, or skip a requirement
to obtain a successful checkpoint.

## 2. Offer the choice and stop

After successful preparation, give the user:

- An information-gathering completion notice with source/query counts and
  logged acquisition gaps, unresolved search executions and stop reasons.
  Distinguish a genuinely searched zero from a broken or inaccessible route. Do not present untested findings.
- The research run location and the **literal, copyable contents** of
  `handoff/processing_prompt.md`, not merely a link or an offer to provide it.
- The question: **“Continue with information evaluation, analysis and the report
  here, or use the handoff prompt to continue in a fresh session?”**

Then end the turn. Never run triage or processing in that turn, assume silence
means continuation, or automatically dispatch another author session. The fresh
session option is useful for models that lose coherence in long contexts;
continuing here retains the current context.

## 3. Resume after the user chooses

For a choice to continue here:

```bash
python <skill>/scripts/session_handoff.py resume --run-dir <run> --choice same-session
```

For the user-submitted prompt in a fresh session, read the skill, this reference,
the acquisition contract and the full fact-checking contract; read the manifest
and query plan, then run:

```bash
python <skill>/scripts/session_handoff.py resume --run-dir <run> --choice new-session
```

The command checks current inputs against the saved snapshot before recording
`status: processing` and the selected session choice in `continuation`.
Submitting the handoff prompt is already a request to start processing: do not
re-ask the initial continuation question. Use the supplied run directory as the
root if the bundle moved; the acquisition snapshot uses relative file paths and
excludes the old absolute `report_dir`. Preserve the original question and scope.

Read `handoff/acquisition.json.search_quality` before starting. Do not treat
failed searches or controls as evidence of absence. Read the triage reference
before interpreting any coverage result. Start at **phase 3, source triage**. Then execute every evidence, triangulation,
counterevidence, synthesis, critique and final-QA gate. Read source files as
needed rather than loading the full corpus into the new context at once; persist
evidence and claims progressively. Author continuation is not an independent
verifier or red-team session; those roles remain separately required.

After processing has started, use `phases_completed` and the persisted artifacts
to resume an interrupted processing task. Do not prepare/resume the initial
handoff again or reset completed phases. Existing bounded delta-acquisition
loops remain available when triage, critique or verification exposes gaps.
Their new sources go through merge and triage in the same run; they do not
repeat the initial pause. Keep the original handoff snapshot as historical
acquisition state; final verification binds the current, expanded evidence bundle.

## Checking or repairing a pending handoff

`session_handoff.py check --run-dir <run>` is read-only and checks a handoff
still awaiting the user's choice. It does not record consent or start processing.
Missing or changed snapshot inputs block resumption. Inspect the discrepancy;
restore the correct inputs or explicitly archive the old `handoff/` files,
clear `processing_handoff`, repair acquisition and prepare a new handoff. Never
silently regenerate hashes to conceal changes. Keep `scope`/`acquire` marked
complete only when their gates still hold. Legacy runs without a research
contract must first recover their actual task context and artifacts; they
are not silently accepted as ready for processing.

Version-1 handoffs and older query logs are not silently upgraded. Recover
actual saved responses, execution metadata and controls; archive the old
snapshot and prepare version 2 only after the current checks pass. Do not
manufacture missing search results, known items or reviews to migrate a bundle.
