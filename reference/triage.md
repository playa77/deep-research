# Phase 3: Source Triage

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

## Run it

```bash
python scripts/triage.py run --run-dir <run> --mode <mode>
```

Exit code 0 = no gaps; exit code 2 = coverage gaps exist (see Gaps below).
The script is idempotent — re-run freely after delta waves; it recomputes all
decisions from `acquisition/` in one pass.

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

**Prioritization.** Selection weighs `origin` (primary 1.0 / secondary 0.6 /
tertiary 0.25) times credibility, then caps the corpus at the mode target
(quick 15 / standard 40 / deep 70 / ultradeep 100; override with
`--max-sources`). Within syndication groups only the representative is kept —
the best-ranked member, others dropped as derivative. Primary sources beat
secondary write-ups of the same material by construction.

**Status meanings.** `selected` = enters evidence work. `reserve` = kept for
cross-checking only; using one in the report requires verifying it first (and
saying so). `dropped` = out of the pipeline, reason recorded.

## Gaps and the delta-acquisition loop

The script compares planned angles (from `query_plan.md`'s machine block)
against selected sources. `uncovered` = zero selected sources for a planned
angle; `undercovered` = fewer than `--min-per-angle` (default 2).

On gaps: run ONE targeted delta wave — a `delegate_task` agent per gap angle,
same acquisition contract, budget ~3 searches / ~3 fetches each. Merge
fragments (`merge-sources`, `merge-query-log`) and re-run `triage.py run`.
Repeat at most once; if an angle still yields nothing credible, record the
hole in the triage report and treat it as a documented limitation — the final
report must disclose it ("No sources found addressing X").

**Gate (phase complete)**: `triage/corpus.jsonl` exists with every discovered
source classified; corpus size within the mode target; all gap angles either
re-covered or documented as limitations; every `reserve` source has its
verification-before-use requirement noted.
