Process this bundle in this fresh session. Boundary: <BOUNDARY_ID>

Use the separate deep-research-processing skill to process the existing
research run at:

<RUN_DIRECTORY>

I am submitting this prompt in a fresh session to request information processing.
The gathering session must never process this run. Do not initialize another
run, repeat broad gathering, or ask me to choose a continuation mode.

Read deep-research-processing/SKILL.md and the shared engine's
reference/session-boundary.md, reference/runtime-integrity.md,
reference/contract.md, reference/search-quality.md, reference/triage.md and the
complete reference/fact-checking.md. Read run_manifest.json and
acquisition/query_plan.md for the original question, mode, full research
contract, constraints, assumptions, untested hypotheses, budgets, stop reasons,
dead ends, gaps and remaining leads. Read handoff/acquisition.json.search_quality;
blocked searches and failed controls do not establish absence.

Check the actual host session identity. It must differ from the recorded
gathering_session_id. Never set, replace or spoof host identity variables.
Record this actual user-submitted prompt and its session/message references and
receipt time using schemas/user_decision.schema.json. Then run:

python <engine>/scripts/session_handoff.py resume --run-dir <run> --decision <record.json>

If checks fail, stop and report them. Never invent provenance or user messages,
refresh a workflow fingerprint, rewrite the handoff or pretend another shell
process is a fresh session. Update only the run path above if the bundle moved.

Continue phases 3–8: source triage and its bounded delta wave, evidence extraction,
triangulation and counterevidence, synthesis, independent critique, sanctioned
gap-filling and independent verification and red-team review for every claim
and evidence link. Preserve every original quality requirement. This session
is the processing author, not either independent reviewer.

Read source material from disk as needed and persist evidence/claims
progressively. Preserve source IDs and original retrieval provenance. Titles
and slugs do not prove syndication; shared origins need reviewed evidence and
unique material must be retained. Reserve any genuine triage delta with
triage.py begin-delta before dispatch; never reset its ledger. Add sanctioned
delta material to the same bundle and re-triage without another initial pause.

Keep both skills read-only. Do not run self-improvement patches or alter workflow
memories. Deliver the report only after all final-QA gates, including the current
fact_check.py verify contract_pass. A handoff check is not evidence verification.
