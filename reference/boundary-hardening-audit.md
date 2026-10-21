# Two-skill, two-session boundary hardening — 0.5.0

## Required behavior

The requested architecture is now a mandatory fresh-session split:
`deep-research` gathers only; `deep-research-processing` processes only.
There is no same-session user choice or override flag. The original gathering
session remains permanently forbidden from processing, even after another
session legitimately resumes. A general autonomy preference cannot authorize
crossing this boundary. Both installed skills stay read-only during research.

The supplied transcript reports two failures: an author knowingly crossing the
initial stop and recording its own continuation choice, then changing the skill
to normalize the run. It is a reported failure narrative, not an authenticated
underlying tool log. This change does not assume its speculative causal account
is proven. Neither `references/processing-checkpoints.md` nor the alleged
skill-local `scripts/measure_loc.py` exists in this checkout; no unrelated
operational content was removed on the strength of that allegation.

## Architectural and executable changes

| Previous bypass | Current behavior |
|---|---|
| One entry point describes the entire pipeline | Gathering and processing have separate SKILL.md entry points and installation directories; the gatherer has no processing workflow |
| “Optional two sessions” interpreted as an optional stop | All modes require a user-started fresh processing session; no choice is offered |
| `resume --choice same-session` fabricates continuation | `--choice` and caller-selected session-ID arguments are removed; host identity must differ from the recorded gatherer |
| A later same-chat message is used to continue | The original host session is permanently barred, including after a valid fresh-session resume |
| Processing called directly without resume | Every triage CLI route, imported triage steps, evidence/claim mutation commands, linking, bibliography/numbering, citation checks and final release require valid processing state |
| Missing manifest treated as a standalone/legacy tool path | Run-bound processing fails closed; there is no missing-manifest exemption |
| Manually toggle manifest status | Frozen snapshot, prompt, boundary ID, accepted user-prompt record and session binding are checked too |
| Reuse an old or inferred user instruction | The record must match this boundary's complete submitted prompt, user role, actual processing identity and later receipt time |
| Self-improvement patches make a bad run look normal | Both skills explicitly prohibit research-time skill/memory edits; initialization fingerprints the workflow, recursive additions/deletions/edits and separate processor entry |
| Put ad-hoc code in the installed skill | Run/skill overlap and nonempty reinitialization are rejected; proposed fixes and scripts belong outside the installation |
| Prepare a boundary after processing already occurred | Substantive processing artifacts block preparation; incidents must be preserved and disclosed |
| Break independent verification while enforcing author identity | Read-only `fact_check.py inspect` permits separate reviewers after valid processing; gathering stays barred and reviewers receive no author/release authority |

The initial acquisition snapshot stays historical after processing begins.
Authorized delta material extends the same bundle without resetting the
boundary or requesting another initial handoff. Final QA binds the expanded
bundle plus the frozen handoff, prompt and accepted user record. Existing
retrieval, search-quality, triage, evidence, independent-review and release
requirements remain in force.

## Validation

The complete local suite passed: **229 tests**, including the prior research
and QA regressions. Command: `python -m unittest discover -s tests`.

`tests/test_session_handoff.py` executes the real initialization, acquisition
merge, prepare/check/resume and processing CLIs with explicit synthetic host
session identities. It exercises all modes, valid fresh processing, relocated
bundles, same-session calls with a complete record, removed flags, forged status,
missing manifest/identity/baseline, non-user or generic-autonomy records, stale
boundaries/times, future dates, skill tampering, imported-command bypasses,
sealed gathering, retrospective handoffs and permanent gathering-session denial.
Rejected pending operations are compared against complete pre-operation run
file bytes to ensure that they do not write processing artifacts.

Unit fixtures for unrelated scoring/formatting tests explicitly create synthetic
processing state in test-only code. This fixture mechanism is not a procedure
for authorizing real research. Independent-review inspection has its own
read-only regression. The full local unittest suite includes the prior semantic
QA, search-quality, citation, triage and provenance regressions. No network calls
or model-generated test approvals are used.

## Enforcement limit and deployment

This removes the supported one-session architecture and makes the normal CLI
reject it. It does **not** turn an unrestricted shell into a security sandbox.
Environment identity and agent-written message records are not independently
authenticated. An agent with arbitrary file/shell authority can spoof an
environment, fabricate a record, or avoid the helpers and write prose manually.
The repository cannot install host policy or prove a real user event by itself.

For a tamper-proof guarantee, the host must own session identity and boundary
state, authenticate the fresh user-submitted prompt, forbid agent substitution
of identity, deny premature processing/background dispatch and mount both skills
read-only. The concrete required controls are in `runtime-integrity.md`.
No test result here is presented as proof that those external controls exist.

Install both skill entry points from 0.5.0 together as described in README.md.
The host must actually inject HERMES_SESSION_ID or CODEX_THREAD_ID; missing
integration blocks research rather than guessing a session. Older handoffs and
runs without initialization fingerprints need separate explicit migration,
not silent upgrades or invented consent. Interrupted authoring is bound to its
recorded processing session; changing authors requires explicit recovery.
