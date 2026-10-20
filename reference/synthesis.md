# Phases 6–7: Synthesize → Critique & Gap-Fill

## Phase 6: SYNTHESIZE

### 6.1 Outline refinement (before drafting)

Compare the planned outline against what the evidence actually supports —
evidence comes first, structure follows (199-biotech's WebWeaver refinement).
Signals that require adapting the outline: major findings contradict initial
assumptions; a more important angle emerged; a critical subtopic wasn't
planned; sources consistently discuss unplanned aspects.

Rules: adaptation must be evidence-driven (cite the sources that prompted
it); never restructure more than ~50% of the outline (that means the scope
was mis-set — go back to phase 1 instead); never abandon the core question;
new sections must already have evidence in hand. Record what changed and why
for the methodology appendix.

### 6.2 Progressive assembly

Write the report section-by-section to `report/report.md` using
`write_file`/`patch` — one section per call, ≤ ~2,000 words per call. Section
order and contracts per `templates/report_template.md`:

1. Executive Summary (200–400 words)
2. Introduction (scope, methodology, assumptions)
3. Main Analysis — findings, each 600–2,000 words, cited
4. Synthesis & Insights
5. Limitations & Caveats
6. Recommendations
7. Bibliography — complete, every citation, no placeholders, no ranges
8. Methodology Appendix
9. Recommended: Counterevidence Register, Claims-Evidence Table

### 6.3 Writing standards (enforced by validation)

- Prose-first: ≥80% flowing prose; bullets only for genuine enumerations.
- Every factual claim cited `[N]` in the same sentence, N mapped to stable
  source_ids via `assign-display-numbers`.
- Precision over vagueness: "reduced mortality 23% (p<0.01)", never
  "significantly improved outcomes"; "5 RCTs (n=1,847) show", never "studies
  suggest".
- Distinguish fact from synthesis: "According to [1]..." vs "This suggests...".
- Admit gaps precisely: distinguish a bounded, working zero-result search
  from an unsearched, blocked or inconclusive route. Neither proves universal
  absence. Never fabricate a citation. Apply `search-quality.md`.
- No placeholders, no "content continues", no truncated sections.
- Paper delivery must stand alone. The Executive Summary states the actual
  conclusion, reason and uncertainty. Claims-Evidence Table verdicts state each
  verifier/red-team outcome and reason in plain language. Never replace a verdict
  with "see qa/fact_check_result.json", another path, or a link to an audit.
- Bibliography: one source per entry line, with a blank line between entries
  so they remain separate paragraphs in rendered Markdown. Keep the clickable
  page title and also display its complete URL, including query and fragment.
  Never shorten a URL or rely on the hidden hyperlink destination for print.

### 6.4 Per-section claim loop

The normative [fact-checking contract](fact-checking.md) applies to every
assertion. These scripts generate candidates and diagnostics only; they do
not establish atomic coverage, entailment or truth. A fact in a limitation,
recommendation, conclusion, table, short sentence or heading is still a fact.

After each section: link, extract, and support-check the growing report, and
fix drift immediately rather than at the end:

```bash
python scripts/extract_claims.py extract --report <run>/report/report.md --dir <run>/evidence
python scripts/link_claims.py link-claims --dir <run>/evidence --run-dir <run>
python scripts/verify_claim_support.py verify --dir <run>/evidence
```

`link_claims.py` resolves each claim's `[N]` display numbers to stable
source_ids via the curated corpus — the bridge between report citations and
the evidence store. All candidate claims remain unverified until the separate verifier and red
team complete the final atomic-claim contract. Lexical overlap never assigns
semantic support. Fix unsupported assertions; softening alone does not supply
missing evidence. Final reviews bind to the current report and evidence snapshot.

## Phase 7: CRITIQUE & GAP-FILL

### 7.1 Independent adversarial verification (every mode)

Assign a verifier and red-team reviewer in separate actual sessions, following
`templates/verification_prompt.md` and `templates/red_team_prompt.md`. Require
source-specific review for every claim, every evidence link and every fact
check. An author role-playing a critic cannot satisfy this requirement.
Additional topic-specific perspectives can help:

- **Skeptical Practitioner** — would someone doing this work daily trust
  these findings? What's missing from their vantage?
- **Adversarial Reviewer** — what would a peer reviewer reject? Which
  inferences outrun the evidence? Where is balance missing?
- **Implementation Engineer** — can the recommendations actually be executed?
  What breaks first?

Universal red-team questions: What's missing? What could be wrong? What
alternative explanations exist? What biases might be present? What
counterfactuals are unconsidered?

### 7.2 Gap-fill loop-back

Critique findings split into writing issues (fix in the draft) and evidence
gaps. Evidence gaps get delta-queries — a time-boxed, targeted acquisition
wave (a few `delegate_task` agents, same acquisition contract, small budgets)
whose output merges into the bundle and re-runs triage; then update the
affected sections from the new evidence. This is the only sanctioned search
in phases 6–8. If a gap cannot be closed, remove or narrow the affected assertion, or retain
a blocked/unverified draft. A disclosure does not waive a failed fact check.

**Gate (phases 6–7 complete)**: report structurally complete per the
template; per-section claim check passing; every critique finding either
addressed or listed in Limitations; hypothesis statuses final; delta-wave
output (if any) merged and reflected in the corpus and citations.
