# The Acquisition/Evidence Contract

This is the load-bearing interface of the merged pipeline. Acquisition agents
and evidence investigators never talk to each other — they communicate only
through the files specified here. Get this right and either half can be
replaced without touching the other.

> **Search is disposable; evidence is durable.**

The release contract in [fact-checking.md](fact-checking.md) is normative and
supersedes any older QA shortcuts. Every evidence source must additionally
preserve original retrieval response bytes and a `retrieval_record` conforming
to `schemas/retrieval.schema.json`. Original bytes, extracted text and their
provenance records are separate artifacts, bound to final reviews by hashes.

## The bundle

Produced by phase 2 (ACQUIRE), consumed by phases 3–8. Created by
`citation_manager.py init-run`; paths are recorded in `run_manifest.json`.

```
<run_dir>/
  run_manifest.json            # query, research_contract, mode, assumptions, hypotheses, phases, handoff
  handoff/
    acquisition.json           # gathered-input snapshot, checked before processing starts
    processing_prompt.md       # literal prompt offered at the mandatory stop
  acquisition/
    query_plan.md              # plan: angles, seed queries, budgets, hypotheses
    query_log.jsonl            # every search executed (merged from agents)
    sources.jsonl              # merged source registry (schemas/source.schema.json)
    leads.jsonl                # promising leads acquisition surfaced but did not chase
    source_map.json            # generated index: angle→sources, raw file→source, agent stats
    original/                  # unchanged HTTP/tool response or document bytes
    retrieval/                 # retrieval.schema.json records with content hashes
    raw/
      a03-001.md               # one file per fetched source
      a03-002.md               #   <agent>-<NN>.md — agent owns its prefix
    agents/
      acquisition-agent-03.sources.jsonl   # per-agent fragments (input to merge)
      acquisition-agent-03.queries.jsonl
  triage/
    triage_report.md           # dedupe, clusters, credibility, gaps, decisions
    triage_result.json         # current coverage status, capacity and next actions
    corpus.jsonl               # THE curated corpus (schemas/corpus.schema.json)
    overrides.json             # optional manual independence-group assignments
    lineage.json               # optional hash-bound pairwise source-origin review
    delta_attempt.json         # exclusive reservation of the single triage wave
  evidence/
    evidence.jsonl             # append-only evidence rows (schemas/evidence.schema.json)
    claims.jsonl               # atomic claim ledger (schemas/claim.schema.json)
  report/
    report.md
  qa/
    qa_report.md
    fact_check.json            # atomic claims, full coverage, source + claim reviews
    fact_check_result.json     # current mechanical release decision and hashes
```

## Raw source file format

Every fetched source becomes one markdown file: YAML frontmatter (identity)
followed by faithfully extracted text. Keep annotations in separate files. The frontmatter is
generated from the agent's source row — fields match
`schemas/source.schema.json`.

```markdown
---
source_id: 9f1c2ab77e4d5203
url: https://www.assemblee-nationale.fr/dyn/docs/15RAP4323
title: Rapport d'enquête parlementaire — financement de la recherche
publisher: Assemblée nationale
published: 2024-01-17
retrieved: 2026-09-29
origin: primary
medium: government
search_angle: french-government-records
discovered_by: acquisition-agent-07
metadata_status: url_verified
retrieval_record: retrieval/a07-001.json
---

<extracted text>

Le budget de la recherche a diminué de 4,2 % en termes réels entre 2019 et 2023.
```

Rules:

- `source_id` is `sha256(canonical_locator)[:16]` via
  `citation_manager.py register-source` or computed at merge — never invented.
- `origin` is the epistemic class — `primary` (original records, data,
  filings, first reporting), `secondary` (analysis of primary material),
  `tertiary` (aggregations, encyclopedias). This drives triage priority.
- `published` is the actual publication date or `null`. Never guessed.
- Store key-passage annotations separately from raw text. Evidence quotes must
  be exact spans in the actual extracted source body, with real locators.
- Extracted text only. No agent commentary, no argument, no conclusion.

## The agent contract

An acquisition agent receives one angle and returns bundle fragments. Its
output rows are exactly:

**`<id>.sources.jsonl`** — one row per fetched source, with at minimum
`raw_url`, `title`, `origin`, `medium`; ideally all source fields including
`search_angle`, `discovered_by`, `raw_file`, `retrieved`, `published`.
Evidence sources MUST also have `retrieval_record` and the original response
bytes, per the fact-checking contract. Missing provenance blocks release.

**`<id>.queries.jsonl`** — one row per search executed: `query_text`, `tool`,
`search_angle`, `result_count`, `top_urls`, `notes`, actual `ts`, `execution_ref`,
`outcome`, `query_role`, `search_surface`, `search_scope`, `search_session`,
`response_file`, `response_sha256`. Save each original search response, including
failed executions and controls. For `no_results`, supply `control_query_id`;
positive controls require `expected_match`; failed outcomes require `limitation`.
See [search-quality.md](search-quality.md) and the query-log schema. Repeated
query text from a distinct execution is preserved; merging is idempotent for
the same execution and rejects conflicting descriptions of it.

**`acquisition/raw/<id>-NN.md`** — the extracted source files.

**`leads.jsonl` fragments** (optional, one file per agent) — rows
`{"lead": "...", "why": "...", "suggested_query": "..."}` for angles the agent
noticed but could not chase within budget.

Return-summary format (for the orchestrator's merge step — counts only):

```json
{"agent": "acquisition-agent-03", "angle": "regulatory-filings",
 "sources_fetched": 7, "queries_executed": 6, "raw_files": 7, "leads": 2,
 "dead_ends": ["paywalled Nexis access", "2019 archive unavailable"]}
```

Forbidden in agent output: findings, arguments, answers to the research
question, assessments of what the evidence "means". An agent that cannot
 resist concluding has failed the contract; keep its sources, discard its
conclusions. The first place a claim is formally constructed and tested is the
evidence engine.

Rationale: acquisition agents are reconnaissance, not mini-researchers.
Agents that conclude burn budget synthesizing redundantly and contaminate the
pipeline with unverified narratives.

## The merge boundary

After all agents finish, the orchestrator (never the agents) runs:

```bash
python scripts/citation_manager.py merge-sources    --acq-dir <run>/acquisition
python scripts/citation_manager.py merge-query-log  --acq-dir <run>/acquisition
python scripts/citation_manager.py build-source-map --acq-dir <run>/acquisition
```

`merge-sources` normalizes locators, computes stable IDs, and dedupes by
canonical identity (first discoverer wins `discovered_by`). Nothing downstream
ever reads `agents/` fragments again.

Consolidate all agent lead fragments into `acquisition/leads.jsonl` before the
handoff. Preserve the research question, every material user constraint and
preference, assumptions, hypotheses, budgets and stop reasons in the manifest
and query plan/log. `research_contract` stores use case, audience, scope,
constraints and definition of done; it is required by the handoff check.

**This is the mandatory gathering/processing stop**, before source triage.
Follow [session-boundary.md](session-boundary.md) to prepare the checked
handoff, show the fresh-session prompt and end the turn. The user must submit
it to deep-research-processing in a different host session; acquisition
summaries never replace source material. A handoff check is not verification.

## Triage output (the evidence engine's input)

`triage/corpus.jsonl` rows = source record + triage decisions:
`credibility` (0–100), `independence_group_id`, `triage_status`
(`selected` | `reserve` | `dropped`), `selection_reason`, duplicate flags.
See `schemas/corpus.schema.json` and `reference/triage.md`.

`triage/triage_result.json` records `status: ok | coverage_gaps`, selected/
reserve/dropped totals, the configured cap and coverage minimum, whether all
planned minima fit, and per-gap causes and next actions. It is a mechanical
coverage diagnostic, not a claim review or release approval. Rerunning triage
replaces this diagnostic; targeted acquisition attempts remain logged in the
query plan/log. `triage.py begin-delta` reserves the attempt in
`triage/delta_attempt.json` before dispatch, so the bounded-wave budget survives
resumption and interrupted dispatch. Title/slug matches are candidates only;
reviewed shared-origin links group corroboration without dropping unique material.

The evidence engine reads **only**: `triage/corpus.jsonl`,
`acquisition/raw/*.md` and original response/document bytes plus retrieval
records for selected/reserve sources, `acquisition/query_plan.md`
(for scope), and `run_manifest.json` (for contract + hypotheses). It must not
re-search the web; the only sanctioned search loops are delta-acquisition
waves triggered by triage gaps or critique findings, and their output enters
the same bundle and passes through the same triage.

## Resumption invariant

`run_manifest.json.phases_completed` + the bundle must contain enough state
for authorized continuation without repeating broad acquisition. Gathering
belongs to its original session; processing belongs to its separate recorded
author session (other author transfers require explicit recovery):

- before `acquire`: query_plan + manifest suffice
- after `acquire`: the complete task context, merged acquisition bundle,
  original responses and retrieval provenance, and pending handoff state
  suffice to start triage after the user submits the prompt to the separate
  processing skill in a different host session
- after `triage`: corpus.jsonl suffices to start evidence work
- after `evidence`: evidence.jsonl + claims.jsonl suffice to synthesize
- during `synthesize`: report.md (progressive) + continuation state in the
  manifest suffice to continue drafting

If you cannot resume from disk, the contract is broken — fix the files before
proceeding, not the re-search.

The initial handoff snapshot records gathering as it stood at the pause. Once
processing starts, sanctioned delta waves append to the same bundle and pass
through triage; do not refresh that snapshot or repeat its initial fresh-session boundary.
The final fact-check snapshot binds the current full bundle independently.
