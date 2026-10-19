# Research Report: [Topic]

<!--
PROGRESSIVE ASSEMBLY: generate one section per write/patch call, each ≤2,000
words, and write it to file immediately. Sections are sized by content, not
by arbitrary targets.

CITATION TRACKING: maintain the running citation list while drafting. Every
factual claim carries [N] in the same sentence. The Bibliography is generated
from the curated corpus via citation_manager.py export-bibliography and must
contain every cited source — no gaps, no ranges, no placeholders.
Each source occupies its own entry line, separated by a blank line so Markdown
renders separate paragraphs. Keep the clickable page title AND display the
complete URL after it; hidden link destinations do not survive paper delivery.

STANDARDS: prose-first (≥80%), precision ("reduced mortality 23% (p<0.01)",
never "significantly improved"), fact vs synthesis distinguished ("According
to [1]..." vs "This suggests..."), uncertainty admitted ("No sources found
addressing X"), speculation labeled. No placeholder text of any kind.

RELEASE: follow reference/fact-checking.md. Every assertion, including tables
and methodological claims, needs atomic coverage and independent verifier +
red-team review. Remove this instructional comment before final review.
The report must stand alone on paper: write actual verdicts, reasons and
remaining uncertainty in its prose and tables. QA paths are supplementary
audit references, never substitutes for an outcome. Include these statements
before freezing the report; never append a claimed gate pass after review.

Section names below are required by scripts/validate_report.py — keep them.
-->

## Executive Summary

(200–400 words. The decision-grade distillation: findings with numbers,
confidence, and the "so what". Written last-quality-pass, placed first.)

**Verdict:** (State the evidence-based conclusion, why it follows, and its main
qualification in plain language. Never substitute "see qa/fact_check_result.json"
or another file reference for the verdict.)

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

(Required for major findings.) The strongest counterarguments to the main findings,
steelmanned, each cited to evidence. What would change our mind.

## Claims-Evidence Table

(A self-contained audit summary.) For every major claim, show the claim in
plain language, cited sources [N] and evidence locators, independence groups,
the actual verifier verdict and reason, the actual red-team verdict and reason,
and residual uncertainty. Evidence IDs and QA paths may supplement these
results; a reader must understand each outcome without opening another file.

## Limitations & Caveats

(Documentation gaps from triage, reserve sources used, unresolved
contradictions, single-origin claims, temporal/geographic coverage holes,
hypotheses that remain inconclusive.)

## Recommendations

(Traceable to registered claims — each recommendation names the findings that
support it. No recommendation without evidence.)

## Bibliography

<!-- Generated: python scripts/citation_manager.py export-bibliography --dir <run>
Format: [N] Author/Org (Year). [Page title](<full URL>). URL: <full URL>
EVERY citation used in the body, individually listed on its own entry line.
Separate entries with a blank line; preserve the full URL including path,
query and fragment. Long URLs may wrap naturally on paper. -->

## Methodology Appendix

(Pipeline used: mode, acquisition waves and budgets, corpus triage summary —
discovered → selected —, evidence counts, delta-acquisition waves, validation
results, real independent reviewer session references, limitations of the
verification, and outline adaptations with their evidence-driven rationale.
Describe which checks passed, failed or remain unreviewed and explain the
findings in the report itself. A pointer to a JSON file is not a verdict.
A contract pass checks audit requirements; it does not prove all claims true.)
