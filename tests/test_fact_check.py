"""Adversarial release-contract tests. Approvals below are synthetic fixtures,
never a method for generating real research review records.
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import fact_check as fc
from citation_manager import compute_source_id
from evidence_store import compute_evidence_id


def rows(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(d) + '\n' for d in data), encoding='utf-8')


def checks(names):
    return {name: {'result': 'pass', 'rationale': f'Synthetic fixture review of {name}; see test setup.'} for name in names}


def persist_retrieval(run, source, body):
    sid = source['source_id']
    original = f'original/{sid}.txt'
    path = run / 'acquisition' / original
    path.parent.mkdir(exist_ok=True)
    path.write_text(body)
    source['retrieval_record'] = f'retrieval/{sid}.json'
    record = dict(source_id=sid, requested_url=source['raw_url'], final_url=source['raw_url'],
                  retrieved_at='2026-10-19T00:00:00Z', tool='fixture-tool', execution_ref='synthetic-call-' + sid,
                  kind='tool_response', http_status=None, content_file=original,
                  content_sha256=fc.sha(path.read_bytes()), extraction_method='Synthetic fixture plain text copy')
    target = run / 'acquisition' / source['retrieval_record']
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(record))


class ContractFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        for folder in ('acquisition/raw', 'report', 'qa'):
            (self.run / folder).mkdir(parents=True)
        self.url = 'https://register.example/trial'
        self.sid = compute_source_id(self.url)
        self.quote = 'The trial enrolled 100 participants.'
        self.source = dict(source_id=self.sid, canonical_locator=self.url, raw_url=self.url,
                           title='Trial record', origin='primary', medium='government',
                           metadata_status='url_verified', registered_at='2026-10-19T00:00:00Z',
                           retrieved='2026-10-19', published='2026-10-18', raw_file='raw/trial.md',
                           credibility=90, independence_group_id='G001', triage_status='selected',
                           selection_reason='Original trial enrollment record')
        self.ev = dict(evidence_id=compute_evidence_id(self.sid, self.quote, 'Enrollment'),
                       source_id=self.sid, quote=self.quote, locator='Enrollment',
                       evidence_type='direct_quote', captured_at='2026-10-19T00:00:00Z')
        self.raw_path = self.run / 'acquisition/raw/trial.md'
        self.raw_path.write_text('---\ntitle: Trial record\n---\nEnrollment\n' + self.quote + '\n', encoding='utf-8')
        persist_retrieval(self.run, self.source, self.quote)
        self.report_path = self.run / 'report/report.md'
        self.report_path.write_text('## Finding\nThe trial enrolled 100 participants [1].\n\n## Bibliography\n[1] [Trial record](' + self.url + '). URL: <' + self.url + '>\n', encoding='utf-8')
        (self.run / 'run_manifest.json').write_text(json.dumps({'mode': 'standard'}), encoding='utf-8')
        rows(self.run / 'triage/corpus.jsonl', [self.source])
        rows(self.run / 'evidence/evidence.jsonl', [self.ev])
        self.query = {'query_text': 'trial enrollment correction retraction discrepancy', 'tool': 'web_search',
                      'query_id': 'q_test', 'agent': 'fixture-agent', 'ts': '2026-10-19T00:00:00Z',
                      'search_angle': 'counterevidence', 'result_count': 0, 'top_urls': [],
                      'notes': 'Synthetic search fixture, not a real search.'}
        rows(self.run / 'acquisition/query_log.jsonl', [self.query])
        self.doc, warnings = fc.prepare(self.run)
        self.assertEqual(warnings, [])
        self.doc['author_id'] = 'writer'
        self.doc['reviewers'] = [dict(reviewer_id=rid, role=role, identity='fixture-model', execution_ref=rid + '-session')
                                 for rid, role in [('writer', 'author'), ('checker', 'verifier'), ('attacker', 'red_team')]]
        for u in self.doc['coverage']:
            u.update(kind='non_assertive', reason='Heading or bibliography entry; identity mapped separately.')
            if u['line'] == 2:
                u.update(kind='claims', claim_ids=['C1'], reason='Enrollment assertion.')
        self.doc['coverage_review'].update(reviewer_id='attacker', verdict='approved', checks=checks(fc.COVERAGE_CHECKS))
        self.doc['source_reviews'] = [dict(source_id=self.sid, reviewer_id='checker',
                                          inputs_sha256=fc.digest(self.doc['inputs']), verdict='approved',
                                          origin_key='trial:original', checks=checks(fc.SOURCE_CHECKS))]
        self.claim = dict(claim_id='C1', text='The trial enrolled 100 participants.',
                          locations=[{'line': 2, 'excerpt': 'The trial enrolled 100 participants [1].'}],
                          kind='factual', importance='minor', as_of='2026-10-19', qualification='',
                          evidence_links=[dict(evidence_id=self.ev['evidence_id'], relation='supports',
                                               rationale='The original enrollment record gives the enrolled count.')],
                          premise_ids=[], countersearch_ids=[fc.digest(self.query)],
                          counterevidence='Synthetic fixture search found no enrollment correction.', calculations=[])
        self.doc['claims'] = [self.claim]
        self.sign_claims()

    def sign_claims(self):
        # Test-only simulated reviews. Production tooling must never auto-approve.
        for c in self.doc['claims']:
            for field, rid, required in [('verification', 'checker', fc.CLAIM_CHECKS), ('red_team', 'attacker', fc.ATTACK_CHECKS)]:
                c[field] = dict(reviewer_id=rid, claim_sha256=fc.claim_digest(c), inputs_sha256=fc.digest(self.doc['inputs']),
                                verdict='approved', checks=checks(required), link_reviews=[
                                    dict(evidence_id=l['evidence_id'], relation=l['relation'], verdict='approved',
                                         rationale='Synthetic fixture link inspected against complete source context.') for l in c['evidence_links']])

    def blocked(self, needle=None):
        try:
            result = fc.verify(self.run, self.doc)
            self.assertEqual(result['status'], 'blocked', result)
            errors = ' '.join(result['errors'])
        except fc.ContractError as exc:
            errors = str(exc)
        if needle:
            self.assertIn(needle, errors)


class ContractTests(ContractFixture):
    def test_valid_review_contract_passes_without_claiming_truth(self):
        result = fc.verify(self.run, self.doc)
        self.assertEqual(result['status'], 'contract_pass', result)
        self.assertIn('not proof of truth', result['assurance'])

    def test_prepare_never_approves(self):
        doc, _ = fc.prepare(self.run)
        self.assertEqual(doc['claims'], [])
        self.assertTrue(all(c['kind'] == 'pending' for c in doc['coverage']))
        with self.assertRaises(fc.ContractError):
            fc.verify(self.run, doc)

    def test_empty_claims_fail(self):
        self.doc['claims'] = []
        self.blocked()

    def test_deleted_coverage_line_fails(self):
        self.doc['coverage'].pop()
        self.blocked('coverage incomplete')

    def test_pending_coverage_fails(self):
        self.doc['coverage'][1]['kind'] = 'pending'
        self.blocked('unreviewed')

    def test_claim_hidden_as_nonassertive_conflicts_with_location(self):
        self.doc['coverage'][1]['kind'] = 'non_assertive'
        self.blocked('unjustified exclusion')

    def test_report_edit_invalidates_reviews(self):
        self.report_path.write_text(self.report_path.read_text() + 'Cats fly.\n')
        self.blocked('snapshot changed')

    def test_raw_edit_invalidates_reviews(self):
        self.raw_path.write_text(self.raw_path.read_text() + 'Correction: the count is provisional.\n')
        self.blocked('snapshot changed')

    def test_refreshing_input_hash_alone_does_not_reapprove(self):
        self.raw_path.write_text(self.raw_path.read_text() + 'New context.\n')
        self.doc['inputs'] = fc.bundle(self.run)[0]
        self.blocked('stale evidence/input review')

    def test_claim_edit_invalidates_reviews(self):
        self.claim['text'] = 'The trial enrolled 1000 participants.'
        self.blocked('stale claim review')

    def test_missing_claim_check_fails(self):
        del self.claim['verification']['checks']['polarity_modality']
        self.blocked()

    def test_failed_red_team_fails(self):
        self.claim['red_team']['checks']['wrong_number_unit_denominator']['result'] = 'fail'
        self.blocked('not passed')

    def test_uncertain_review_fails(self):
        self.claim['verification']['verdict'] = 'uncertain'
        self.blocked('not approved')

    def test_author_cannot_verify(self):
        self.claim['verification']['reviewer_id'] = 'writer'
        self.blocked('author cannot approve')

    def test_reviewer_session_cannot_be_reused_under_different_id(self):
        self.doc['reviewers'][2]['execution_ref'] = self.doc['reviewers'][1]['execution_ref']
        self.blocked('distinct sessions')

    def test_missing_link_red_team_fails(self):
        self.claim['red_team']['link_reviews'] = []
        self.blocked('every evidence link')

    def test_changed_relation_fails(self):
        self.claim['red_team']['link_reviews'][0]['relation'] = 'context'
        self.blocked('relationship rejected')

    def test_missing_anchor_fails(self):
        self.doc['anchors'] = []
        self.blocked('missing evidence or exact anchor')

    def test_wrong_quote_offsets_fail(self):
        self.doc['anchors'][0]['start'] += 1
        self.blocked('fabricated or stale quote')

    def test_quote_only_in_agent_annotation_is_not_evidence(self):
        self.raw_path.write_text('> [KEY PASSAGE] "' + self.quote + '"\n')
        with self.assertRaises(fc.ContractError):
            fc.anchor_for(self.run, self.source, self.ev)

    def test_quote_in_frontmatter_is_not_evidence(self):
        self.raw_path.write_text('---\ntitle: ' + self.quote + '\n---\nUnrelated text.\n')
        with self.assertRaises(fc.ContractError):
            fc.anchor_for(self.run, self.source, self.ev)

    def test_quote_ambiguity_requires_manual_offsets(self):
        self.raw_path.write_text(self.quote + '\n' + self.quote)
        with self.assertRaises(fc.ContractError):
            fc.anchor_for(self.run, self.source, self.ev)

    def test_path_traversal_fails(self):
        self.source['raw_file'] = '../../outside.md'
        rows(self.run / 'triage/corpus.jsonl', [self.source])
        self.blocked('escapes run')

    def test_symlink_escape_fails(self):
        with tempfile.TemporaryDirectory() as out:
            target = Path(out) / 'outside.md'
            target.write_text(self.quote)
            self.raw_path.unlink()
            self.raw_path.symlink_to(target)
            self.blocked('escapes run')

    def test_major_single_origin_fails(self):
        self.claim['importance'] = 'major'
        self.sign_claims()
        self.blocked('fewer than 3 independent origins')

    def test_renaming_claim_to_speculation_does_not_bypass(self):
        self.claim['kind'] = 'speculation'
        self.sign_claims()
        self.blocked('reviewed premises')

    def test_attribution_requires_label_in_report(self):
        self.claim['kind'] = 'attribution'
        self.sign_claims()
        self.blocked('attribution must be explicit')

    def test_missing_countersearch_fails(self):
        self.claim['countersearch_ids'] = []
        self.sign_claims()
        self.blocked()

    def test_unknown_query_hash_fails(self):
        self.claim['countersearch_ids'] = ['0' * 64]
        self.sign_claims()
        self.blocked('countersearch log references')

    def test_duplicate_claim_id_fails(self):
        other = deepcopy(self.claim)
        other['text'] = 'Different assertion.'
        self.doc['claims'].append(other)
        self.blocked('duplicate claim_id')

    def test_unknown_schema_field_fails(self):
        self.doc['waive_failures'] = True
        self.blocked()

    def test_incorrect_bibliography_url_fails(self):
        self.report_path.write_text(self.report_path.read_text().replace(self.url, 'https://wrong.example/'))
        self.blocked('URL disagrees')

    def test_source_review_missing_fails(self):
        self.doc['source_reviews'] = []
        self.blocked('source not reviewed')

    def test_unselected_source_fails(self):
        self.source['triage_status'] = 'reserve'
        rows(self.run / 'triage/corpus.jsonl', [self.source])
        self.blocked('not reviewed/selected')

    def test_empty_or_missing_bundle_fails(self):
        (self.run / 'evidence/evidence.jsonl').write_text('')
        self.blocked('must be nonempty')

    def test_malformed_json_and_duplicate_keys_rejected(self):
        for text in ('{"a":1,"a":2}', '{', '{"x":NaN}', '{"x":Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                fc.parse_json(text)

    def test_cli_failure_replaces_stale_success(self):
        result_path = self.run / 'qa/fact_check_result.json'
        result_path.write_text('{"status":"contract_pass"}')
        (self.run / 'qa/fact_check.json').write_text('{')
        result = subprocess.run([sys.executable, str(SCRIPTS / 'fact_check.py'), 'verify', '--run-dir', str(self.run)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result_path.read_text())['status'], 'blocked')

    def test_strict_legacy_command_requires_full_contract(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'verify_claim_support.py'), 'verify', '--dir', str(self.run / 'evidence'), '--strict'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['status'], 'blocked')

    def test_mutual_premise_cycle_fails(self):
        second = deepcopy(self.claim)
        second.update(claim_id='C2', premise_ids=['C1'])
        self.claim['premise_ids'] = ['C2']
        self.doc['claims'].append(second)
        self.doc['coverage'][1]['claim_ids'].append('C2')
        self.sign_claims()
        self.blocked('cyclic premise')


class ArithmeticTests(unittest.TestCase):
    def calc(self, op, tokens, expected, places=2, quotes=None):
        evs = {str(n): {'quote': q} for n, q in enumerate(quotes or tokens)}
        calc = dict(operation=op, inputs=[dict(evidence_id=str(n), token=t, scale='one') for n, t in enumerate(tokens)],
                    decimal_places=places, rounding='half_even', reported_value=expected)
        return fc.calculate(calc, evs)

    def test_exact_decimal_percentage_and_growth(self):
        self.assertEqual(self.calc('percentage', ['1', '3'], '33.33'), '33.33')
        self.assertEqual(self.calc('percent_change', ['100', '125'], '25'), '25.00')
        self.assertEqual(self.calc('sum', ['0.1', '0.2'], '0.30'), '0.30')

    def test_wrong_denominator_and_wrong_output_fail(self):
        with self.assertRaises(fc.ContractError):
            self.calc('percentage', ['1', '4'], '33.33')

    def test_division_by_zero_fails(self):
        with self.assertRaises(ArithmeticError):
            self.calc('ratio', ['1', '0'], '0')

    def test_number_must_exist_as_whole_token(self):
        for quote in ('100', '12.5', 'item1', '1,000'):
            with self.subTest(quote=quote), self.assertRaises(fc.ContractError):
                self.calc('sum', ['1'], '1', quotes=[quote])

    def test_completed_years_respects_anniversary(self):
        self.assertEqual(self.calc('completed_years', ['2000-10-20', '2026-10-19'], '25', 0), '25')
        self.assertEqual(self.calc('elapsed_days', ['2024-02-28', '2024-03-01'], '2', 0), '2')

    def test_reversed_and_invalid_dates_fail(self):
        for pair in (['2026-10-19', '2000-10-20'], ['2024-02-30', '2026-01-01']):
            with self.subTest(pair=pair), self.assertRaises(ValueError):
                self.calc('elapsed_days', pair, '1')

    def test_nan_and_infinity_output_fail(self):
        for expected in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(expected=expected), self.assertRaises(fc.ContractError):
                self.calc('sum', ['1'], expected)



class AdditionalContractTests(ContractFixture):
    """Mutations requiring fresh synthetic signatures to exercise deeper gates."""

    def test_hidden_only_bibliography_url_blocks_release_after_fresh_reviews(self):
        self.report_path.write_text(self.report_path.read_text().replace(f'. URL: <{self.url}>', ''))
        self.refresh()
        self.blocked('display the full URL')

    def test_file_only_verdict_blocks_release_after_fresh_reviews(self):
        self.report_path.write_text(self.report_path.read_text() + '\nVerdict: see qa/fact_check_result.json\n')
        self.refresh()
        self.blocked('verdict must state the outcome')

    def test_collapsed_bibliography_blocks_release_after_fresh_reviews(self):
        self.add_origins()
        self.report_path.write_text(self.report_path.read_text().replace('\n\n[2]', '\n[2]'))
        self.refresh()
        self.blocked('blank line')

    def test_generated_bibliography_matches_release_mapping(self):
        bibliography = subprocess.run([sys.executable, str(SCRIPTS / 'citation_manager.py'),
                                       'export-bibliography', '--dir', str(self.run)],
                                      capture_output=True, text=True, check=True).stdout
        prefix = self.report_path.read_text().split('## Bibliography')[0]
        self.report_path.write_text(prefix + bibliography)
        self.refresh()
        self.assertEqual(fc.verify(self.run, self.doc)['status'], 'contract_pass')

    def refresh(self):
        self.doc['inputs'] = fc.bundle(self.run)[0]
        self.doc['coverage'] = fc.inventory(self.report_path.read_text())
        for unit in self.doc['coverage']:
            unit.update(kind='non_assertive', reason='Synthetic heading or bibliography metadata.')
            if unit['line'] == 2:
                unit.update(kind='claims', claim_ids=[c['claim_id'] for c in self.doc['claims']])
        self.doc['coverage_review']['inputs_sha256'] = fc.digest(self.doc['inputs'])
        for review in self.doc['source_reviews']:
            review['inputs_sha256'] = fc.digest(self.doc['inputs'])
        sources = fc.load_rows(self.run / 'triage/corpus.jsonl')
        evs = fc.load_rows(self.run / 'evidence/evidence.jsonl')
        index = {s['source_id']: s for s in sources}
        self.doc['anchors'] = [fc.anchor_for(self.run, index[e['source_id']], e) for e in evs]
        self.sign_claims()

    def add_origins(self, count=3, same_group=False, same_domain=False, same_body=False, same_origin=False):
        sources = [self.source]
        evs = [self.ev]
        for n in range(2, count + 1):
            source = deepcopy(self.source)
            url = f'https://sub{n}.register.example/trial' if same_domain else f'https://independent{n}.example/trial'
            source.update(source_id=compute_source_id(url), canonical_locator=url, raw_url=url,
                          raw_file=f'raw/trial{n}.md', independence_group_id='G001' if same_group else f'G{n:03}')
            ev = deepcopy(self.ev)
            ev['source_id'] = source['source_id']
            ev['evidence_id'] = compute_evidence_id(ev['source_id'], ev['quote'], ev['locator'])
            if same_body:
                body = self.raw_path.read_text().split('---\n', 2)[-1]
                content = f'---\ntitle: Different header {n}\n---\n' + body
            else:
                content = self.quote + f'\nSeparate original investigation {n}.\n'
            (self.run / 'acquisition' / source['raw_file']).write_text(content)
            persist_retrieval(self.run, source, content)
            sources.append(source)
            evs.append(ev)
            self.claim['evidence_links'].append(dict(evidence_id=ev['evidence_id'], relation='supports',
                                                       rationale='Synthetic independently retrieved enrollment record.'))
            review = deepcopy(self.doc['source_reviews'][0])
            review.update(source_id=source['source_id'], origin_key='trial:original' if same_origin else f'trial:independent{n}')
            self.doc['source_reviews'].append(review)
        rows(self.run / 'triage/corpus.jsonl', sources)
        rows(self.run / 'evidence/evidence.jsonl', evs)
        excerpt = 'The trial enrolled 100 participants [' + ', '.join(str(n) for n in range(1, count + 1)) + '].'
        self.claim['locations'] = [{'line': 2, 'excerpt': excerpt}]
        self.report_path.write_text('## Finding\n' + excerpt + '\n\n## Bibliography\n' + '\n\n'.join(f'[{n}] [Trial record]({s["raw_url"]}). URL: <{s["raw_url"]}>' for n, s in enumerate(sources, 1)) + '\n')
        self.claim['importance'] = 'major'
        self.refresh()

    def test_three_reviewed_independent_origins_pass(self):
        self.add_origins()
        self.assertEqual(fc.verify(self.run, self.doc)['status'], 'contract_pass')

    def test_two_origins_only_pass_quick(self):
        self.add_origins(count=2)
        self.blocked('fewer than 3')
        (self.run / 'run_manifest.json').write_text('{"mode":"quick"}')
        self.refresh()
        self.assertEqual(fc.verify(self.run, self.doc)['status'], 'contract_pass')

    def test_copied_domains_groups_bodies_and_origins_do_not_multiply_support(self):
        for option in ('same_group', 'same_domain', 'same_body', 'same_origin'):
            with self.subTest(option=option):
                # Isolate each mutation rather than accumulating evidence rows.
                case = AdditionalContractTests()
                case.setUp()
                try:
                    case.add_origins(**{option: True})
                    case.blocked('independent origins')
                finally:
                    case.doCleanups()

    def test_new_numeric_value_fails_even_with_fresh_review_signatures(self):
        self.claim['text'] = 'The trial enrolled 1000 participants.'
        self.claim['locations'][0]['excerpt'] = 'The trial enrolled 1000 participants [1].'
        self.report_path.write_text(self.report_path.read_text().replace('100 participants', '1000 participants'))
        self.refresh()
        self.blocked('numeric literal/sign/magnitude mismatch')

    def test_missing_number_in_atomic_claim_cannot_hide_report_number(self):
        self.claim['text'] = 'The trial enrolled participants.'
        self.sign_claims()
        self.blocked('report numbers absent')

    def test_manifest_closeout_does_not_stale_scientific_review(self):
        manifest = fc.load_json(self.run / 'run_manifest.json')
        manifest.update(finished_at='2026-10-19T01:00:00Z', phases_completed=['qa'])
        (self.run / 'run_manifest.json').write_text(json.dumps(manifest))
        self.assertEqual(fc.verify(self.run, self.doc)['status'], 'contract_pass')

    def test_manifest_scope_change_invalidates_review(self):
        (self.run / 'run_manifest.json').write_text('{"mode":"standard","query":"different research question"}')
        self.blocked('snapshot changed')

    def test_no_automatic_semantic_approval_for_negation_roles_or_units(self):
        from verify_claim_support import compute_support_score
        pairs = [('The treatment reduces mortality.', 'The treatment does not reduce mortality.'),
                 ('Cats chase dogs.', 'Dogs chase cats.'),
                 ('Revenue was 25 million dollars.', 'Revenue was 25 billion dollars.'),
                 ('Revenue was 25 in 2024.', 'Revenue was 25 in 2025.')]
        for claim, quote in pairs:
            with self.subTest(claim=claim):
                self.assertNotEqual(compute_support_score(claim, [quote])[0], 'supported')
        self.assertNotEqual(fc.quantities(pairs[2][0]), fc.quantities(pairs[2][1]))
        self.assertNotEqual(fc.quantities('Declined by -5%.'), fc.quantities('Declined by 5%.'))
        self.assertNotEqual(fc.quantities('5 percentage points'), fc.quantities('5 percent'))

    def test_calculation_wrong_result_is_a_release_blocker(self):
        self.claim['calculations'] = [dict(operation='sum', inputs=[dict(evidence_id=self.ev['evidence_id'], token='100', scale='one')],
                                           decimal_places=0, rounding='half_even', reported_value='999', rendered='999',
                                           unit='participants', rationale='Synthetic invalid sum to test blocking.')]
        self.sign_claims()
        self.blocked('calculation mismatch')

    def test_unknown_evidence_cannot_be_borrowed_from_cited_source(self):
        self.claim['evidence_links'][0]['evidence_id'] = '0' * 16
        self.sign_claims()
        self.blocked('missing evidence or exact anchor')

    def test_forged_stored_support_flag_is_rejected_by_schema(self):
        self.claim['support_status'] = 'supported'
        self.blocked()

    def test_cli_pass_and_overwrite_refusal(self):
        path = self.run / 'qa/fact_check.json'
        path.write_text(json.dumps(self.doc))
        cmd = [sys.executable, str(SCRIPTS / 'fact_check.py')]
        passed = subprocess.run(cmd + ['verify', '--run-dir', str(self.run)], capture_output=True, text=True)
        self.assertEqual(passed.returncode, 0, passed.stdout)
        self.assertEqual(json.loads(passed.stdout)['status'], 'contract_pass')
        old = path.read_bytes()
        refused = subprocess.run(cmd + ['prepare', '--run-dir', str(self.run)], capture_output=True, text=True)
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(path.read_bytes(), old)

    def test_missing_original_retrieval_record_blocks(self):
        del self.source['retrieval_record']
        rows(self.run / 'triage/corpus.jsonl', [self.source])
        self.blocked('no retrieval_record')

    def test_changed_original_response_invalidates_review(self):
        record = fc.load_json(self.run / 'acquisition' / self.source['retrieval_record'])
        path = self.run / 'acquisition' / record['content_file']
        path.write_text('An amended original response.')
        self.blocked('original retrieval response hash mismatch')

    def test_false_original_content_hash_fails(self):
        path = self.run / 'acquisition' / self.source['retrieval_record']
        record = fc.load_json(path)
        record['content_sha256'] = '0' * 64
        path.write_text(json.dumps(record))
        self.blocked('original retrieval response hash mismatch')

    def test_failed_http_retrieval_is_not_evidence(self):
        path = self.run / 'acquisition' / self.source['retrieval_record']
        record = fc.load_json(path)
        record.update(kind='http_response', http_status=403)
        path.write_text(json.dumps(record))
        self.blocked('unsuccessful HTTP retrieval')

    def test_extraction_cannot_replace_original_response(self):
        path = self.run / 'acquisition' / self.source['retrieval_record']
        record = fc.load_json(path)
        record.update(content_file=self.source['raw_file'], content_sha256=fc.sha(self.raw_path.read_bytes()))
        path.write_text(json.dumps(record))
        self.blocked('preserve original response separately')

    def test_retrieval_identity_cannot_point_to_another_source(self):
        path = self.run / 'acquisition' / self.source['retrieval_record']
        record = fc.load_json(path)
        record['requested_url'] = 'https://different.example/'
        path.write_text(json.dumps(record))
        self.blocked('retrieval record identity mismatch')

    def test_unsafe_calculation_is_rejected_as_data(self):
        self.claim['calculations'] = [dict(operation='__import__("os").system("echo unsafe")', inputs=[],
                                           decimal_places=0, rounding='half_even', reported_value='100', rendered='100',
                                           unit='participants', rationale='Synthetic injection must fail schema validation.')]
        self.sign_claims()
        self.blocked('fact_check.schema.json')

    def test_scalar_manifest_cannot_leave_stale_success(self):
        (self.run / 'qa/fact_check.json').write_text(json.dumps(self.doc))
        result_path = self.run / 'qa/fact_check_result.json'
        for malformed in ('null', '[]', '"not an object"'):
            with self.subTest(manifest=malformed):
                result_path.write_text('{"status":"contract_pass"}')
                (self.run / 'run_manifest.json').write_text(malformed)
                proc = subprocess.run([sys.executable, str(SCRIPTS / 'fact_check.py'), 'verify', '--run-dir', str(self.run)], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 1)
                self.assertEqual(json.loads(result_path.read_text())['status'], 'blocked')

    def test_short_tables_footnotes_headings_and_methodology_are_inventoried(self):
        text = '# Cats fly.\n\n## Methodology\nCosts doubled.\n| Treatment | 25% |\n[^1]: It failed.\n'
        self.assertEqual([u['line'] for u in fc.inventory(text)], [1, 3, 4, 5, 6])

    def test_result_symlink_cannot_overwrite_report(self):
        (self.run / 'qa/fact_check.json').write_text(json.dumps(self.doc))
        (self.run / 'qa/fact_check_result.json').symlink_to(self.report_path)
        before = self.report_path.read_bytes()
        proc = subprocess.run([sys.executable, str(SCRIPTS / 'fact_check.py'), 'verify', '--run-dir', str(self.run)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.report_path.read_bytes(), before)

    def test_synthetic_approvals_are_not_a_semantic_truth_oracle(self):
        # Deliberately fabricate reviewer attestations for a reversed relation.
        # This documents a boundary, not a way to perform real review.
        self.quote = 'Cats chase dogs.'
        self.ev.update(quote=self.quote, evidence_id=compute_evidence_id(self.sid, self.quote, 'Enrollment'))
        self.raw_path.write_text(self.quote)
        persist_retrieval(self.run, self.source, self.quote)
        rows(self.run / 'triage/corpus.jsonl', [self.source])
        rows(self.run / 'evidence/evidence.jsonl', [self.ev])
        self.report_path.write_text('## Finding\nDogs chase cats [1].\n\n## Bibliography\n[1] [Trial record](' + self.url + '). URL: <' + self.url + '>\n')
        self.claim.update(text='Dogs chase cats.', locations=[dict(line=2, excerpt='Dogs chase cats [1].')])
        self.claim['evidence_links'][0]['evidence_id'] = self.ev['evidence_id']
        self.refresh()
        result = fc.verify(self.run, self.doc)
        self.assertEqual(result['status'], 'contract_pass')
        self.assertIn('not proof of truth', result['assurance'])

    def test_whitespace_review_rationale_is_not_completed_work(self):
        self.claim['red_team']['checks']['cherry_picking']['rationale'] = ' ' * 50
        self.blocked()

    def test_wrong_canonical_url_cannot_reuse_identity_hash(self):
        self.source['canonical_locator'] = 'https://unrelated.example/'
        self.source['source_id'] = compute_source_id(self.source['canonical_locator'])
        # Keep source/evidence internally consistent to isolate URL identity.
        self.ev['source_id'] = self.source['source_id']
        self.ev['evidence_id'] = compute_evidence_id(self.ev['source_id'], self.ev['quote'], self.ev['locator'])
        persist_retrieval(self.run, self.source, self.quote)
        rows(self.run / 'triage/corpus.jsonl', [self.source])
        rows(self.run / 'evidence/evidence.jsonl', [self.ev])
        self.blocked('canonical identity disagrees')

    def test_strict_citation_compatibility_uses_same_gate_without_network(self):
        (self.run / 'qa/fact_check.json').write_text(json.dumps(self.doc))
        proc = subprocess.run([sys.executable, str(SCRIPTS / 'verify_citations.py'), '--report', str(self.report_path), '--strict'], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(json.loads(proc.stdout)['status'], 'contract_pass')

    def test_strict_citation_command_cannot_verify_a_different_report(self):
        (self.run / 'qa/fact_check.json').write_text(json.dumps(self.doc))
        other = self.report_path.with_name('other.md')
        other.write_text('An unreviewed different report.')
        proc = subprocess.run([sys.executable, str(SCRIPTS / 'verify_citations.py'), '--report', str(other), '--strict'], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)['status'], 'blocked')

    def test_external_qa_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as out:
            (self.run / 'qa').rmdir()
            (self.run / 'qa').symlink_to(out)
            proc = subprocess.run([sys.executable, str(SCRIPTS / 'fact_check.py'), 'prepare', '--run-dir', str(self.run)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(list(Path(out).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
