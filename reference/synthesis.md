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
- Admit gaps: "No sources found addressing X" — never fabricate a citation.
- No placeholders, no "content continues", no truncated sections.

### 6.4 Per-section claim loop

After each section: link, extract, and support-check the growing report, and
fix drift immediately rather than at the end:

```bash
python scripts/extract_claims.py extract --report <run>/report/report.md --dir <run>/evidence
python scripts/link_claims.py link-claims --dir <run>/evidence --run-dir <run>
python scripts/verify_claim_support.py verify --dir <run>/evidence
```

`link_claims.py` resolves each claim's `[N]` display numbers to stable
source_ids via the curated corpus — the bridge between report citations and
the evidence store. Factual claims that come back `unsupported` are either
backed (add evidence rows + citations) or rewritten — they never ship.
`needs_review` flags low lexical overlap: confirm the evidence genuinely
supports the claim, or soften the sentence.

## Phase 7: CRITIQUE & GAP-FILL

### 7.1 Persona critique (deep/ultradeep; one general critique pass in standard)

Simulate critics relevant to the topic and let each attack the draft:

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
in phases 6–8. If a gap cannot be closed, it is disclosed in Limitations.

**Gate (phases 6–7 complete)**: report structurally complete per the
template; per-section claim check passing; every critique finding either
addressed or listed in Limitations; hypothesis statuses final; delta-wave
output (if any) merged and reflected in the corpus and citations.
