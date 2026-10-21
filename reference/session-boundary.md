# Gathering → processing: two skills, two sessions

| Task | Skill | Session | Responsibility |
|---|---|---|---|
| Gather | deep-research | original host session | phases 1–2: scope, acquire, merge/map, checked handoff |
| Process | deep-research-processing | different, user-started host session | phases 3–8: triage, evidence, analysis, report, independent QA |

**A fresh processing session is mandatory in every mode. There is no choice to
continue here.** This is an architectural boundary, not a tool-consent prompt.
Generic autonomy, a complete-report request, memories about approvals, silence
or a later “continue” in the gathering chat cannot authorize processing there.
Compaction and a new Python/terminal process preserve the host session identity.
The gathering author must not automatically create or delegate a processor.

Read `runtime-integrity.md`. Both skills and the shared engine are read-only
during research. Maintenance must be explicitly requested as a separate task.

## 1. Complete gathering

Use the gathering skill's scope/acquisition gates. Before acquisition, persist
the complete research contract, original question, mode, constraints, assumptions,
untested hypotheses, angles, seed queries and budgets. Persist stop reasons,
gaps, failures, dead ends and remaining leads. Merge agent fragments and query
logs, consolidate leads and rebuild the source map. Retain faithful extracted
text, original response bytes, actual tool executions and retrieval hashes.
No summary replaces the durable bundle. Gathering must never triage, score
source/evidence quality, decide hypotheses, construct findings or draft a report.

The host must supply `HERMES_SESSION_ID` or `CODEX_THREAD_ID`; initialization
captures it as `gathering_session_id` and captures `workflow_sha256`. The agent
must never supply, replace or spoof these variables. Missing identity is a
blocked runtime integration, not permission to invent one. Only the recorded
gathering session may prepare its bundle.

Review essential unanswered questions against the definition of done. A source
count, budget stop or passing mechanical check does not establish adequate
coverage. Mark only `scope` and `acquire` complete; leave `finished_at: null`.

```bash
python <engine>/scripts/session_handoff.py prepare --run-dir <run>
```

This checks the task contract, source/query schemas and identities, faithful
extracts, original-response provenance/hashes and search-quality contract.
It blocks missing native routes and invalid zero-result controls, preserves
unresolved execution failures, and rejects changed/missing skill baselines.
Substantive triage/evidence/report/QA files block preparation: a handoff cannot
launder premature processing. Missing material must be recovered from actual
records, never invented to pass the check.

It writes `handoff/acquisition.json` (version 3) with input hashes, quality
summary, workflow fingerprint, gathering-session identity, random boundary ID
and preparation time. It writes the literal fresh-session prompt at
`handoff/processing_prompt.md`. The manifest binds the snapshot digest and
records `processing_handoff.status: awaiting_user`, `next_phase: triage`.

## 2. Present the handoff and end the gathering task

`prepare` is the final workflow command of the gathering task. Then only read
and display the saved prompt and explain the handoff. Give the user:

- A gathering-complete notice: source/query counts, stop reasons, logged gaps
  and unresolved search failures. Distinguish searched zeroes from broken
  routes. These are acquisition facts, not untested findings.
- The run location and the **complete, literal, copyable contents** of
  `handoff/processing_prompt.md`, not merely a link.
- “Open a fresh session and submit this prompt to deep-research-processing.
  This gathering session cannot perform processing.”

**End the turn.** Do not ask about continuation here. Do not run resume, triage,
scoring, evidence-ledger extraction, hypothesis evaluation, analysis, drafting,
QA or packaging. No queued work, callback or automatically delegated author may
cross the boundary. Merely generating/reading/forwarding the prompt does not
constitute a user request. A later message in this same session cannot unlock it.

A read-only `session_handoff.py check --run-dir <run>` can diagnose a pending
handoff later; success still means `awaiting_user`, never processing permission.

## 3. The user opens the fresh processing session

The user submits the complete saved prompt to **deep-research-processing**.
That submission is already the processing request; do not ask another approval
or offer modes. The current host identity must differ from the gathering ID.
Processing remains a disk-based task: read the original full contract, plan,
snapshot, source material and quality failures, not gathering-context conclusions.

Record the actual submitted prompt and actual session/message metadata in an
input JSON file outside both skills (e.g. `<run>/decision-input.json`). Use host
message IDs when exposed; otherwise honest, resolvable transcript-local turn
labels. Never invent host IDs or timestamps. The notice is in the gathering
session; the user submission is in this different processing session:

```json
{
  "version": 1,
  "boundary_id": "<actual-boundary-id>",
  "boundary_notice": {"session_id": "<gathering-host-session>", "message_id": "<notice-turn>"},
  "user_message": {
    "role": "user",
    "session_id": "<current-processing-host-session>",
    "message_id": "<actual-user-turn>",
    "received_at": "<actual-receipt-time-in-ISO-8601>",
    "content": "<complete-literal-user-submitted-prompt>"
  }
}
```

```bash
python <engine>/scripts/session_handoff.py resume --run-dir <run> --decision <record.json>
```

There is no `--choice` or caller-selected session-identity flag. The command
rejects the gathering host identity, stale/changed input snapshots, mismatched
boundary IDs, non-user records, incorrect session IDs, dates before preparation
or in the future, and text other than the complete prompt. A moved bundle may
replace its old absolute run path with the new path. Do not rewrite other text.

The accepted record is frozen at `handoff/user_decision.json`; its digest and
current `processing_session_id` are recorded in `continuation`. The handoff
becomes `processing`. Every processing CLI checks the host identity, immutable
skill, frozen snapshot/prompt and decision before doing its work. Editing only
a status flag or omitting the manifest cannot unlock processing. The gathering
session stays barred even after another session has legitimately resumed.

## 4. Process and verify

Start at source triage and execute the processor skill's phases 3–8. The quality
requirements are unchanged: all evidence/claims, triangulation/counterevidence,
critique, distinct verifier and red-team sessions, and final fail-closed QA.
Author continuation is not an independent review. A handoff check is not truth
verification, evidence support, source fitness or an acquisition-completeness
judgment. Treat hypotheses as untested and inaccessible searches as unknowns.

Interrupted processing resumes in its recorded processing session using the
manifest and files; do not prepare/resume the initial handoff again. A different
processing author requires explicit recovery/migration, never an identity spoof.
Sanctioned delta waves append to the same bundle and are merged/re-triaged;
they do not rewrite the historical initial snapshot or repeat its pause.
The final release gate binds the current expanded bundle and frozen handoff.

## Failures and migration

Missing context, identity, provenance, prompt, decision or changed workflow means
stop and report. Do not refresh hashes, edit validators, change identity variables,
backfill a message, reset phases or replace sources with a compact narrative.
Premature processing is an incident: preserve and disclose the actual artifacts.
Do not retrospectively create a compliant-looking gathering stop.

For genuine acquisition repairs before processing, explicitly archive all old
handoff/decision files, repair from actual records, and prepare/present a new
boundary in the original gathering session. Previous decision records are stale.
Skill changes, older version-1/2 handoffs and missing initialization baselines
require separate explicitly requested maintenance/migration. Preserve the old
run; no fictional consent or history. See `runtime-integrity.md` for limits and
host controls: local files and environment variables are not authenticated proof
against an agent with arbitrary shell and file authority.
