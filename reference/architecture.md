# Architecture: What Was Merged, What Was Kept, What Was Thrown Away

The skill merges two upstream skills at a clean boundary instead of splicing
two complete workflows:

- **standardhuman/deep-research-skill** contributes the **retrieval
  architecture**: break the problem into search angles, fan out aggressively,
  search in parallel, fetch/extract broadly, build a large source corpus.
- **199-biotechnologies/claude-deep-research-skill** contributes everything
  **after you have a corpus**: evidence persistence, source identity, claim
  extraction, triangulation, counterevidence, verification, disciplined
  synthesis, and the audit trail (scripts + JSONL schemas are ported from it).

## The division

```
USER QUESTION
     │
     ▼
SCOPE & PLAN            (199-biotech epistemology, standardhuman budgets)
     │
     ▼
ACQUISITION ENGINE      (standardhuman mechanism)
     ├── query decomposition into search angles
     ├── parallel search waves (multiple retrieval agents)
     ├── broad fetch/extract
     ├── deduplication
     └── source catalog
     │                     ← the acquisition bundle (contract.md)
     ▼
SOURCE TRIAGE           (new phase; 199-biotech scoring machinery)
     ├── dedupe / syndication detection
     ├── origin clustering (independence groups)
     ├── primary-source prioritization
     ├── coverage-gap detection → delta-acquisition
     └── ~mode-scaled curated corpus
     │
     ▼
EVIDENCE ENGINE         (199-biotech machinery)
     ├── evidence extraction + persistence (evidence.jsonl)
     ├── primary-source deep dives
     ├── claim ledger (claims.jsonl)
     ├── triangulation + contradiction classification
     ├── counterevidence
     ├── synthesis
     ├── adversarial critique + gap-fill
     ├── 8-check final QA
     └── final report
```

Conceptually: **standardhuman = reconnaissance/intelligence collection;
199-biotech = evidence laboratory.** The result is wide enough to discover
obscure primary material, and rigorous enough to distrust that material once
found.

## What was stolen vs. discarded

Kept from standardhuman (the *mechanism*): search-angle decomposition,
parallel waves, broad discovery and fetching, source metadata discipline,
deduplication, budget/stop rules (N_search/N_fetch caps, saturation checks),
the prompt-injection firewall, and hypothesis formation as an acquisition
steering tool.

Thrown away from standardhuman (the *epistemology* — precisely the things
199-biotech does better): the 2-source verification as a final gate,
standalone contradiction-resolution logic, the CSV evidence ledger, Graph-of-
Thoughts state machinery (`graph_state.json`, scoring/pruning rules), its
synthesis phase, its QA phase, and its packaging. Running both halves'
triangulation, synthesis, and QA back-to-back would duplicate the expensive
parts; this pipeline runs them exactly once.

Kept from 199-biotech: the whole evidence laboratory — stable source identity
(`source_id = sha256(canonical_locator)[:16]`), append-only JSONL stores,
claim taxonomy (factual/synthesis/recommendation/speculation), deterministic
claim-support verification, citation verification (DOI/URL/hallucination
patterns), credibility scoring, progressive report assembly, continuation
protocol, prose-first writing standards.

Dropped from 199-biotech: its own thin retrieval phase (phase 3's parallel
search pattern) — subsumed by the acquisition engine — the search-cli /
Claude-Code tool bindings, and the HTML/PDF packaging chain (Markdown is the
deliverable; HTML/PDF can be added later without touching the contract).

## Why the handoff is a bundle, not prose

The acquisition agents produce files, not findings. Three reasons:

1. **Independence of the halves.** The acquisition engine can be swapped or
   re-tuned without touching the epistemic half, and vice versa.
2. **Cost.** Agents that return "my conclusion about the topic" burn tokens
   synthesizing redundantly and produce narratives that must be re-verified
   anyway. Agents that return sources, passages, and leads are cheap and
   parallel-safe.
3. **Durability.** Disk survives context compaction. Any phase can be resumed
   by a fresh session from the manifest + bundle, with zero re-searching.

## Why SOURCE TRIAGE exists

Large acquisition output is excellent acquisition but terrible evidence input.
Five articles derived from the same wire story are not five independent
sources — they are one. Triage (phase 3) enforces the independence principle
that both upstreams gesture at, mechanically: dedupe by content and canonical
identity, cluster syndication and same-origin material into independence
groups, score credibility, prioritize primary sources, and detect coverage
gaps *before* the expensive reasoning budget is spent. Investigators then work
from a curated corpus instead of rediscovering the internet.

## The symmetric blind spots

Each upstream has exactly the weakness the other covers:

- standardhuman is excellent at *finding what exists* and weaker at proving
  that its synthesis is numerically/arithmetically sound.
- 199-biotech is excellent at *proving that its evidence trail is internally
  faithful* and weaker at finding the widest possible evidence base.

A mechanical quote check can happily verify that a source really wrote "26
years" — while the underlying claim is arithmetically wrong. These are
different questions:

```
"Did the source actually say X?"   ≠   "Is X actually true?"
```

The 199 machinery answers the first. The merged final QA adds the second as
explicit gates — hence 8 checks, including the two cheap orthogonal ones the
199 pipeline lacked:

1. Citation/quote verification
2. Source-independence verification
3. Claim-support verification
4. Contradiction resolution
5. **Numerical sanity check**
6. **Temporal/date arithmetic check**
7. Counterevidence pass
8. Final synthesis review

## Cost discipline

The merged pipeline is strictly cheaper than running two complete
methodologies back-to-back because:

- acquisition agents never synthesize (contract),
- deduplication happens once, at the merge boundary,
- credibility scoring and clustering happen once, in triage,
- verification/independence reasoning happens once, in the evidence engine,
- triage shrinks the corpus before investigator reasoning is spent,
- all state is on disk, so context failures cost a re-read, not a re-search.

## Attribution

- standardhuman/deep-research-skill (MIT) — acquisition architecture,
  budgets/stop rules, injection firewall, hypothesis formation.
- 199-biotechnologies/claude-deep-research-skill (MIT) — evidence lab:
  identity/JSONL design, ported scripts (`evidence_store.py`,
  `extract_claims.py`, `source_evaluator.py`, `verify_claim_support.py`,
  `verify_citations.py`, `validate_report.py`), claim/evidence/manifest
  schemas, progressive assembly + continuation, writing standards.
- Both inherit from earlier work: standardhuman credits Anthropic's
  claude-code-deep-research and the ETH Zürich Graph of Thoughts project;
  199-biotechnologies' lineage is documented in its README. This repository is
  MIT; the merge itself and all new code (`citation_manager.py` extensions,
  `triage.py`, schemas, references) are original to this repo.
