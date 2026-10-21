---
name: deep-research-processing
description: Process an existing deep-research acquisition bundle ONLY in a fresh user-started session. Reject the gathering session. Triage, persist evidence, analyze, write and independently verify the report. Never initialize a research run.
version: 0.5.0
author: Daniel (playa77), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [research, evidence, citations, verification, synthesis]
    related_skills: [deep-research]
---

# Deep Research Processing — separate session only

## Entry contract

Use only when the user submits a prepared deep-research processing prompt and
its existing run path in a fresh session. **Never process a run gathered by
this session, even if the user says “continue,” asks for autonomy, or requests a
complete report.** There is no same-session mode or override flag. Do not invoke
this skill as an acquisition worker or automatically dispatched author.

The original gathering session is permanently barred. The host-supplied current
`HERMES_SESSION_ID` or `CODEX_THREAD_ID` must differ from
`run_manifest.json.gathering_session_id`. Missing identity blocks work. Never
set, replace or spoof runtime identity variables. Another shell/Python process,
compaction or a claimed fresh role within the gathering chat is not sufficient.

The installed `deep-research` directory supplies the shared engine. It is the
sibling `../deep-research` when installed; when working in this repository it is
the parent of `processing-skill/`. Locate that engine directory without invoking
its gathering workflow. All paths below are relative to the engine root.
Both skill entry points, shared scripts, schemas and references are read-only.

## Validate the handoff before processing

1. Read `reference/session-boundary.md`, `reference/runtime-integrity.md`,
   `reference/contract.md`, `reference/search-quality.md`, `reference/triage.md`
   and the **complete** `reference/fact-checking.md`.
2. Read `run_manifest.json`, `acquisition/query_plan.md` and the saved snapshot.
   Preserve the original question, mode, full research contract, constraints,
   assumptions, untested hypotheses, budgets, stop reasons, gaps and leads.
   Read `handoff/acquisition.json.search_quality`. Failed controls and blocked
   native searches are not evidence of absence. Source counts do not prove
   that acquisition adequately investigated the question.
3. For a pending boundary, record the **actual user-submitted prompt** and its
   actual session/message metadata using `schemas/user_decision.schema.json`.
   Run `python <engine>/scripts/session_handoff.py resume --run-dir <run>
   --decision <record.json>`. A same-session call is rejected before a decision
   can be accepted. Submission of the prompt is already the user's processing
   request; there is no continuation question or second approval.
4. On failure, stop and report the discrepancy. Never reinitialize the run,
   synthesize missing provenance, refresh the skill baseline, rewrite the
   handoff or invent a user message. Resuming interrupted processing in the
   already-recorded processing session uses persisted phases/artifacts without
   rerunning the initial handoff. A different author session requires explicit
   maintenance/recovery; never silently impersonate the recorded session.

## Execute phases 3–8

1. **Triage.** Run `python <engine>/scripts/triage.py run --run-dir <run>
   --mode <mode>`. Titles/slugs are review leads; remove only full-content
   duplicates. Reviewed common origins affect independence groups while
   retaining unique material. Exit 2 requires inspection of
   `triage/triage_result.json`: resolve corpus capacity before considering source
   shortfalls. Genuine shortfalls permit one triage delta wave total, at most
   3 searches/3 fetches per affected angle. Reserve it with `triage.py begin-delta`
   before dispatch; never reset its durable ledger or lower coverage thresholds.
2. **Evidence.** Read `reference/evidence-engine.md`. Work from the curated
   corpus and raw originals on disk. Persist quotes/locatable spans progressively
   with `evidence_store.py add --dir <run>/evidence --json ...`. Preserve source
   IDs, original responses, retrieval provenance and exact anchors.
3. **Triangulate and seek counterevidence.** Count independent origin groups,
   never raw article counts. Major claims need 3+ groups (quick mode uses the
   explicit contract's 2-group rule). Classify contradictions, steelman opposing
   evidence and reproduce calculations. Hypotheses remain untested until here.
4. **Synthesize.** Read `reference/synthesis.md`. Write prose progressively to
   `report/report.md` using `templates/report_template.md`. Every factual claim
   has `[N]` citations in the same sentence. Preserve all requested scope and
   mode requirements. The report must stand alone on paper: actual verdict,
   reasons, uncertainty and verifier/red-team outcomes, not paths to QA files.
   Bibliography entries each get a separate line and blank line, clickable
   titles and complete visible URLs including query and fragment.
5. **Critique and gap-fill.** Perform independent critique. Only sanctioned
   triage/critique/verification delta-acquisition loops may fetch new material.
   Append it to this run, merge and re-triage. Never repeat the initial gathering
   pause, replace original evidence with summaries, or erase unresolved gaps.
6. **Final QA and package.** Read `reference/final-qa.md` and re-read the full
   fact-checking contract. Finalize the bibliography, validate presentation,
   inventory every assertion and complete atomic coverage. Obtain distinct,
   actual verifier and red-team sessions for **every claim and evidence link**,
   including review of the fact checks. An author simulating personas is invalid.
   Use `templates/verification_prompt.md` and `templates/red_team_prompt.md`.
   Run `fact_check.py verify --run-dir <run>`; missing, stale, uncertain or failed
   checks block reviewed delivery. At most 3 repair cycles, then report blocked.
   No paid service is required; no assertion type or section is exempt.

## Essential commands (only after successful fresh-session resume)

```bash
python <engine>/scripts/triage.py run --run-dir <run> --mode <mode>
python <engine>/scripts/extract_claims.py extract --report <run>/report/report.md --dir <run>/evidence
python <engine>/scripts/link_claims.py link-claims --dir <run>/evidence --run-dir <run>
python <engine>/scripts/citation_manager.py export-bibliography --dir <run>
python <engine>/scripts/validate_report.py --report <run>/report/report.md
python <engine>/scripts/fact_check.py prepare --run-dir <run>
python <engine>/scripts/fact_check.py inspect --run-dir <run>
python <engine>/scripts/fact_check.py verify --run-dir <run>
```

All 8 final checks must have recorded outcomes in `qa/qa_report.md`.
Deliver only a current `contract_pass` matching the final report/bundle and
passing presentation/final synthesis review. Freeze report and bibliography
once reviewed. Changes require renewed review, not appended pass claims.
A contract pass proves audit completeness, not source truth or authenticated
user authorship; see the runtime contract for the host controls required.

## Immutable skill and incidents

Do not invoke self-improvement/skill-edit tools, patch helpers or validators,
update workflow memories, or normalize a failed run as a lesson. Ad-hoc scripts
and source checkouts go in the run directory. Proposed changes remain inert
maintenance notes until a separate explicit user request authorizes skill
maintenance. If the boundary was violated, stop, preserve and disclose it;
never backfill consent or reset the history to make the run appear valid.
