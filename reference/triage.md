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

**Dedupe & syndication.** Exact duplicates (identical content hash or repeated
canonical locator) are flagged `duplicate_of`. Same or near-identical titles
(slug equality or title similarity ≥ 0.92) on different registrable domains
are flagged as a syndication cluster — five republications of one wire story
become one origin, not five.

**Origin clustering.** Sources sharing a registrable domain or a syndication
lineage get one `independence_group_id` (G001_example.com, ...). This group id
is what triangulation counts in phase 5 — corroborating a claim with two
sources from one group corroborates nothing. Manual corrections go in
`triage/overrides.json` (`{"<source_id>": "G042_different_origin"}`), for cases
deterministic clustering can't see (a wire story republished under different
slugs, a consortium report mirrored on member sites).

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
threshold stay in reserve and consume no selected slots. Within syndication groups only the representative is kept —
the best-ranked member, others dropped as derivative. Primary sources beat
secondary write-ups of the same material by construction.

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

On exit 2, read the structured result once and act on its diagnostics:

1. Check `coverage_capacity.sufficient`. If false, all planned minima cannot
   fit within the cap. Resolve capacity against the agreed research scope
   before acquiring more sources. Do not silently change the cap, lower the
   coverage minimum, remove planned angles or change quality requirements.
2. For `next_action: review_corpus_cap`, enough eligible sources for that
   angle already exist. Review capacity; another search wave cannot resolve
   that constraint. Low-trust reserves and derivative copies do not count as
   eligible alternatives.
3. For `next_action: delta_acquisition`, run ONE targeted wave on those angles
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

At most one triage-triggered wave in total; rerunning triage or resuming a
session does not reset that budget. If coverage still falls short, retain the
gap and exit-2 result and document the precise limitation separately in the
plan and final report. For one selected source, say coverage is limited to
one source; do not say "No sources found". Documentation does not clear the
gap or count as evidence. An essential unanswered question can leave the
research task blocked; all claim verification and release gates still apply.

**Gate (phase complete)**: `triage/corpus.jsonl` exists with every discovered
source classified; corpus size within the mode target; all gap angles either
re-covered or documented as limitations; every `reserve` source has its
verification-before-use requirement noted.
