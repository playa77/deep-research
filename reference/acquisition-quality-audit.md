# Acquisition, triage and handoff rework

Audit date: 19 October 2026. Baseline: merged PR #4, commit `10d6eb4`.
This is a code/protocol audit and local adversarial reproduction. The quoted
production research bundle was not available here; no live CERL or
Deutsche-Biographie result was verified by this exercise.

## Why the previous fix was insufficient

PR #4 changed how sources were allocated across angles and how resulting
shortfalls were diagnosed. It left the earlier destructive dedupe policy:
matching titles/slugs became syndication links; transitive clustering then
removed all but one source. Tests explicitly expected unrelated same-title
documents to be grouped. Better allocation could not recover deleted sources.

There was a second duplicate error: hashing only the first 8,000 normalized
characters could discard long sources with different substantive material.
Source lineage and corpus retention had been conflated: even genuine common
origins caused nonidentical documents with added material to be removed.

The gathering boundary checked artifact integrity and provenance but not
whether recorded search routes worked. Query records had no structured outcome,
saved-response or known-item-control requirement. The final checker accepted
any recorded query hash as a countersearch. Repeating the same query with the
same agent/tool was discarded at merge, including a real recovery attempt.
Acquisition instructions also told agents to log blocked extraction and move on.

These defects explain why processing immediately exposed problems after the
handoff: that was the first destructive triage step and the first substantive
inspection of search execution quality. The boundary preserved the defective
inputs. Changing sessions did not repair them.

## Direct comparison against the merged implementation

The baseline and replacement functions were executed against the same local
synthetic inputs. Original code was loaded from the merged commit, without
editing the workspace or making network calls.

| Reproduction | Merged PR #4 | Reworked behavior |
|---|---|---|
| Twelve distinct reference pages titled “Mink”, sharing a URL slug, covering the three reported angles | 1 selected, 11 dropped; all three angles have gaps | 12 selected, 0 dropped; no gaps, twelve domain groups |
| Two documents with the same first 8,000 characters and different later entries | One flagged as an exact duplicate | Both retained |
| Target query labeled zero-results; known-item control logged inconclusive | Handoff snapshot accepted | Handoff blocked: no successful positive control |

The first two now have direct triage regressions. The third has search-quality
and actual CLI handoff regressions; separate final-gate tests prove that failed
queries and positive controls cannot fulfill countersearch requirements even
when the rest of the synthetic review contract is complete.

## Implemented contracts

- Full-body exact duplicate handling, retaining case and internal layout;
  short identical responses are not automatically discarded as documents.
- Similarity candidates never delete sources or merge groups. Reviewed,
  hash-bound lineage groups corroboration while retaining nonidentical material.
- Persisted search executions and responses, explicit outcomes, compatible
  known-item controls, indispensable native-route coverage and visible failures.
- Search-quality checks before gathering completes and on both handoff routes;
  version-2 snapshots bind response bytes and the workflow fingerprint.
- Distinct retry executions survive merge; conflicting descriptions of one
  execution fail. Final review binds search responses and uses only usable
  discovery queries for countersearches.
- A single triage delta attempt is exclusively reserved on disk before dispatch;
  stale decisions, capacity-only constraints and repeated reservations fail.
  Actual per-angle search/fetch budget accounting remains the dispatcher's duty.
- Missing plans and failed re-triage leave a blocked result, replacing a stale
  successful diagnostic.

The acquisition, processing and review instructions now share
[search-quality.md](search-quality.md). Skill version is `0.4.0`; old handoffs
and query logs need explicit repair from real saved records, with the old
snapshot archived. Missing executions or controls are never generated.

## Validation and limits

The original suite passed **180 tests** despite the reproduced defects.
The expanded suite passes **207 tests**. Existing assertions that endorsed
false lineage/deletion were corrected. Python compilation and `git diff --check`
also pass. Tests use synthetic local responses and reviews, not production
approvals or a live research-accuracy benchmark.

Mechanical controls cannot judge whether a catalogue covers every requested
volume, a spelling variant is historically meaningful, an attribution proves
lineage, or a search result supports a factual conclusion. Those judgments
remain explicit acquisition-completeness, source-fitness and independent review
requirements. An echoed known-item string is not substantive control recovery.
A scoped zero does not prove universal absence. An essential inaccessible
source leaves completion blocked; a limitation disclosure does not answer it.
