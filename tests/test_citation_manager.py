#!/usr/bin/env python3
"""Smoke tests for citation_manager.py CLI (merged-pipeline bundle layout)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'citation_manager.py')


def run_cm(*args: str) -> dict:
    """Run citation_manager.py with args, return parsed JSON from stdout."""
    result = subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f'Exit {result.returncode}: {result.stderr}')
    return json.loads(result.stdout) if result.stdout.strip().startswith(('{', '[')) else result.stdout


class TestInitRun(unittest.TestCase):
    def test_creates_manifest_and_bundle_skeleton(self):
        with tempfile.TemporaryDirectory() as d:
            out = run_cm('init-run', '--out-dir', d, '--query', 'test question', '--mode', 'deep')
            self.assertEqual(out['status'], 'ok')

            manifest = json.load(open(os.path.join(d, 'run_manifest.json')))
            self.assertEqual(manifest['version'], '1.0.0')
            self.assertEqual(manifest['query'], 'test question')
            self.assertEqual(manifest['mode'], 'deep')
            self.assertIsNotNone(manifest['started_at'])
            self.assertIsNone(manifest['finished_at'])
            self.assertEqual(manifest['artifact_paths']['sources'], 'acquisition/sources.jsonl')
            self.assertEqual(manifest['artifact_paths']['corpus'], 'triage/corpus.jsonl')

            # Bundle skeleton exists
            for sub in ('acquisition/raw', 'acquisition/agents', 'triage', 'evidence', 'report', 'qa'):
                self.assertTrue(os.path.isdir(os.path.join(d, sub)), f'{sub} missing')

            # Empty JSONL artifacts exist
            for rel in ('acquisition/sources.jsonl', 'acquisition/query_log.jsonl',
                        'acquisition/leads.jsonl', 'evidence/evidence.jsonl',
                        'evidence/claims.jsonl'):
                path = os.path.join(d, rel)
                self.assertTrue(os.path.exists(path), f'{rel} missing')
                self.assertEqual(os.path.getsize(path), 0)


class TestRegisterSource(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        run_cm('init-run', '--out-dir', self.tmpdir, '--query', 'test')
        self.acq = os.path.join(self.tmpdir, 'acquisition')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_register_and_dedup(self):
        src = json.dumps({
            'raw_url': 'https://arxiv.org/abs/2305.14251',
            'title': 'FActScore',
            'medium': 'academic',
            'year': '2023',
        })
        out1 = run_cm('register-source', '--json', src, '--dir', self.acq)
        self.assertEqual(out1['status'], 'registered')
        self.assertEqual(len(out1['source_id']), 16)
        self.assertTrue(out1['canonical_locator'].startswith('arxiv:'))

        out2 = run_cm('register-source', '--json', src, '--dir', self.acq)
        self.assertEqual(out2['status'], 'duplicate')
        self.assertEqual(out2['source_id'], out1['source_id'])

    def test_extended_provenance_fields(self):
        src = json.dumps({
            'raw_url': 'https://www.assemblee-nationale.fr/rap/R4323',
            'title': 'Rapport parlementaire',
            'origin': 'primary',
            'medium': 'government',
            'publisher': 'Assemblée nationale',
            'published': '2024-01-17',
            'retrieved': '2026-09-29',
            'search_angle': 'french-government-records',
            'discovered_by': 'acquisition-agent-07',
            'raw_file': 'raw/a07-001.md',
        })
        out = run_cm('register-source', '--json', src, '--dir', self.acq)
        self.assertEqual(out['status'], 'registered')
        row = json.loads(open(os.path.join(self.acq, 'sources.jsonl')).read().strip())
        self.assertEqual(row['origin'], 'primary')
        self.assertEqual(row['medium'], 'government')
        self.assertEqual(row['search_angle'], 'french-government-records')
        self.assertEqual(row['discovered_by'], 'acquisition-agent-07')

    def test_legacy_source_type_maps_to_medium(self):
        src = json.dumps({
            'raw_url': 'https://example.com/doc',
            'title': 'Doc',
            'source_type': 'academic',  # 199-biotech legacy field name
        })
        run_cm('register-source', '--json', src, '--dir', self.acq)
        row = json.loads(open(os.path.join(self.acq, 'sources.jsonl')).read().strip())
        self.assertEqual(row['medium'], 'academic')

    def test_bad_origin_falls_back(self):
        src = json.dumps({
            'raw_url': 'https://example.com/x', 'title': 'X', 'origin': 'PRIMARY!!!',
        })
        run_cm('register-source', '--json', src, '--dir', self.acq)
        row = json.loads(open(os.path.join(self.acq, 'sources.jsonl')).read().strip())
        self.assertEqual(row['origin'], 'secondary')

    def test_doi_canonicalization(self):
        src = json.dumps({
            'raw_url': 'https://doi.org/10.1038/s41586-023-06745-9',
            'title': 'Some Nature paper',
        })
        out = run_cm('register-source', '--json', src, '--dir', self.acq)
        self.assertTrue(out['canonical_locator'].startswith('doi:10.1038/'))

    def test_url_normalization(self):
        src1 = json.dumps({
            'raw_url': 'https://Example.Com/article?utm_source=google&id=42',
            'title': 'Test',
        })
        src2 = json.dumps({
            'raw_url': 'https://example.com/article?id=42&utm_medium=email',
            'title': 'Test duplicate',
        })
        out1 = run_cm('register-source', '--json', src1, '--dir', self.acq)
        out2 = run_cm('register-source', '--json', src2, '--dir', self.acq)
        self.assertEqual(out1['source_id'], out2['source_id'])
        self.assertEqual(out2['status'], 'duplicate')


class TestMergeSources(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        run_cm('init-run', '--out-dir', self.tmpdir, '--query', 'test')
        self.acq = os.path.join(self.tmpdir, 'acquisition')
        self.agents = os.path.join(self.acq, 'agents')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name, rows):
        with open(os.path.join(self.agents, name), 'w') as f:
            for row in rows:
                f.write(json.dumps(row) + '\n')

    def test_merge_dedupes_across_agents(self):
        self._write('acquisition-agent-01.sources.jsonl', [
            {'raw_url': 'https://a.com/x', 'title': 'A', 'origin': 'primary',
             'medium': 'news', 'search_angle': 'angle-a'},
            {'raw_url': 'https://b.com/y', 'title': 'B', 'origin': 'secondary',
             'medium': 'web', 'search_angle': 'angle-a'},
        ])
        # agent 02 rediscovers A (with tracking params) and adds C
        self._write('acquisition-agent-02.sources.jsonl', [
            {'raw_url': 'https://a.com/x?utm_source=twitter', 'title': 'A',
             'origin': 'primary', 'medium': 'news', 'search_angle': 'angle-b'},
            {'raw_url': 'https://c.com/z', 'title': 'C', 'origin': 'primary',
             'medium': 'government', 'search_angle': 'angle-b'},
        ])
        out = run_cm('merge-sources', '--acq-dir', self.acq)
        self.assertEqual(out['status'], 'ok')
        self.assertEqual(out['added'], 3)
        self.assertEqual(out['skipped_duplicates'], 1)

        rows = [json.loads(l) for l in open(os.path.join(self.acq, 'sources.jsonl')) if l.strip()]
        self.assertEqual(len(rows), 3)
        first_a = [r for r in rows if r['title'] == 'A'][0]
        self.assertEqual(first_a['discovered_by'], 'acquisition-agent-01')

        # re-merge is idempotent
        out2 = run_cm('merge-sources', '--acq-dir', self.acq)
        self.assertEqual(out2['added'], 0)

    def test_merge_skips_malformed_rows(self):
        self._write('acquisition-agent-01.sources.jsonl', [
            {'title': 'no url at all'},
            {'raw_url': 'https://good.com/1', 'title': 'Good', 'origin': 'primary', 'medium': 'web'},
        ])
        out = run_cm('merge-sources', '--acq-dir', self.acq)
        self.assertEqual(out['malformed_rows'], 1)
        self.assertEqual(out['added'], 1)


class TestMergeQueryLog(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        run_cm('init-run', '--out-dir', self.tmpdir, '--query', 'test')
        self.acq = os.path.join(self.tmpdir, 'acquisition')
        self.agents = os.path.join(self.acq, 'agents')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_merge_and_dedupe(self):
        for agent, q in [('acquisition-agent-01', 'alpha query'),
                         ('acquisition-agent-01', 'alpha query'),  # exact dup
                         ('acquisition-agent-02', 'beta query')]:
            path = os.path.join(self.agents, f'{agent}.queries.jsonl')
            with open(path, 'a') as f:
                f.write(json.dumps({'query_text': q, 'tool': 'web_search',
                                    'search_angle': 'angle-a', 'result_count': 5}) + '\n')
        out = run_cm('merge-query-log', '--acq-dir', self.acq)
        self.assertEqual(out['added'], 2)
        self.assertEqual(out['skipped_duplicates'], 1)
        rows = [json.loads(l) for l in open(os.path.join(self.acq, 'query_log.jsonl')) if l.strip()]
        self.assertTrue(all(r['query_id'].startswith('q_') for r in rows))
        self.assertTrue(all(r['ts'] for r in rows))


class TestBuildSourceMap(unittest.TestCase):
    def test_map_includes_angles_raw_and_agents(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test')
            acq = os.path.join(d, 'acquisition')
            agents = os.path.join(acq, 'agents')
            with open(os.path.join(agents, 'acquisition-agent-03.sources.jsonl'), 'w') as f:
                f.write(json.dumps({'raw_url': 'https://x.com/1', 'title': 'X1',
                                    'origin': 'primary', 'medium': 'news',
                                    'search_angle': 'angle-x'}) + '\n')
            with open(os.path.join(agents, 'acquisition-agent-03.queries.jsonl'), 'w') as f:
                f.write(json.dumps({'query_text': 'q1', 'tool': 'web_search'}) + '\n')
            run_cm('merge-sources', '--acq-dir', acq)
            run_cm('merge-query-log', '--acq-dir', acq)

            raw_dir = os.path.join(acq, 'raw')
            with open(os.path.join(raw_dir, 'a03-001.md'), 'w') as f:
                f.write('---\nsource_id: deadbeefdeadbeef\ntitle: X1\nsearch_angle: angle-x\n---\n\nbody\n')
            with open(os.path.join(raw_dir, 'not-a-source.txt'), 'w') as f:
                f.write('ignored')

            out = run_cm('build-source-map', '--acq-dir', acq)
            self.assertEqual(out['totals']['sources'], 1)
            self.assertEqual(out['totals']['raw_files'], 1)
            self.assertEqual(out['totals']['queries'], 1)

            smap = json.load(open(os.path.join(acq, 'source_map.json')))
            self.assertIn('angle-x', smap['angles'])
            self.assertEqual(smap['angles']['angle-x']['source_count'], 1)
            self.assertIn('raw/a03-001.md', smap['raw_files'])
            self.assertEqual(smap['raw_files']['raw/a03-001.md']['source_id'], 'deadbeefdeadbeef')
            self.assertEqual(smap['agents']['acquisition-agent-03']['sources_discovered'], 1)
            self.assertEqual(smap['agents']['acquisition-agent-03']['queries'], 1)


class TestDisplayNumbersAndBibliography(unittest.TestCase):
    def test_prefers_corpus_over_acquisition(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test')
            acq = os.path.join(d, 'acquisition')
            run_cm('register-source', '--json', json.dumps(
                {'raw_url': 'https://a.com/1', 'title': 'A'}), '--dir', acq)

            # curated corpus (triage/ already exists from init-run) contains
            # the source with triage fields — resolution must prefer it
            src_row = json.loads(open(os.path.join(acq, 'sources.jsonl')).read().strip())
            corpus_row = dict(src_row, triage_status='selected',
                              credibility=75.0, independence_group_id='G001_a.com',
                              selection_reason='test')
            with open(os.path.join(d, 'triage', 'corpus.jsonl'), 'w') as f:
                f.write(json.dumps(corpus_row) + '\n')

            mapping = run_cm('assign-display-numbers', '--dir', d)
            self.assertEqual(len(mapping), 1)  # corpus, not acquisition sources

            bib = run_cm('export-bibliography', '--dir', d, '--style', 'markdown')
            self.assertIn('[1]', bib)
            self.assertIn('A', bib)

    def test_dropped_rows_excluded_from_numbering(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test')
            corpus = os.path.join(d, 'triage', 'corpus.jsonl')
            rows = []
            for i, (url, status) in enumerate([
                    ('https://a.com/1', 'selected'), ('https://b.com/2', 'dropped'),
                    ('https://c.com/3', 'selected')]):
                canonical = f'https://{url.split("//")[1]}/'
                rows.append(dict(
                    source_id=f'{i:016x}', canonical_locator=canonical,
                    raw_url=url, title=f'S{i}', triage_status=status,
                    credibility=70.0, independence_group_id=f'G{i:03d}',
                    selection_reason='test'))
            with open(corpus, 'w') as f:
                for r in rows:
                    f.write(json.dumps(r) + '\n')

            mapping = run_cm('assign-display-numbers', '--dir', d)
            self.assertEqual(sorted(mapping.values()), [1, 2])  # dropped skipped
            bib = run_cm('export-bibliography', '--dir', d, '--style', 'json')
            self.assertEqual(len(bib), 2)
            self.assertTrue(all(r['source_id'] != rows[1]['source_id'] for r in bib))

    def test_bibliography_includes_publisher(self):
        with tempfile.TemporaryDirectory() as d:
            run_cm('init-run', '--out-dir', d, '--query', 'test')
            acq = os.path.join(d, 'acquisition')
            run_cm('register-source', '--json', json.dumps(
                {'raw_url': 'https://a.com/1', 'title': 'A', 'publisher': 'Pub Co',
                 'year': '2024'}), '--dir', acq)
            out = run_cm('export-bibliography', '--dir', d, '--style', 'json')
            self.assertEqual(out[0]['publisher'], 'Pub Co')


class TestCanonicalization(unittest.TestCase):
    """Unit tests for canonicalize_locator without running the CLI."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
        from citation_manager import canonicalize_locator, compute_source_id
        cls.canonicalize = staticmethod(canonicalize_locator)
        cls.compute_id = staticmethod(compute_source_id)

    def test_doi_from_url(self):
        canonicalize_locator = self.canonicalize
        self.assertEqual(
            canonicalize_locator('https://doi.org/10.1038/s41586-023-06745-9'),
            'doi:10.1038/s41586-023-06745-9',
        )
        self.assertEqual(
            canonicalize_locator('https://dx.doi.org/10.1234/test.'),
            'doi:10.1234/test',
        )

    def test_arxiv_from_url(self):
        canonicalize_locator = self.canonicalize
        self.assertEqual(
            canonicalize_locator('https://arxiv.org/abs/2305.14251v2'),
            'arxiv:2305.14251v2',
        )
        self.assertEqual(
            canonicalize_locator('arxiv:2401.15884'),
            'arxiv:2401.15884',
        )

    def test_url_strips_tracking(self):
        canonicalize_locator = self.canonicalize
        result = canonicalize_locator('https://Example.Com/page?utm_source=x&key=val')
        self.assertNotIn('utm_source', result)
        self.assertIn('key=val', result)
        self.assertTrue(result.startswith('https://example.com'))

    def test_url_strips_fragment(self):
        canonicalize_locator = self.canonicalize
        result = canonicalize_locator('https://example.com/page#section')
        self.assertNotIn('#section', result)

    def test_url_strips_trailing_slash(self):
        canonicalize_locator = self.canonicalize
        result = canonicalize_locator('https://example.com/page/')
        self.assertFalse(result.endswith('/'))


if __name__ == '__main__':
    unittest.main()
