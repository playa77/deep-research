# Search execution quality and negative evidence

This contract applies during initial acquisition and every delta wave. Read it
before dispatch, before declaring gathering complete, and before processing.
Finding a failure after handoff does not make the earlier gathering adequate.

## Plan searches that can answer the question

For each angle identify the actual source classes needed: original records,
native catalogues and indexes, datasets, scholarly treatments and critical
alternatives. Broad web searches and tertiary summaries are discovery routes;
they cannot replace the relevant primary material. Record indispensable native
search routes in the angle's `required_search_surfaces` array in the query-plan
machine block. Use the identical surface string in query records. The handoff
gate requires a usable execution on each of these routes. Do not remove a
required route because it failed; an indispensable inaccessible source leaves
the task blocked until the agreed scope can actually be met.

For historical names, for example, plan documented spelling variants, historical
orthography, date and place bounds, original attestations, corpus coverage and
the difference between a person, surname, dictionary headword and heraldic entry.
An attractive etymology needs critical treatments and counterexamples. A modern
name-frequency page cannot establish medieval attestation or heraldic absence.
These examples describe research methods, not findings about any particular name.

## Record what the tool actually did

Every search execution, including positive controls and failed retries, gets a
query-log row and its own unchanged saved response. `query_log.schema.json`
requires the actual timestamp, `execution_ref`, `response_file` (relative to
`acquisition/`), full `response_sha256`, `query_role`, `outcome`, `result_count`,
`search_surface`, `search_scope` and `search_session`, in addition to identity
and query fields. Use unique actual tool-call references; never invent them.
Reuse a `search_session` only for the same access context and index state.
`search_scope` identifies filters, collections, date ranges and other limits.

Outcomes:

- `results`: the executed search returned actual results; positive result count.
- `no_results`: a working search returned an explicit zero, with a working
  positive control referenced by `control_query_id`.
- `error`, `blocked`, `inconclusive`: the search could not establish a result.
  Include a precise `limitation`. Never encode these as a negative finding.

A JSON/HTML error response is still a response to preserve, not a zero-result
search. HTTP 200, an empty extraction, a generic landing page, a timeout or a
search-engine snippet does not establish a functioning native search. Read the
actual response and verify the endpoint, parameters, returned records and
pagination. Save extracts separately from the original tool response.

## Validate negatives at the time of searching

Before using a zero-result search, run a **known-item positive control**: an
item independently known to exist in the searched collection. Record it with
`query_role: positive_control` and `expected_match` (a specific known title,
identifier or URL that is actually recovered in the saved response). The
control must return results through the **same tool, surface, scope and session**.
Inspect whether the expected record was genuinely recovered; echoed query text
or a recommended link on an error page is insufficient.

If both the target and control fail, the route is inconclusive. For the quoted
CERL/Siebmacher example, failure to recover the control means that route cannot
support “no Mink arms in Siebmacher.” It also cannot be repaired by finding the
control through a general web search. A Deutsche-Biographie negative needs its
own working control on the search route used; a control for another collection
does not validate it.

Recover by consulting the native search documentation, checking request
parameters and collection selection, trying a browser or documented API,
testing documented name variants and searching available original indexes or
scans. Respect access restrictions. Log every attempt and count controls and
retries against the acquisition budget. An actual zero obtained through one
route says only that the specified search returned zero in that collection,
with those filters and variants, at that time. It does not prove universal
nonexistence, completeness of an index, or absence from unsearched volumes.

Keep failed attempts. Append fresh executions with their own response files
and references. If an earlier row mislabeled a tool failure as `no_results`,
correct its classification from the preserved response and document the
correction in `notes`; do not rewrite its response or pretend the old attempt
succeeded. Query merging preserves retries and rejects conflicting descriptions
of the same execution. Do not spend a processing delta wave redoing acquisition
that has not passed this gate.

## Check before the boundary, again on resume, and before release

```bash
python scripts/search_quality.py --run-dir <run>
```

This checks schemas, saved response hashes, unique execution references,
known-item recovery strings and negative/control compatibility. It requires a
usable non-control execution for each planned angle and each required surface.
An invalid `no_results` row blocks the check. Properly classified failed attempts
remain in `unresolved_searches`; they cannot fulfill coverage or a countersearch.
Review those limitations against the definition of done before marking acquire
complete. A successful query elsewhere does not answer an essential missing
question. Budget exhaustion and saturation do not establish completeness.

`session_handoff.py prepare/check/resume` runs these checks and binds all search
responses, the quality summary and the workflow fingerprint in its version-2
snapshot. Present unresolved searches with the gathering-completion notice;
the new session must read the summary before triage. Required routes with no
usable searches block handoff. Identical checks apply to both session choices.

The final fact-check snapshot includes search responses. Only discovery rows
with usable outcomes may satisfy `countersearch_ids`; controls, tool errors,
blocked and inconclusive searches cannot substitute for an executed challenge.
Independent reviewers must still assess relevance, search breadth, native
collection coverage and the inference from results to a report claim. Hashes
and a recovered string cannot establish those semantic judgments.

Older bundles must recover actual execution records and original responses;
there is no generated migration that invents missing controls or provenance.
If acquisition needs repair, preserve the old snapshot and follow the explicit
repair procedure in `session-boundary.md` before preparing a new handoff.
