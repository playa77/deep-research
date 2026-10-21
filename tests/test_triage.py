#!/usr/bin/env python3
"""Tests for triage.py: dedupe, syndication, clustering, selection, gaps."""

import hashlib
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from boundary_fixtures import processing_fixture

SCRIPTS = os.path.join(os.path.dirname(__file__), '..', 'scripts')
sys.path.insert(0, SCRIPTS)

from citation_manager import canonicalize_locator, compute_source_id  # noqa: E402
import triage  # noqa: E402


class TriageFixture:
    """Builds a fake run directory with agent fragments, raw files, and plan."""

    def __init__(self, root: str):
        self.root = root
        processing_fixture(root)
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

    def review_lineage(self, sources):
        ids = [s['source_id'] for s in sources[:2]]
        raw = {s['source_id']: Path(self.root, 'acquisition', s['raw_file']).read_bytes()
               for s in sources[:2]}
        record = dict(source_ids=ids, relation='shared_origin',
                      reviewer='synthetic fixture reviewer', reason='Synthetic fixture lineage review',
                      raw_sha256={sid: hashlib.sha256(raw[sid]).hexdigest() for sid in ids},
                      passages={sid: raw[sid].decode().split('---', 2)[-1].strip() for sid in ids})
        Path(self.root, 'triage/lineage.json').write_text(json.dumps([record]))

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
                                   origin='primary', body='identical body content here ' * 20)
        sid_b = self.fx.add_source('https://b.com/copy', 'Report B copy',
                                   body='identical body content here ' * 20)
        sources = triage.load_sources(self.tmp)
        triage.step_dedupe(sources, self.tmp)
        dup = self.fx.by_title(sources, 'Report B copy')
        orig = self.fx.by_title(sources, 'Report A')
        self.assertEqual(dup['duplicate_of'], orig['source_id'])
        self.assertEqual(orig['source_id'], sid_a)

    def test_long_shared_prefix_does_not_delete_different_documents(self):
        prefix = 'Shared introductory wording before unique substantive material. ' * 180
        self.fx.add_source('https://a.org/Mink', 'Mink', body=prefix + 'Original archival entry A.')
        self.fx.add_source('https://b.org/Mink', 'Mink', body=prefix + 'Distinct archival entry B.')
        sources = triage.load_sources(self.tmp)
        triage.step_dedupe(sources, self.tmp)
        self.assertFalse(any(s.get('duplicate_of') for s in sources))
        self.assertNotEqual(sources[0]['content_hash'], sources[1]['content_hash'])

    def test_short_identical_error_messages_and_missing_bodies_are_not_documents(self):
        for domain, body in (('a.org', 'Access denied'), ('b.org', 'Access denied'),
                             ('c.org', None), ('d.org', None)):
            self.fx.add_source('https://' + domain + '/Mink', 'Mink', body=body)
        sources = triage.load_sources(self.tmp)
        triage.step_dedupe(sources, self.tmp)
        self.assertFalse(any(s.get('duplicate_of') or s.get('lineage_with') for s in sources))

    def test_content_case_is_preserved_for_exact_duplicate_decisions(self):
        prefix = 'The archival text describes a particular subject in detail. ' * 10
        self.fx.add_source('https://a.org/1', 'A', body=prefix + 'US')
        self.fx.add_source('https://b.org/2', 'B', body=prefix + 'us')
        sources = triage.load_sources(self.tmp)
        triage.step_dedupe(sources, self.tmp)
        self.assertFalse(any(s.get('duplicate_of') for s in sources))

    def test_same_title_is_only_a_review_lead(self):
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
        self.assertEqual(ids, set())
        self.assertTrue(s1.get('similarity_candidates'))

    def test_three_independent_same_title_sources_are_not_syndication(self):
        self.fx.add_source('https://a.com/one', 'Same Title Here', body='body one')
        self.fx.add_source('https://b.com/two', 'Same Title Here', body='body two')
        self.fx.add_source('https://c.example.org/x', 'Same Title Here', body='body three')
        sources = triage.load_sources(self.tmp)
        triage.step_dedupe(sources, self.tmp)
        # a.com and c.example.org differ; b.com pairs with one of them — all
        # three share a title so all pair cross-domain; assert no same-domain pair
        # was flagged *because of domain* (clustering handles domains).
        syndicated = {s['source_id'] for s in sources if s.get('syndication_with')}
        self.assertEqual(syndicated, set())
        triage.step_cluster(sources, self.tmp)
        self.assertEqual(len({s['independence_group_id'] for s in sources}), 3)


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
        self.fx.review_lineage(sources)
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

    def test_stale_lineage_or_fabricated_body_passage_blocks_triage(self):
        self.fx.add_source('https://a.org/1', 'Mink', body='Original body with attribution.')
        self.fx.add_source('https://b.org/2', 'Mink', body='Different body with attribution.')
        sources = triage.load_sources(self.tmp)
        self.fx.review_lineage(sources)
        path = Path(self.tmp, 'triage/lineage.json')
        original = json.loads(path.read_text())
        sid = sources[0]['source_id']
        for field, value, error in (('raw_sha256', '0' * 64, 'stale lineage'),
                                     ('passages', 'Fabricated attribution.', 'passage missing')):
            record = json.loads(json.dumps(original))
            record[0][field][sid] = value
            path.write_text(json.dumps(record))
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, error):
                triage.step_dedupe(sources, self.tmp)


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

    def test_reviewed_shared_origin_retains_unique_material(self):
        # Shared origin limits corroboration, but unique passages remain usable.
        self.fx.add_source('https://blogs.example.org/story', 'The Big Finding',
                           origin='secondary', body='secondary write-up text')
        self.fx.add_source('https://data.gov.ie/report', 'The Big Finding',
                           origin='primary', body='primary record text')
        self.fx.review_lineage(triage.load_sources(self.tmp))
        sources = self._prepare()
        triage.step_select(sources, self.tmp, max_sources=10)
        kept = [s for s in sources if s['triage_status'] == 'selected']
        dropped = [s for s in sources if s['triage_status'] == 'dropped']
        self.assertEqual(len(kept), 2)
        self.assertEqual(len(dropped), 0)
        self.assertEqual(len({s['independence_group_id'] for s in kept}), 1)

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

    def test_low_credibility_reserve_does_not_consume_selected_capacity(self):
        sources = [
            {'source_id': 'low', 'origin': 'primary', 'credibility': 35},
            {'source_id': 'usable', 'origin': 'secondary', 'credibility': 70},
        ]
        triage.step_select(sources, self.tmp, max_sources=1)
        self.assertEqual(sources[0]['triage_status'], 'reserve')
        self.assertIn('verify before use', sources[0]['selection_reason'])
        self.assertEqual(sources[1]['triage_status'], 'selected')

    def test_planned_coverage_precedes_filling_by_global_rank(self):
        self.fx.write_plan(['general', 'variant-cluster'])
        sources = [
            {'source_id': f'general-{i}', 'origin': 'primary',
             'credibility': 90, 'search_angle': 'general'} for i in range(5)
        ] + [
            {'source_id': f'variant-{i}', 'origin': 'secondary',
             'credibility': 60, 'search_angle': 'variant-cluster'} for i in range(2)
        ]
        triage.step_select(sources, self.tmp, max_sources=4)
        selected = [s for s in sources if s['triage_status'] == 'selected']
        self.assertEqual(len(selected), 4)
        self.assertEqual(sum(s['search_angle'] == 'variant-cluster' for s in selected), 2)
        self.assertEqual(triage.step_gaps(sources, self.tmp), [])

    def test_insufficient_capacity_covers_each_angle_before_second_source(self):
        self.fx.write_plan(['general', 'variant-cluster'])
        sources = [
            {'source_id': f'general-{i}', 'origin': 'primary',
             'credibility': 90, 'search_angle': 'general'} for i in range(3)
        ] + [
            {'source_id': f'variant-{i}', 'origin': 'secondary',
             'credibility': 60, 'search_angle': 'variant-cluster'} for i in range(2)
        ]
        triage.step_select(sources, self.tmp, max_sources=2)
        selected = [s for s in sources if s['triage_status'] == 'selected']
        self.assertEqual({s['search_angle'] for s in selected}, {'general', 'variant-cluster'})
        gaps = triage.step_gaps(sources, self.tmp)
        self.assertEqual(len(gaps), 2)
        self.assertTrue(all(g['next_action'] == 'review_corpus_cap' for g in gaps))
        self.assertTrue(all(g['additional_sources_needed'] == 0 for g in gaps))

    def test_custom_minimum_is_used_for_selection(self):
        self.fx.write_plan(['general', 'variant-cluster'])
        sources = [
            {'source_id': f'general-{i}', 'origin': 'primary',
             'credibility': 90, 'search_angle': 'general'} for i in range(3)
        ] + [{'source_id': 'variant', 'origin': 'secondary',
              'credibility': 60, 'search_angle': 'variant-cluster'}]
        triage.step_select(sources, self.tmp, max_sources=3, min_per_angle=1)
        self.assertEqual(triage.step_gaps(sources, self.tmp, min_per_angle=1), [])
        self.assertEqual(sum(s['triage_status'] == 'selected' for s in sources), 3)

    def test_coverage_keeps_unique_derivatives_but_never_promotes_low_credibility(self):
        self.fx.write_plan(['general', 'variant-cluster'])
        sources = [
            {'source_id': 'general', 'origin': 'primary', 'credibility': 90,
             'search_angle': 'general'},
            {'source_id': 'variant', 'origin': 'primary', 'credibility': 80,
             'search_angle': 'variant-cluster', 'lineage_with': ['derivative']},
            {'source_id': 'derivative', 'origin': 'secondary', 'credibility': 80,
             'search_angle': 'variant-cluster', 'lineage_with': ['variant']},
            {'source_id': 'duplicate', 'origin': 'primary', 'credibility': 90,
             'search_angle': 'variant-cluster', 'duplicate_of': 'variant'},
            {'source_id': 'weak', 'origin': 'primary', 'credibility': 39.9,
             'search_angle': 'variant-cluster'},
        ]
        triage.step_select(sources, self.tmp, max_sources=10)
        by_id = {s['source_id']: s for s in sources}
        self.assertEqual(by_id['variant']['triage_status'], 'selected')
        self.assertEqual(by_id['derivative']['triage_status'], 'selected')
        self.assertEqual(by_id['duplicate']['triage_status'], 'dropped')
        self.assertEqual(by_id['weak']['triage_status'], 'reserve')
        self.assertNotIn('variant-cluster', [g['angle'] for g in triage.step_gaps(sources, self.tmp)])

    def test_coverage_keeps_best_sources_per_angle_then_fills_by_rank(self):
        self.fx.write_plan(['general', 'variant-cluster'])
        sources = [
            {'source_id': 'best', 'origin': 'primary', 'credibility': 95,
             'search_angle': 'general'},
            {'source_id': 'second', 'origin': 'primary', 'credibility': 90,
             'search_angle': 'general'},
            {'source_id': 'extra', 'origin': 'primary', 'credibility': 85,
             'search_angle': 'general'},
            {'source_id': 'lower', 'origin': 'secondary', 'credibility': 75,
             'search_angle': 'general'},
            {'source_id': 'variant-best', 'origin': 'primary', 'credibility': 70,
             'search_angle': 'variant-cluster'},
            {'source_id': 'variant-second', 'origin': 'secondary', 'credibility': 60,
             'search_angle': 'variant-cluster'},
            {'source_id': 'variant-lower', 'origin': 'secondary', 'credibility': 50,
             'search_angle': 'variant-cluster'},
        ]
        triage.step_select(sources, self.tmp, max_sources=5)
        self.assertEqual({s['source_id'] for s in sources if s['triage_status'] == 'selected'},
                         {'best', 'second', 'extra', 'variant-best', 'variant-second'})
        for s in sources:
            if s['triage_status'] == 'selected':
                self.assertIn(f"credibility={s['credibility']}", s['selection_reason'])

    def test_uncapped_selection_keeps_all_eligible_sources(self):
        self.fx.write_plan(['general', 'variant-cluster'])
        sources = [
            {'source_id': 'core', 'origin': 'primary', 'credibility': 95,
             'search_angle': 'general'},
            {'source_id': 'critical', 'origin': 'secondary', 'credibility': 70,
             'search_angle': 'unplanned-counterevidence'},
            {'source_id': 'boundary', 'origin': 'secondary', 'credibility': 40,
             'search_angle': 'variant-cluster'},
            {'source_id': 'weak', 'origin': 'primary', 'credibility': 39.9,
             'search_angle': 'variant-cluster'},
        ]
        triage.step_select(sources, self.tmp, max_sources=10)
        self.assertEqual({s['source_id'] for s in sources if s['triage_status'] == 'selected'},
                         {'core', 'critical', 'boundary'})


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

    def test_missing_eligible_sources_requests_only_the_actual_shortfall(self):
        self.fx.write_plan(['variant-cluster'])
        sources = [
            {'source_id': 'selected', 'search_angle': 'variant-cluster',
             'triage_status': 'selected'},
            {'source_id': 'untrusted', 'search_angle': 'variant-cluster',
             'triage_status': 'reserve', 'credibility': 35,
             'selection_reason': 'credibility 35 < 40: verify before use'},
            {'source_id': 'copy', 'search_angle': 'variant-cluster',
             'triage_status': 'dropped', 'selection_reason': 'exact duplicate'},
        ]
        gap, = triage.step_gaps(sources, self.tmp)
        self.assertEqual(gap['selected_sources'], 1)
        self.assertEqual(gap['eligible_sources'], 1)
        self.assertEqual(gap['reserve_sources'], 1)
        self.assertEqual(gap['dropped_sources'], 1)
        self.assertEqual(gap['additional_sources_needed'], 1)
        self.assertEqual(gap['next_action'], 'delta_acquisition')

    def test_plan_ids_and_names_refer_to_the_same_angle(self):
        self.fx.write_plan(['variant-cluster'])
        sources = [
            {'source_id': 'one', 'search_angle': 'angle-01', 'triage_status': 'selected'},
            {'source_id': 'two', 'search_angle': 'variant-cluster', 'triage_status': 'selected'},
        ]
        self.assertEqual(triage.step_gaps(sources, self.tmp), [])


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
        self.assertEqual(result['status'], 'coverage_gaps')
        with open(result['result']) as f:
            self.assertEqual(json.load(f), result)
        # CLI exit code 2 signals gaps
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, 'triage.py'), 'run',
             '--run-dir', self.tmp, '--mode', 'standard', '--max-sources', '10'],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)

    def test_twelve_same_name_reference_pages_do_not_create_false_gaps(self):
        from fact_check import validate_schema
        angles = ['distribution-frequency-data', 'medieval-historical-attestations',
                  'critical-folk-etymology']
        domains = ['duden.de', 'dwds.de', 'forebears.io', 'geneanet.org',
                   'wiktionary.org', 'dastelefonbuch.de', 'wikipedia.org', 'geogen.de',
                   'archive.org', 'cerl.org', 'deutsche-biographie.de', 'uni.example.de']
        for i, domain in enumerate(domains):
            self.fx.add_source('https://' + domain + '/Mink', 'Mink', origin='primary',
                               search_angle=angles[i % 3],
                               body=(f'Distinct source {domain} archival and statistical material. ' * 12))
        self.fx.write_plan(angles)
        result = triage.run_triage(self.tmp, 'deep', max_sources=70, min_per_angle=2)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['counts'], {'selected': 12, 'reserve': 0, 'dropped': 0})
        for row in self.fx.rows():
            validate_schema(row, 'corpus.schema.json')
        self.assertEqual(len({s['independence_group_id'] for s in self.fx.rows()}), 12)
        self.assertEqual(result['similarity_candidate_sources'], 12)

    def test_delta_reservation_survives_retriage_and_a_fresh_process(self):
        from search_fixtures import search_record
        self.fx.write_plan(['stats'])
        self.fx.add_source('https://a.org/one', 'One', origin='primary',
                           search_angle='stats', body='Unique available record.')
        query = search_record(Path(self.tmp), angle='stats')
        Path(self.tmp, 'acquisition/query_log.jsonl').write_text(json.dumps(query) + '\n')
        triage.run_triage(self.tmp, 'standard', max_sources=10, min_per_angle=2)
        first = triage.begin_delta(self.tmp)
        self.assertEqual(first['angles'], ['stats'])
        ledger = Path(self.tmp, 'triage/delta_attempt.json').read_bytes()
        triage.run_triage(self.tmp, 'standard', max_sources=10, min_per_angle=2)
        proc = subprocess.run([sys.executable, os.path.join(SCRIPTS, 'triage.py'),
                               'begin-delta', '--run-dir', self.tmp], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(Path(self.tmp, 'triage/delta_attempt.json').read_bytes(), ledger)

    def test_delta_rejects_stale_decisions_and_capacity_constraints(self):
        self.fx.write_plan(['stats', 'critical'])
        triage.run_triage(self.tmp, 'standard', max_sources=1, min_per_angle=2)
        with self.assertRaisesRegex(ValueError, 'capacity'):
            triage.begin_delta(self.tmp)
        self.fx.write_plan(['changed'])
        with self.assertRaisesRegex(ValueError, 'stale triage'):
            triage.begin_delta(self.tmp)
        self.assertFalse(Path(self.tmp, 'triage/delta_attempt.json').exists())

    def test_failed_retriage_invalidates_a_previous_success_result(self):
        self.fx.write_plan(['stats'])
        triage.run_triage(self.tmp, 'standard', max_sources=10, min_per_angle=1)
        Path(self.tmp, 'acquisition/query_plan.md').write_text('No machine-readable plan.')
        with self.assertRaisesRegex(ValueError, 'planned angles'):
            triage.run_triage(self.tmp, 'standard', max_sources=10, min_per_angle=1)
        result = json.loads(Path(self.tmp, 'triage/triage_result.json').read_text())
        self.assertEqual(result['status'], 'blocked')
        with self.assertRaisesRegex(ValueError, 'stale triage'):
            triage.begin_delta(self.tmp)

    def test_gaps_subcommand_matches_full_triage(self):
        self.fx.add_source('https://a.com/1', 'One', search_angle='stats',
                           origin='primary', body='first unique source')
        self.fx.add_source('https://b.com/2', 'Two', search_angle='stats',
                           origin='primary', body='second unique source')
        self.fx.write_plan(['stats', 'missing-angle'])
        expected = triage.run_triage(self.tmp, 'standard', max_sources=40, min_per_angle=2)
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, 'triage.py'), 'gaps',
             '--run-dir', self.tmp], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(proc.stdout), expected['gaps'])

    def test_gaps_subcommand_honors_custom_limits(self):
        self.fx.add_source('https://a.com/1', 'One', search_angle='stats',
                           origin='primary', body='unique source')
        self.fx.write_plan(['stats'])
        expected = triage.run_triage(self.tmp, 'quick', max_sources=1, min_per_angle=1)
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, 'triage.py'), 'gaps',
             '--run-dir', self.tmp, '--mode', 'quick', '--max-sources', '1',
             '--min-per-angle', '1'], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(proc.stdout), expected['gaps'])

    def test_real_gap_persists_until_another_eligible_source_arrives(self):
        self.fx.write_plan(['variant-cluster'])
        self.fx.add_source('https://a.com/one', 'Original study',
                           search_angle='variant-cluster', origin='primary', body='original body')
        before = triage.run_triage(self.tmp, 'standard', max_sources=10, min_per_angle=2)
        self.assertEqual(before['status'], 'coverage_gaps')
        self.assertEqual(before['gaps'][0]['additional_sources_needed'], 1)
        self.fx.add_source('https://b.org/two', 'Independent dataset',
                           search_angle='variant-cluster', origin='primary', body='independent data')
        after = triage.run_triage(self.tmp, 'standard', max_sources=10, min_per_angle=2)
        self.assertEqual(after['status'], 'ok')
        self.assertEqual(after['gaps'], [])
        self.assertEqual(after['counts']['selected'], 2)
        repeated = triage.run_triage(self.tmp, 'standard', max_sources=10, min_per_angle=2)
        self.assertEqual(after, repeated)

    def test_impossible_capacity_is_reported_without_changing_limits(self):
        self.fx.write_plan(['general', 'variant-cluster'])
        result = triage.run_triage(self.tmp, 'standard', max_sources=3, min_per_angle=2)
        self.assertEqual(result['status'], 'coverage_gaps')
        self.assertEqual(result['max_sources'], 3)
        self.assertEqual(result['minimum_per_angle'], 2)
        self.assertEqual(result['coverage_capacity'],
                         {'minimum_required_sources': 4, 'sufficient': False})
        with open(result['report']) as f:
            self.assertIn('Capacity constraint:', f.read())

    def test_nonpositive_cli_limits_are_rejected(self):
        for flag in ('--max-sources', '--min-per-angle'):
            for value in ('0', '-1'):
                with self.subTest(flag=flag, value=value):
                    proc = subprocess.run(
                        [sys.executable, os.path.join(SCRIPTS, 'triage.py'), 'run',
                         '--run-dir', self.tmp, flag, value], capture_output=True, text=True)
                    self.assertEqual(proc.returncode, 2)
                    self.assertIn('must be a positive integer', proc.stderr)


if __name__ == '__main__':
    unittest.main()
