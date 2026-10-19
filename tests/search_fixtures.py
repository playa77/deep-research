"""Synthetic search responses for local tests; no real search attestations."""
import hashlib


def search_record(run, qid='q_test', angle='official-records', outcome='results', **extra):
    path = run / 'acquisition/original' / (qid + '.txt')
    path.parent.mkdir(parents=True, exist_ok=True)
    response = ('Synthetic known item recovered. Result record from a test fixture.'
                if outcome == 'results' else
                'Synthetic query executed successfully and returned zero results.'
                if outcome == 'no_results' else
                'Synthetic search failed; no search result was established.')
    path.write_text(response)
    row = dict(query_id=qid, query_text='synthetic fixture search', tool='fixture-search',
               agent='fixture-agent', ts='2026-10-19T00:00:00Z', search_angle=angle,
               outcome=outcome, search_surface='fixture-catalogue', search_scope='all records',
               search_session='fixture-session', query_role='discovery',
               execution_ref='synthetic:' + qid, response_file='original/' + path.name,
               response_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
               result_count=1 if outcome == 'results' else 0)
    if outcome in ('error', 'blocked', 'inconclusive'):
        row['limitation'] = 'Synthetic inaccessible query; cannot establish absence.'
    row.update(extra)
    return row
