#!/usr/bin/env python3
"""Check persisted search executions and controls; never infer factual absence.

A response hash proves integrity, not that a search tool worked correctly.
Expected-item recovery and relevance still require substantive review.
"""
import argparse
import json
from pathlib import Path
import sys


def assess_queries(run, queries):
    # Import here so fact_check can reuse this check without an import cycle.
    from fact_check import inside, sha, validate_schema, require
    run = Path(run).resolve()
    by_id, executions, files, responses = {}, set(), set(), {}
    require(bool(queries), 'query log is empty')
    for query in queries:
        validate_schema(query, 'query_log.schema.json')
        qid = query['query_id']
        require(qid.strip() and qid not in by_id, f'duplicate/empty query ID: {qid}')
        require(query['execution_ref'] not in executions, 'duplicate search execution reference')
        require(query['query_text'].strip() and query['tool'].strip(), 'empty search query/tool')
        executions.add(query['execution_ref'])
        by_id[qid] = query
        relative = 'acquisition/' + query['response_file']
        path = inside(run, relative)
        require(path.is_relative_to((run / 'acquisition/original').resolve()),
                'save original search responses under acquisition/original/')
        raw = path.read_bytes()
        require(raw and sha(raw) == query['response_sha256'], f'{qid}: missing/stale search response')
        files.add(relative)
        responses[qid] = raw.decode('utf-8', errors='replace')

    usable, negatives, unresolved = set(), [], []
    for qid, query in by_id.items():
        if query['query_role'] == 'positive_control':
            # Failed controls may be logged, but cannot validate any negative.
            if query['outcome'] == 'results':
                require(query['expected_match'].casefold() in responses[qid].casefold(),
                        f'{qid}: positive control did not recover the expected item')
            else:
                unresolved.append({'query_id': qid, 'outcome': query['outcome'],
                                   'limitation': query.get('limitation', 'positive control failed')})
            continue
        if query['outcome'] in ('error', 'blocked', 'inconclusive'):
            unresolved.append({'query_id': qid, 'outcome': query['outcome'],
                               'limitation': query['limitation']})
            continue
        if query['outcome'] == 'no_results':
            control = by_id.get(query['control_query_id'])
            require(control and control['query_role'] == 'positive_control' and
                    control['outcome'] == 'results',
                    f'{qid}: negative search lacks a successful positive control')
            require(all(control[field] == query[field] for field in
                        ('tool', 'search_surface', 'search_scope', 'search_session')),
                    f'{qid}: control used a different search surface/scope/session')
            negatives.append(qid)
        usable.add(qid)
    return {'usable_query_ids': sorted(usable), 'validated_negative_query_ids': negatives,
            'unresolved_searches': unresolved, 'response_files': sorted(files)}


def check_acquisition(run, queries, angles):
    from fact_check import require
    require(bool(angles), 'missing planned angles; acquisition coverage cannot be assessed')
    result = assess_queries(run, queries)
    usable = set(result['usable_query_ids'])
    for angle in angles:
        aliases = {angle.get('id'), angle.get('name')} - {None}
        found = [q for q in queries if q['query_id'] in usable and q.get('search_angle') in aliases]
        require(found, f'{angle}: no usable search execution; failed searches do not complete an angle')
        for surface in angle.get('required_search_surfaces', []):
            require(any(q['search_surface'] == surface for q in found),
                    f'{angle}: required search surface is unsearched or unusable: {surface}')
    return result


def main():
    from fact_check import load_rows
    from triage import load_plan_angles
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    try:
        result = check_acquisition(run, load_rows(run / 'acquisition/query_log.jsonl'),
                                   load_plan_angles(str(run)))
        print(json.dumps({'status': 'checked', **result}, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
