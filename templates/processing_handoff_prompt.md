Use the installed deep-research skill to perform information processing for the
existing research run at:

<RUN_DIRECTORY>

This is my request to continue with processing in this fresh session. Do not
initialize another run or repeat broad information gathering.

Read SKILL.md, reference/session-boundary.md, reference/contract.md,
reference/search-quality.md, reference/triage.md and the full
reference/fact-checking.md. Read run_manifest.json and acquisition/query_plan.md
for the original question, mode, research contract, constraints, assumptions,
hypotheses, search budgets, stop reasons, dead ends and remaining leads.
Read handoff/acquisition.json.search_quality, including unresolved searches
and the exact native routes and controls. Failed controls and inaccessible
searches are not negatives. Investigate any essential acquisition failure
before interpreting results or spending a delta wave.
Treat hypotheses as untested; acquisition has produced sources, not findings.

Run the following with the actual run directory (update the path above if the
bundle moved):

python <skill>/scripts/session_handoff.py resume --run-dir <run> --choice new-session

If the check fails, stop and report the missing or changed inputs. Never invent
lost context or replace original sources with a summary. Do not automatically
re-run acquisition or overwrite the handoff snapshot.

The resume check binds the current workflow and saved search responses; it
does not replace source-fitness or acquisition-completeness judgment.

Continue phases 3–8: source triage and its bounded delta-acquisition loop,
evidence extraction, triangulation and counterevidence, report synthesis,
critique and targeted gap-filling, then independent verification and red-team
review and the mandatory fact_check.py verify release gate. Apply every
original quality requirement. This session remains the author; it does not
replace either independent reviewer.

Read source material from the bundle as needed and persist evidence and claims
as you work. Preserve stable source IDs and original retrieval provenance.
Title/slug similarity never proves syndication. Shared-origin grouping must
be evidence-backed and must retain nonidentical documents with unique material.
Check current gap causes and source dispositions; use triage.py begin-delta
to reserve the single triage wave before dispatch. Never reset its ledger.
Use only the prescribed delta-acquisition loops for new material, append their
output to the same bundle and re-triage it. Keep unresolved gaps visible.
Do not pause again at the initial acquisition boundary during those loops.
Do not treat a successful handoff check as evidence verification or a release
approval. Deliver the report only under the existing final-QA contract.
