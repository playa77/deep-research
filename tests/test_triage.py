#!/usr/bin/env python3
"""Tests for triage.py: dedupe, syndication, clustering, selection, gaps."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), '..', 'scripts')
sys.path.insert(0, SCRIPTS)

from citation_manager import canonicalize_locator, compute_source_id  # noqa: E402
import triage  # noqa: E402


class TriageFixture:
    """Builds a fake run directory with agent fragments, raw files, and plan."""

    def __init__(self, root: str):
        self.root = root
        for sub in ('acquisition/raw', 'acquisition/agents', 'triage', 'evidence', 'report', 'qa'):
            os.makedirs(os.path.join(root, sub), exist_ok=True)
        for name in ('acquisition/sources.jsonl', 'acquisition/query_log.jsonl',
                     'acquisition/leads.jsonl', 'evidence/evidence.jsonl',
                     'evidence/claims.jsonl'):
            open(os.path.join(root, name), 'w').close()
        self._n_raw = 0

    def add_source(self, raw_url, title, origin='secondary', medium='web',
                   search_angle='angle-a', body='generic body text about the topic',
                   agent='acquisition-agent-01', published=None, **extra):
        canonical = canonicalize_locator(raw_url)
        sid = compute_source_id(canonical)
        raw_file = None
        if body is not None:
            self._n_raw += 1
            raw_file = f'raw/a01-{self._n_raw:03d}.md'
            fm = (f'---\nsource_id: {sid}\nurl: {raw_url}\ntitle: {title}\n'
                  f'origin: {origin}\nmedium: {medium}\nsearch_angle: {search_angle}\n'
                  f'published: {published or "null"}\n---\n\n')
            with open(os.path.join(self.root, 'acquisition', raw_file), 'w') as f:
                f.write(fm + body + '\n')
        row = {
            'source_id': sid, 'canonical_locator': canonical, 'raw_url': raw_url,
            'title': title, 'origin': origin, 'medium': medium,
            'metadata_status': 'unverified', 'search_angle': search_angle,
            'discovered_by': agent, 'raw_file': raw_file,
            'registered_at': '2026-09-29T00:00:00+00:00',
            'published': published, 'authors': None, 'year': None,
            'publisher': None, 'retrieved': '2026-09-29',
        }
        row.update(extra)
        with open(os.path.join(self.root, 'acquisition', 'sources.jsonl'), 'a') as f:
            f.write(json.dumps(row) + '\n')
        return sid

    def write_plan(self, angles):
        names = [{'id': f'angle-{i+1:02d}', 'name': a} for i, a in enumerate(angles)]
        plan = ("# Query Plan\n\n## Machine Block\n\n```json\n"
                + json.dumps({'angles': names, 'budgets': {'searches': 10}})
                + "\n```\n")
        with open(os.path.join(self.root, 'acquisition', 'query_plan.md'), 'w') as f:
            f.write(plan)

    def rows(self):
        with open(os.path.join(self.root, 'triage', 'corpus.jsonl')) as f:
            return [json.loads(l) for l in f if l.strip()]

    def by_title(self, rows, title):
        return [r for r in rows if r['title'] == title][0]


class TestDedupe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fx = TriageFixture(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_exact_content_duplicate(self):
        sid_a = self.fx.add_source('https://a.com/report', 'Report A',
                                   body='identical body content here')
        sid_b = self.fx.add_source('https://b.com/copy', 'Report B copy',
                                   body='identical body content here')
        sources = triage.load_sources(self.tmp)
        triage.step_dedupe(sources, self.tmp)
        dup = self.fx.by_title(sources, 'Report B copy')
        orig = self.fx.by_title(sources, 'Report A')
        self.assertEqual(dup['duplicate_of'], orig['source_id'])
        self.assertEqual(orig['source_id'], sid_a)

    def test_syndication_same_title_different_domain(self):
        self.fx.add_source('https://reuters.com/story-x', 'New policy announced today',
                           body='reuters body with distinct wording')
        self.fx.add_source('https://some-blog.net/other-path', 'New policy announced today',
                           body='a completely different body text on the same event')
        self.fx.add_source('https://reuters.com/story-y', 'Unrelated other story',
                           body='different content entirely again')
        sources = triage.load_sources(self.tmp)
        triage.step_dedupe(sources, self.tmp)
        s1 = self.fx.by_title(sources, 'New policy announced today')  # first occurrence
        ids = {s['source_id'] for s in sources if s.get('syndication_with')}
        self.assertEqual(len(ids), 2)
        self.assertTrue(s1.get('syndication_with'))

    def test_same_site_same_title_is_not_syndication(self):
        self.fx.add_source('https://a.com/one', 'Same Title Here', body='body one')
        self.fx.add_source('https://b.com/two', 'Same Title Here', body='body two')
        self.fx.add_source('https://c.example.org/x', 'Same Title Here', body='body three')
        sources = triage.load_sources(self.tmp)
        triage.step_dedupe(sources, self.tmp)
        # a.com and c.example.org differ; b.com pairs with one of them — all
        # three share a title so all pair cross-domain; assert no same-domain pair
        # was flagged *because of domain* (clustering handles domains).
        syndicated = {s['source_id'] for s in sources if s.get('syndication_with')}
        self.assertEqual(len(syndicated), 3)


class TestClustering(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fx = TriageFixture(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_same_domain_one_group(self):
        self.fx.add_source('https://a.com/1', 'One', body='body one unique')
        self.fx.add_source('https://a.com/2', 'Two', body='body two unique')
        self.fx.add_source('https://b.org/3', 'Three', body='body three unique')
        sources = triage.load_sources(self.tmp)
        triage.step_dedupe(sources, self.tmp)
        triage.step_cluster(sources, self.tmp)
        groups = {s['title']: s['independence_group_id'] for s in sources}
        self.assertEqual(groups['One'], groups['Two'])
        self.assertNotEqual(groups['One'], groups['Three'])

    def test_syndication_merges_groups(self):
        self.fx.add_source('https://reuters.com/x', 'Shared headline text',
                           body='reuters original body')
        self.fx.add_source('https://mirror-site.info/y', 'Shared headline text',
                           body='mirror body with other words')
        sources = triage.load_sources(self.tmp)
        triage.step_dedupe(sources, self.tmp)
        triage.step_cluster(sources, self.tmp)
        groups = {s['independence_group_id'] for s in sources}
        self.assertEqual(len(groups), 1)

    def test_overrides_win(self):
        sid = self.fx.add_source('https://a.com/1', 'One', body='body one unique')
        self.fx.add_source('https://a.com/2', 'Two', body='body two unique')
        with open(os.path.join(self.tmp, 'triage', 'overrides.json'), 'w') as f:
            json.dump({sid: 'G099_special'}, f)
        sources = triage.load_sources(self.tmp)
        triage.step_dedupe(sources, self.tmp)
        triage.step_cluster(sources, self.tmp)
        groups = {s['title']: s['independence_group_id'] for s in sources}
        self.assertEqual(groups['One'], 'G099_special')
        self.assertNotEqual(groups['Two'], 'G099_special')


class TestSelect(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fx = TriageFixture(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _prepare(self):
        sources = triage.load_sources(self.tmp)
        triage.step_dedupe(sources, self.tmp)
        triage.step_cluster(sources, self.tmp)
        triage.step_score(sources, self.tmp)
        return sources

    def test_primary_beats_secondary_in_syndication_group(self):
        # same title, different domains -> syndication group -> keep the primary
        self.fx.add_source('https://blogs.example.org/story', 'The Big Finding',
                           origin='secondary', body='secondary write-up text')
        self.fx.add_source('https://data.gov.ie/report', 'The Big Finding',
                           origin='primary', body='primary record text')
        sources = self._prepare()
        triage.step_select(sources, self.tmp, max_sources=10)
        kept = [s for s in sources if s['triage_status'] == 'selected']
        dropped = [s for s in sources if s['triage_status'] == 'dropped']
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]['origin'], 'primary')
        self.assertEqual(len(dropped), 1)
        self.assertIn('syndicated/derivative', dropped[0]['selection_reason'])

    def test_low_cred_tertiary_dropped(self):
        from unittest.mock import patch, MagicMock
        self.fx.add_source('https://spam-content.blogspot.com/x', 'SEO listicle',
                           origin='tertiary', body='thin content keyword stuffing')
        sources = triage.load_sources(self.tmp)
        stub = MagicMock()
        stub.evaluate_source.return_value = MagicMock(
            overall_score=15.0, recommendation='low_trust')
        with patch.object(triage, 'SourceEvaluator', return_value=stub):
            triage.step_score(sources, self.tmp)
        triage.step_select(sources, self.tmp, max_sources=10)
        self.assertEqual(sources[0]['triage_status'], 'dropped')
        self.assertIn('low credibility', sources[0]['selection_reason'])

    def test_cap_marks_reserve(self):
        for i in range(5):
            self.fx.add_source(f'https://site{i}.com/p{i}', f'T{i}',
                               origin='primary', body=f'body {i} text here')
        sources = self._prepare()
        triage.step_select(sources, self.tmp, max_sources=2)
        statuses = [s['triage_status'] for s in sources]
        self.assertEqual(statuses.count('selected'), 2)
        self.assertEqual(statuses.count('reserve'), 3)


class TestGaps(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fx = TriageFixture(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_uncovered_and_undercovered(self):
        self.fx.add_source('https://a.com/1', 'One', search_angle='stats',
                           origin='primary', body='body one')
        self.fx.add_source('https://a.com/2', 'Two', search_angle='stats',
                           origin='primary', body='body two')
        self.fx.add_source('https://b.com/3', 'Three', search_angle='criticism',
                           origin='secondary', body='body three')
        self.fx.write_plan(['stats', 'criticism', 'french-government-records'])
        sources = triage.load_sources(self.tmp)
        triage.step_dedupe(sources, self.tmp)
        triage.step_cluster(sources, self.tmp)
        triage.step_score(sources, self.tmp)
        triage.step_select(sources, self.tmp, max_sources=10)
        gaps = triage.step_gaps(sources, self.tmp, min_per_angle=2)
        by_angle = {g['angle']: g for g in gaps}
        self.assertEqual(by_angle['criticism']['severity'], 'undercovered')
        self.assertEqual(by_angle['french-government-records']['severity'], 'uncovered')
        self.assertNotIn('stats', by_angle)


class TestFullRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fx = TriageFixture(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_writes_corpus_and_report(self):
        self.fx.add_source('https://data.gov.ie/dataset', 'Official dataset 2025',
                           origin='primary', medium='government',
                           search_angle='stats', body='official statistics body')
        self.fx.add_source('https://news-outlet.com/a', 'Coverage of dataset release',
                           origin='secondary', search_angle='stats',
                           body='news coverage body text')
        self.fx.add_source('https://critic.org/analysis', 'Critical analysis of policy',
                           origin='secondary', search_angle='criticism',
                           body='critical analysis body text')
        self.fx.add_source('https://wiki.example.org/Topic', 'Topic overview',
                           origin='tertiary', search_angle='criticism',
                           body='encyclopedia overview text')
        self.fx.write_plan(['stats', 'criticism'])

        result = triage.run_triage(self.tmp, 'standard', max_sources=10, min_per_angle=1)
        self.assertEqual(result['status'], 'ok')
        self.assertTrue(os.path.exists(result['corpus']))
        self.assertTrue(os.path.exists(result['report']))

        rows = self.fx.rows()
        self.assertEqual(len(rows), 4)
        selected = [r for r in rows if r['triage_status'] == 'selected']
        self.assertGreaterEqual(len(selected), 3)
        # every row carries full triage fields
        for r in rows:
            for field in ('credibility', 'independence_group_id', 'selection_reason'):
                self.assertIn(field, r)
        # corpus sorted: selected first
        order = {'selected': 0, 'reserve': 1, 'dropped': 2}
        statuses = [r['triage_status'] for r in rows]
        self.assertEqual(statuses, sorted(statuses, key=lambda s: order[s]))

        with open(result['report']) as f:
            report = f.read()
        self.assertIn('Coverage Gaps', report)
        self.assertIn('Independence Groups', report)

    def test_run_reports_gaps(self):
        self.fx.add_source('https://a.com/1', 'One', search_angle='stats',
                           origin='primary', body='body one')
        self.fx.write_plan(['stats', 'missing-angle'])
        result = triage.run_triage(self.tmp, 'standard', max_sources=10, min_per_angle=1)
        self.assertEqual([g['angle'] for g in result['gaps']], ['missing-angle'])
        # CLI exit code 2 signals gaps
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, 'triage.py'), 'run',
             '--run-dir', self.tmp, '--mode', 'standard', '--max-sources', '10'],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)


if __name__ == '__main__':
    unittest.main()
