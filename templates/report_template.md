# Research Report: [Topic]

<!--
PROGRESSIVE ASSEMBLY: generate one section per write/patch call, each ≤2,000
words, and write it to file immediately. Sections are sized by content, not
by arbitrary targets.

CITATION TRACKING: maintain the running citation list while drafting. Every
factual claim carries [N] in the same sentence. The Bibliography is generated
from the curated corpus via citation_manager.py export-bibliography and must
contain every cited source — no gaps, no ranges, no placeholders.

STANDARDS: prose-first (≥80%), precision ("reduced mortality 23% (p<0.01)",
never "significantly improved"), fact vs synthesis distinguished ("According
to [1]..." vs "This suggests..."), uncertainty admitted ("No sources found
addressing X"), speculation labeled. No placeholder text of any kind.

Section names below are required by scripts/validate_report.py — keep them.
-->

## Executive Summary

(200–400 words. The decision-grade distillation: findings with numbers,
confidence, and the "so what". Written last-quality-pass, placed first.)

## Introduction

(Scope, audience, methodology summary, and every high-materiality assumption
made during scoping — stated explicitly, never silently defaulted.)

## Main Analysis

### Finding 1: [Title]

(600–2,000 words. Evidence and analysis per finding; every factual claim
cited [N] in the same sentence; implications (SO WHAT / NOW WHAT) at the end
of each finding.)

### Finding 2: [Title]

(...)

## Synthesis & Insights

(Patterns across findings, second-order implications, conceptual framework.
Insights beyond source statements are allowed here but must be labeled as
synthesis and consistent with the claim ledger.)

## Counterevidence Register

*(Recommended section.)* The strongest counterarguments to the main findings,
steelmanned, each cited to evidence. What would change our mind.

## Claims-Evidence Table

*(Recommended section.)* Major claim → evidence_ids → independence groups →
support status. The audit bridge between report and ledger.

## Limitations & Caveats

(Documentation gaps from triage, reserve sources used, unresolved
contradictions, single-origin claims, temporal/geographic coverage holes,
hypotheses that remain inconclusive.)

## Recommendations

(Traceable to registered claims — each recommendation names the findings that
support it. No recommendation without evidence.)

## Bibliography

<!-- Generated: python scripts/citation_manager.py export-bibliography --dir <run>
Format: [N] Author/Org (Year). "Title". Publication. URL (Retrieved: Date)
EVERY citation used in the body, individually listed. -->

## Methodology Appendix

(Pipeline used: mode, acquisition waves and budgets, corpus triage summary —
discovered → selected —, evidence counts, delta-acquisition waves, validation
results, and outline adaptations with their evidence-driven rationale.)
