#!/usr/bin/env python3
"""Tests for link_claims.py: display-number -> source_id resolution."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from boundary_fixtures import processing_fixture

SCRIPTS = os.path.join(os.path.dirname(__file__), '..', 'scripts')
SCRIPT = os.path.join(SCRIPTS, 'link_claims.py')
sys.path.insert(0, SCRIPTS)

from citation_manager import canonicalize_locator, compute_source_id  # noqa: E402


def run_link(*args) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True)
    return proc.returncode, json.loads(proc.stdout) if proc.stdout.strip().startswith('{') else {}


class TestLinkClaims(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        processing_fixture(self.tmp)
        self.ev = os.path.join(self.tmp, 'evidence')
        os.makedirs(self.ev)
        # corpus with two sources in display order
        self.corpus_path = os.path.join(self.tmp, 'triage', 'corpus.jsonl')
        os.makedirs(os.path.dirname(self.corpus_path), exist_ok=True)
        rows = []
        for url, title in [('https://a.com/1', 'A'), ('https://b.com/2', 'B')]:
            canonical = canonicalize_locator(url)
            rows.append({'source_id': compute_source_id(canonical),
                         'canonical_locator': canonical, 'raw_url': url,
                         'title': title})
        with open(self.corpus_path, 'w') as f:
            for r in rows:
                f.write(json.dumps(r) + '\n')
        self.sid_a, self.sid_b = rows[0]['source_id'], rows[1]['source_id']

        claims = [
            {'claim_id': 'c1', 'section_id': 'finding_1', 'text': 'Claim one [1].',
             'claim_type': 'factual', 'cited_source_ids': [],
             'evidence_ids': [], 'support_status': 'unverified',
             '_citation_numbers': [1]},
            {'claim_id': 'c2', 'section_id': 'finding_1', 'text': 'Claim two [2, 1].',
             'claim_type': 'factual', 'cited_source_ids': [],
             'evidence_ids': [], 'support_status': 'unverified',
             '_citation_numbers': [2, 1]},
            {'claim_id': 'c3', 'section_id': 'finding_2', 'text': 'Synthesis without citations.',
             'claim_type': 'synthesis', 'cited_source_ids': [],
             'evidence_ids': [], 'support_status': 'unverified'},
            {'claim_id': 'c4', 'section_id': 'finding_2', 'text': 'Drifted citation [9].',
             'claim_type': 'factual', 'cited_source_ids': [],
             'evidence_ids': [], 'support_status': 'unverified',
             '_citation_numbers': [9]},
        ]
        with open(os.path.join(self.ev, 'claims.jsonl'), 'w') as f:
            for c in claims:
                f.write(json.dumps(c) + '\n')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_links_and_flags_unresolvable(self):
        rc, out = run_link('link-claims', '--dir', self.ev, '--sources', self.corpus_path)
        self.assertEqual(rc, 1)  # Unresolved citation remains a hard failure on every run
        self.assertEqual(out['newly_linked'], 2)  # c1, c2 (c4 has only unresolvable)
        self.assertEqual(out['already_linked'], 0)
        self.assertEqual(out['no_citations_in_text'], 1)
        self.assertEqual(out['claims_with_unresolvable_numbers'], {'c4': [9]})

        rows = {r['claim_id']: r for r in
                (json.loads(l) for l in open(os.path.join(self.ev, 'claims.jsonl')) if l.strip())}
        self.assertEqual(rows['c1']['cited_source_ids'], [self.sid_a])
        self.assertEqual(rows['c2']['cited_source_ids'], sorted([self.sid_b, self.sid_a]))
        self.assertNotIn('_citation_numbers', rows['c1'])
        # unresolvable claim keeps empty citation list but loses the temp field
        self.assertEqual(rows['c4']['cited_source_ids'], [])
        self.assertNotIn('_citation_numbers', rows['c4'])

    def test_idempotent(self):
        run_link('link-claims', '--dir', self.ev, '--sources', self.corpus_path)
        rc, out = run_link('link-claims', '--dir', self.ev, '--sources', self.corpus_path)
        self.assertEqual(rc, 1)  # Unresolved citation remains a hard failure on every run
        self.assertEqual(out['already_linked'], 2)
        self.assertEqual(out['newly_linked'], 0)

    def test_reordered_corpus_relinks_existing_citations(self):
        run_link('link-claims', '--dir', self.ev, '--sources', self.corpus_path)
        with open(self.corpus_path) as f:
            corpus = [json.loads(line) for line in f if line.strip()]
        with open(self.corpus_path, 'w') as f:
            for row in reversed(corpus):
                f.write(json.dumps(row) + '\n')
        run_link('link-claims', '--dir', self.ev, '--sources', self.corpus_path)
        with open(os.path.join(self.ev, 'claims.jsonl')) as f:
            claims = {c['claim_id']: c for c in map(json.loads, f)}
        self.assertEqual(claims['c1']['cited_source_ids'], [self.sid_b])
        self.assertEqual(claims['c1']['support_status'], 'unverified')

    def test_unresolved_citation_cannot_disappear_on_rerun(self):
        first_rc, first = run_link('link-claims', '--dir', self.ev, '--sources', self.corpus_path)
        second_rc, second = run_link('link-claims', '--dir', self.ev, '--sources', self.corpus_path)
        self.assertEqual((first_rc, second_rc), (1, 1))
        self.assertEqual(first['claims_with_unresolvable_numbers'], second['claims_with_unresolvable_numbers'])

    def test_requires_run_dir_or_sources(self):
        proc = subprocess.run([sys.executable, SCRIPT, 'link-claims', '--dir', self.ev],
                              capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('--run-dir', proc.stderr)


if __name__ == '__main__':
    unittest.main()
