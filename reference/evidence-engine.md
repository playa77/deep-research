# Phases 4–5: Evidence Engine

The 199-biotech laboratory. Input: `triage/corpus.jsonl` + raw files for
selected/reserve sources + the query plan + manifest hypotheses. If you find
yourself wanting to search the web here, stop — only the sanctioned
delta-acquisition loops (phase 3 gaps, phase 7 critique) may search, and their
output re-enters the bundle through triage.

## Phase 4: EVIDENCE — persistence

Evidence must not live only in model context. Every load-bearing quote, data
point, or methodological detail from a corpus source is persisted to
`evidence/evidence.jsonl` before any synthesis happens. A continuation agent
(or a fresh session, or an auditor) must be able to reconstruct the report's
justification chain from disk alone.

Read order: primary sources first, deepest for the angles that bear on
load-bearing claims; secondary sources for context and cross-checks; reserve
sources only to verify-then-use.

Persist each evidence span:

```bash
python scripts/evidence_store.py add --dir <run>/evidence --json '{
  "source_id": "<16-hex id from corpus>",
  "quote": "exact text from the source",
  "evidence_type": "direct_quote",   # direct_quote|paraphrase|data_point|figure_reference|methodology
  "locator": "section 3, p. 42",
  "retrieval_query": "<query or angle that surfaced it>"
}'
```

Discipline:

- `quote` is verbatim for `direct_quote` and `data_point` rows — copy, don't
  reconstruct from memory. Paraphrases are labeled `paraphrase`.
- `locator` is mandatory in practice (page, section heading, table, timestamp).
  An evidence row without a locator cannot be re-checked and fails QA check 1.
- Key passages already marked `> [KEY PASSAGE]` in raw files promote directly
  into evidence rows.
- Claim-relevant numbers get `data_point` rows with the exact figure, unit,
  timeframe, and geography in the quote or locator — phase 8's numerical and
  temporal checks run against these rows.
- Sources that turn out irrelevant: do not delete them from the corpus; just
  don't extract evidence. Triage decisions stay auditable.

**Gate**: every selected source either has ≥1 evidence row or is explicitly
noted irrelevant; every evidence row has a locator; evidence exists for every
angle's key materials (not just the loudest sources).

## Phase 5: TRIANGULATE & COUNTEREVIDENCE

This is where claims are formally constructed and tested for the first time.

### 5.1 Claim inventory

From the evidence pool, build the candidate claims the report can actually
support. Register each in the ledger (manually during this phase — the
deterministic extractor re-captures them from drafted text in phase 6):

```bash
python scripts/extract_claims.py add --dir <run>/evidence --json '{
  "section_id": "finding_1",          # provisional until outline refinement
  "text": "Sentence-length atomic claim",
  "claim_type": "factual",            # factual|synthesis|recommendation|speculation
  "cited_source_ids": ["<sid>", "..."],
  "evidence_ids": ["<eid>", "..."]
}'
```

Atomic = one claim per row. "Company X grew revenue 23% in 2024 and plans
three acquisitions" is two claims.

### 5.2 Independence-checked corroboration

Count corroboration in independence groups, never rows. A major (report-grade)
claim needs sources spanning ≥3 distinct `independence_group_id`s in
standard/deep/ultradeep, ≥2 in quick. Single-origin claims are allowed only
when flagged: "only one origin source exists; high uncertainty."

### 5.3 Contradiction classification

When evidence conflicts, classify before resolving:

| Conflict type | Resolution method |
|---|---|
| Data disagreement | Numbers differ → find the primary source; prefer the most recent primary; otherwise report the range with dates |
| Interpretation disagreement | Conclusions differ → present both with evidence strength; do not pick a winner silently |
| Methodological disagreement | Methods differ → weigh by credibility score and study design; disclose the weighting |
| Paradigm conflict | Assumptions differ → unresolved; present both framings; note it as a limitation |

Every contradiction and its disposition is recorded (claim `notes` / QA
report input). Silence about a known conflict is a QA failure (check 4).

### 5.4 Counterevidence pass

For each major finding and each hypothesis: search the corpus for the
strongest counterargument — disconfirming data, failure cases, expert
dissent, methodological weaknesses, alternative explanations. Present
counterarguments at their strongest ("steelman"), cite evidence, and record
them — they become the report's Counterevidence Register and Limitations
sections. Update hypothesis statuses in `run_manifest.json`
(supported/disconfirmed/inconclusive).

**Gate (phases 4–5 complete)**: `evidence.jsonl` covers the selected corpus's
load-bearing material; every major claim registered with cited source_ids +
evidence_ids and meets the group-count rule or is flagged single-origin;
every contradiction classified and dispositioned; counterevidence register
drafted; hypothesis statuses updated.
