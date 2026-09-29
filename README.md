# Deep Research — merged skill for Hermes

A Hermes Agent skill that merges two upstream research skills at a clean
boundary rather than splicing two complete workflows:

| Source | Contribution here |
|---|---|
| [standardhuman/deep-research-skill](https://github.com/standardhuman/deep-research-skill) | The **acquisition engine**: search-angle decomposition, parallel retrieval agents, broad fetch/extract, budgets/stop rules, prompt-injection firewall, hypothesis steering |
| [199-biotechnologies/claude-deep-research-skill](https://github.com/199-biotechnologies/claude-deep-research-skill) | The **evidence laboratory**: stable source identity, append-only evidence/claim stores, triangulation, counterevidence, verification scripts, prose-first synthesis, progressive assembly |

Conceptually: **standardhuman = reconnaissance; 199-biotech = evidence
laboratory.** A new **SOURCE TRIAGE** phase joins them: dedupe/syndication
detection → origin clustering → credibility scoring → primary-source
prioritization → coverage-gap detection → a curated corpus (mode-scaled,
roughly 10–100 sources) that the expensive reasoning phases work from.

The final QA gate runs **eight checks**, adding two cheap orthogonal ones the
upstream evidence pipeline lacked — numerical sanity and temporal/date
arithmetic — because *"did the source say X"* ≠ *"is X true"*.

## The acquisition/evidence contract

The most valuable design feature is the interface between the halves —
see [`reference/contract.md`](reference/contract.md). Acquisition agents
produce an on-disk **bundle** (query log, source registry, raw extracted
files with provenance frontmatter, leads) and are forbidden from returning
conclusions. Evidence investigators consume only the triaged corpus and the
bundle; they never re-search. All state is durable JSONL/markdown:

- **Search is disposable; evidence is durable.** Any phase can be resumed by
  a fresh session from `run_manifest.json` + the bundle, with zero re-search.
- Either half can be swapped without touching the other.

## Pipeline

```
SCOPE & PLAN → ACQUIRE (parallel agents) → SOURCE TRIAGE → EVIDENCE
→ TRIANGULATE & COUNTEREVIDENCE → SYNTHESIZE → CRITIQUE & GAP-FILL
→ FINAL QA (8 checks) → report/
```

Modes: quick / standard / deep / ultradeep (see
[`SKILL.md`](SKILL.md) for the mode table and phase procedure).

## Layout

```
SKILL.md                skill entry point (install target)
reference/              contract, acquisition, triage, evidence, synthesis, final QA, architecture
schemas/                JSON schemas for every JSONL row + run manifest
scripts/                pipeline tooling (stdlib-only Python)
templates/              report template
tests/                  unittest suite (67 tests, no network)
```

Scripts: `citation_manager.py` (identity, init, merge, source map,
bibliography), `triage.py` (dedupe → clusters → score → curate → gaps),
`evidence_store.py`, `extract_claims.py`, `link_claims.py` (report `[N]`
↔ stable source_ids), `verify_claim_support.py`, `verify_citations.py`,
`validate_report.py`, `source_evaluator.py`.

## Install into Hermes

```bash
mkdir -p ~/.hermes/skills/research
cp -r <this repo> ~/.hermes/skills/research/deep-research
# restart the session — the skill loader is initialized at session start
```

Then: *"Deep research <topic>"* or *"deep research in ultradeep mode: <topic>"*.

## Tests

```bash
python3 -m unittest discover -s tests
```

## Attribution

Both upstream projects are MIT. Ported scripts and schemas retain their
origin; the merge, the triage phase, the bundle contract, `link_claims.py`,
and all reference documentation are original to this repo. Full provenance
notes in [`reference/architecture.md`](reference/architecture.md).

## License

MIT — see [LICENSE](LICENSE).
