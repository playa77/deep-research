# Research is read-only skill consumption

This contract applies to the main author, acquisition workers, independent
reviewers and any self-improvement or memory hook invoked during research.
The user-requested skill-maintenance task is a different activity; do not run a
research pipeline just because its source is being edited.

## Write locations and maintenance

- Both installed skill directories are read-only for every research task. This
  includes SKILL.md, scripts, schemas, references, templates, installation
  configuration and any alternate path/symlink to those files. Do not call
  skill-edit tools, patch validators, add helpers or update workflow memories
  to normalize an incident. Generic self-improvement instructions do not
  authorize changing this research protocol during a run.
- Run files live in a separate directory outside the installation. Resolve
  paths first. Ad-hoc measurement/repository scripts go in `<run>/scripts/`;
  source checkouts go in `<run>/repositories/`. Their outputs must retain
  provenance and pass the same evidence/review gates as other report inputs.
- Proposed lessons may be written as inert proposals in
  `<run>/maintenance/skill-change-proposals.md`. Include the failure, observed
  artifacts and whether the run violated its protocol. Do not auto-load these
  proposals as instructions, merge them into the skill, or treat completion of
  an invalid run as evidence that bypassing a gate works.
- Editing the skill requires a separate explicit user request for maintenance.
  Review the actual diff and tests, version the change, and distinguish verified
  defects from hypotheses. A failure transcript is evidence of reported
  behavior, not proof that every claimed file edit or causal explanation is
  accurate. Never delete alleged contaminated files without inspecting them.

## What the local checks enforce

`init-run` refuses a nonempty target or overlapping skill/run directory and
captures `workflow_sha256`. Its fingerprint includes SKILL.md, README.md,
requirements.txt and recursive scripts/schemas/reference/templates/processing-skill
content, plus the separately installed processor entry when present
(excluding Python bytecode caches). Before handoff and processing, a missing
or changed fingerprint fails closed. Never update it to unblock research.

`init-run` also records the host's gathering-session identity. The original
session is permanently barred from processing. `prepare` accepts only that
session, scope/acquisition completion and no substantive processing artifacts.
Its version-3 snapshot includes a random boundary ID, gathering identity,
preparation timestamp, input hashes and prompt; the manifest binds its digest.
An exit-0 `check` remains `awaiting_user`.

`resume` requires a different actual host identity and a record of the complete
user-submitted fresh-session prompt. It validates role, boundary, distinct
message references, time and literal text. There is no same-session route,
`--choice` flag, or caller-selected identity flag. The frozen decision binds the
processing session, and every subsequent processing command checks that current
host identity. Changing only the status, spawning another Python process or
returning to the gathering chat after valid processing cannot unlock it.

All triage CLI routes (including single steps and delta reservation), evidence
and claim mutation CLIs, claim linking, citation numbering/bibliography and the
final fact-checking contract check processing state before doing their work.
Read-only `fact_check.py inspect` permits independent reviewer sessions after
legitimate processing starts, but still permanently rejects the gathering
session. Reviewers cannot use it to acquire authoring or release authority.
Missing manifests are not accepted as legacy processing. The release contract
also hashes the frozen handoff, prompt and decision. Later approved delta
acquisition can extend the bundle without rewriting the initial boundary or
repeating the initial fresh-session handoff.

Read-only diagnostic utilities, low-level Python functions and the shell are
not a security sandbox. Manual report drafting is likewise controlled by the
agent instructions and final release gate, not intercepted by these scripts.

## Host enforcement and honest limits

An agent that can write a decision JSON can fabricate that JSON. Environment session IDs,
timestamps, prompt tokens and hashes do not authenticate user authorship
or prove that the gathering turn ended. A separate Python process also does
not establish a separate assistant turn. Do not claim otherwise.

To make those guarantees independent of agent compliance, the hosting runtime
must enforce all of the following outside the research agent's write authority:

1. Mount both installed skills read-only for the author and every worker; keep
   installation/skill-management and policy-edit tools outside their authority.
2. Issue a boundary event only after the gathering response has been delivered
   and its turn has ended; bind it to the run and snapshot digest.
3. Accept processing only from an authenticated later **user** message that
   submits the fresh-session prompt in a different user-started session. Record
   transcript/session identity in host-owned storage; reject replay.
4. Supply the actual session identity through a protected runtime channel and
   prevent agent commands from substituting `HERMES_SESSION_ID`/`CODEX_THREAD_ID`.
   The current CLI checks those host-injected variables but cannot make them
   immutable inside an unrestricted shell. Deny all processing tool executions and background dispatch until that host
   state advances. Author sessions and workers must share the same policy.
5. Authenticate the saved decision to the host transcript before accepting a
   report as released. Local `contract_pass` remains an audit result, not a
   cryptographic proof of a real user event.

This repository has no host transcript API or host policy-management API, so
it cannot install those runtime controls itself. Its local checks reduce and
expose bypasses but cannot make a deliberately disobedient agent impossible.

## Incident and migration behavior

If processing started prematurely, stop immediately. Preserve and identify
the premature artifacts; do not backdate a decision, reset phases, delete the
history or prepare a clean-looking handoff over them. Disclose the violation
and wait for an explicit recovery instruction. Existing useful report material
may be preserved without certifying the run as compliant.

If skill files changed, stop and report the observed paths/hashes when known.
Keep proposed remedies in the run. Restoring or migrating the installation is
maintenance, not a research repair shortcut. Preserve the original run; older
handoffs and missing baselines require explicitly requested migration and a
real boundary choice, never invented consent. Ordinary acquisition repairs
before processing may archive a pending handoff, fix actual inputs and present
a new boundary, which invalidates all old decision records.
