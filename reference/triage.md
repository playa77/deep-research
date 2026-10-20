# Phase 3: Source Triage

This is the first phase of the **information-processing task**, after gathering
has stopped and the user has chosen continuation here or submitted the
fresh-session handoff prompt. Resume through
[session-boundary.md](session-boundary.md) before running triage. Later targeted
delta-acquisition loops re-enter triage without another initial-boundary pause.

Triage converts the acquisition pile into the evidence engine's working
corpus. Not verification — triage: cheap, deterministic, mechanical. The
principle: **194 discovered sources is excellent acquisition but terrible
evidence input.**

```
discovered sources
  → dedupe / syndication detection
  → origin clustering (independence groups)
  → credibility scoring
  → primary-source prioritization → curate
  → coverage-gap detection → (delta-acquisition if needed)
  → triage/corpus.jsonl + triage_report.md
```

Heuristic scores and clusters do not verify claims. Before final use, preserve
original retrievals and obtain source-specific independent review under
[fact-checking.md](fact-checking.md). Domain authority, recency and source
counts are not truth guarantees. Verify actual origin lineage and substantive
fitness; do not "upgrade" a source by changing a numeric score alone.

## Run it

```bash
python scripts/triage.py run --run-dir <run> --mode <mode>
```

Exit code 0 = no gaps; exit code 2 = coverage gaps exist (see Gaps below).
Successful execution writes `triage/triage_result.json` as well as the corpus
and Markdown report. Its `status` is `ok` or `coverage_gaps`; each gap includes
the selected count, minimum, eligible/reserve/dropped counts, cause, actual
acquisition shortfall and `next_action`. An exit 2 is a coverage signal, not a
test failure or permission to weaken research requirements. Argument errors
also exit 2 but print a usage error to stderr rather than a result object.
The script is idempotent — re-run freely after delta waves; it recomputes all
decisions from `acquisition/` in one pass.

`gaps` recomputes selection with the same defaults and accepts the same
`--mode`, `--max-sources` and `--min-per-angle` options as `run`. It prints only
the gap array without writing artifacts; its successful diagnostic exit is 0
even when gaps exist. Use `run` for the persisted result and coverage exit code.

## What each step decides

**Dedupe and lineage.** Only identical complete source bodies may be removed
as duplicates. The comparison reads the whole body (not the first 8,000
characters), preserves case and internal layout, and requires at least 200
characters and 40 words to avoid treating short error messages/snippets as
documents. Original material wins the representative tie-break, then stable
source ID. Identical content counts as one origin even across domains.

Matching titles (similarity ≥ 0.92) or URL slugs produce
`similarity_candidates` for inspection only. A shared subject such as “Mink”
is not syndication. Such matches never delete documents, merge independence
groups or authorize new acquisition. Missing content is not duplication.

**Origin clustering.** Same-domain sources share an independence group by
default. Exact duplicates share a group across domains. Other shared-origin
links require `triage/lineage.json`, an array conforming to
`schemas/lineage.schema.json`. Each pair records `source_ids`, `relation`
(`shared_origin` or `independent`), `reviewer`, substantive `reason`, and maps
`raw_sha256` and `passages` keyed by both source IDs. Use full extracted-file
hashes and exact body passages showing attribution or the reason for the
judgment. Changed source files, unknown IDs, missing passages and conflicting
pair reviews block triage. A matching title is not a substantive rationale.
Independent review remains necessary; these local records are not truth proofs.

Reviewed shared-origin links merge corroboration groups, **not corpus rows**.
Nonidentical derivatives may contain useful added material; preserve them and
let evidence review assess each passage. Multiple rows from one group still
count as only one origin. `independent` records document the review; they do
not automatically split domain-level groups or override transitive shared
lineage. Legacy `overrides.json` group assignments remain for manual corrections,
never source deletion; final reviewers must check their justification.

**Credibility scoring.** `source_evaluator.py` (ported from 199-biotech)
scores 0–100 from domain authority, recency, expertise, bias signals.
Interpretation bands: ≥80 core-claim eligible; 40–79 usable with normal
citations; <40 `reserve` — never load-bearing until a human-quality check
upgrades it; <20 AND tertiary → dropped.

**Prioritization.** Selection ranks by `0.6 × origin rank + 0.4 × credibility/100`
(primary 1.0 / secondary 0.6 / tertiary 0.25), then caps selected sources at the mode target
(quick 15 / standard 40 / deep 70 / ultradeep 100; override with
`--max-sources`). Among eligible sources it first allocates one source per
planned angle, then a second, up to `--min-per-angle`, always taking the
best-ranked sources within each angle. Ranking breaks ties if capacity is
insufficient. Remaining slots are filled by global rank, including eligible
sources outside planned angles. Sources below the unchanged credibility
threshold stay in reserve and consume no selected slots. Exact duplicate bodies
keep one representative; nonidentical shared-origin sources remain eligible.
Coverage counts rows; independent corroboration still counts reviewed origins.

Coverage allocation can move a higher-ranked source to reserve to make room
for an eligible source on an underrepresented angle. Every source and decision
remains in the corpus for inspection. This balances planned breadth within the
cap; it does not establish substantive relevance or evidence support. Source
fitness review, independent-origin triangulation and final verification still
apply. No source is promoted by lowering its quality threshold or retagging it
to an angle its content does not address.

**Status meanings.** `selected` = enters evidence work. `reserve` = kept for
cross-checking only; using one in the report requires verifying it first (and
saying so). `dropped` = out of the pipeline, reason recorded.

## Gaps and the delta-acquisition loop

The script compares planned angles (from `query_plan.md`'s machine block)
against selected sources. `uncovered` = zero selected sources for a planned
angle; `undercovered` = fewer than `--min-per-angle` (default 2).
Planned angle IDs and names resolve to the same angle; original source tags
are preserved. Counts are selected sources, not proof of independent origins
or claim support.

On exit 2, read the structured result and its source decisions before dispatch.
First check the current search-quality gate and inspect any dropped/reserve
material relevant to the deficit. Fix erroneous metadata, extraction or lineage
decisions from actual evidence and rerun triage; a local processing defect is
not an acquisition shortage. Never infer a shortage from the exit code alone.
Then act on the diagnostics:

1. Check `coverage_capacity.sufficient`. If false, all planned minima cannot
   fit within the cap. Resolve capacity against the agreed research scope
   before acquiring more sources. Do not silently change the cap, lower the
   coverage minimum, remove planned angles or change quality requirements.
2. For `next_action: review_corpus_cap`, enough eligible sources for that
   angle already exist. Review capacity; another search wave cannot resolve
   that constraint. Low-trust reserves and exact duplicates do not count as eligible
   alternatives. Nonidentical derivatives may contribute unique material but
   never additional independent corroboration.
3. For `next_action: delta_acquisition`, reserve the attempt with
   `python scripts/triage.py begin-delta --run-dir <run>` BEFORE dispatch.
   This checks the result against current source/plan/review inputs, checks
   search quality and capacity, and exclusively creates
   `triage/delta_attempt.json`. An existing attempt blocks another reservation,
   including after a crash, re-triage or fresh session. Never delete it to reset
   the budget. Then run ONE targeted wave on those angles
   only, using the same acquisition contract and budgets of at most 3 searches
   and 3 fetches per angle. `additional_sources_needed` is the shortfall in
   eligible sources, not a guarantee that this many fetches will suffice.
   Seek substantively relevant original material and independent origins;
   a numerical count never substitutes for evidence quality.
4. Record the wave's angles, budgets and attempt in `acquisition/query_plan.md`
   before dispatch, and its actual queries, dead ends and outcomes in the
   existing query log/plan. Reuse the acquisition template and schemas with
   new fragment/raw-file prefixes; inspect existing artifacts only as needed
   to resolve an unfamiliar field. Merge sources and query logs, rebuild the
   source map, then rerun triage with the original mode, cap and minimum.

At most one triage-triggered wave in total; the durable reservation consumes
the attempt even if dispatch is interrupted. Record actual execution counts
in the plan/log and enforce the ≤3 search/fetch per-angle limits during dispatch. Rerunning triage or resuming a session does not reset that budget. If coverage still falls short, retain the
gap and exit-2 result and document the precise limitation separately in the
plan and final report. For one selected source, say coverage is limited to
one source; do not say "No sources found". Documentation does not clear the
gap or count as evidence. An essential unanswered question can leave the
research task blocked; all claim verification and release gates still apply.

**Gate (phase complete)**: `triage/corpus.jsonl` exists with every discovered
source classified; corpus size within the mode target; all gap angles either
re-covered or documented as limitations; every `reserve` source has its
verification-before-use requirement noted.
