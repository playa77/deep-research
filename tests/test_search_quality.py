"""Adversarial search-control tests using synthetic local responses only."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from fact_check import ContractError
from search_quality import assess_queries, check_acquisition
from search_fixtures import search_record


class SearchQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name)
        self.control = search_record(self.run, 'control', query_role='positive_control',
                                     expected_match='Synthetic known item')
        self.negative = search_record(self.run, 'negative', outcome='no_results',
                                      control_query_id='control')

    def test_working_scoped_negative_with_known_item_is_usable(self):
        result = assess_queries(self.run, [self.control, self.negative])
        self.assertEqual(result['usable_query_ids'], ['negative'])
        self.assertEqual(result['validated_negative_query_ids'], ['negative'])
        self.assertEqual(result['unresolved_searches'], [])

    def test_missing_control_or_failed_known_item_blocks_negative(self):
        for outcome in ('missing', 'no_results', 'error', 'blocked', 'inconclusive'):
            with self.subTest(outcome=outcome), self.assertRaisesRegex(ContractError, 'positive control'):
                queries = [self.negative]
                if outcome != 'missing':
                    control = dict(self.control, outcome=outcome, result_count=0,
                                   limitation='Synthetic known item was not recovered')
                    queries.insert(0, control)
                assess_queries(self.run, queries)

    def test_control_must_recover_the_expected_item_in_saved_response(self):
        self.control['expected_match'] = 'An item that was never returned'
        with self.assertRaisesRegex(ContractError, 'expected item'):
            assess_queries(self.run, [self.control, self.negative])

    def test_control_cannot_come_from_other_route_filters_session_or_tool(self):
        for field in ('tool', 'search_surface', 'search_scope', 'search_session'):
            with self.subTest(field=field), self.assertRaisesRegex(ContractError, 'different search'):
                control = dict(self.control, **{field: 'different'})
                assess_queries(self.run, [control, self.negative])

    def test_inconclusive_attempts_and_controls_cannot_fulfill_angle(self):
        failed = search_record(self.run, 'failed', outcome='inconclusive')
        result = assess_queries(self.run, [self.control, failed])
        self.assertEqual(result['usable_query_ids'], [])
        self.assertEqual(result['unresolved_searches'][0]['query_id'], 'failed')
        with self.assertRaisesRegex(ContractError, 'no usable search'):
            check_acquisition(self.run, [self.control, failed], [{'name': 'official-records'}])

    def test_general_search_cannot_replace_required_native_catalogue(self):
        row = search_record(self.run)
        angle = {'name': 'official-records', 'required_search_surfaces': ['native-catalogue']}
        with self.assertRaisesRegex(ContractError, 'required search surface'):
            check_acquisition(self.run, [row], [angle])
        row['search_surface'] = 'native-catalogue'
        self.assertEqual(check_acquisition(self.run, [row], [angle])['usable_query_ids'], ['q_test'])

    def test_saved_response_edits_including_controls_invalidate_check(self):
        for row in (self.control, self.negative):
            path = self.run / 'acquisition' / row['response_file']
            original = path.read_bytes()
            path.write_bytes(original + b'changed')
            with self.assertRaisesRegex(ContractError, 'stale search response'):
                assess_queries(self.run, [self.control, self.negative])
            path.write_bytes(original)

    def test_failed_retry_is_retained_and_successful_retry_can_cover_angle(self):
        failed = search_record(self.run, 'failed', outcome='blocked')
        retry = search_record(self.run, 'retry')
        result = check_acquisition(self.run, [failed, retry], [{'name': 'official-records'}])
        self.assertEqual(result['usable_query_ids'], ['retry'])
        self.assertEqual(result['unresolved_searches'][0]['query_id'], 'failed')

    def test_missing_metadata_empty_plan_and_duplicate_executions_fail_closed(self):
        row = search_record(self.run)
        with self.assertRaisesRegex(ContractError, 'missing planned angles'):
            check_acquisition(self.run, [row], [])
        for field in ('outcome', 'response_file', 'execution_ref', 'search_scope'):
            incomplete = deepcopy(row)
            incomplete.pop(field)
            with self.subTest(field=field), self.assertRaises(ContractError):
                assess_queries(self.run, [incomplete])
        with self.assertRaisesRegex(ContractError, 'duplicate search execution'):
            assess_queries(self.run, [row, dict(row, query_id='other')])

    def test_noresults_cannot_be_null_count_and_error_requires_limitation(self):
        for changes in ({'result_count': None}, {'result_count': 1}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                assess_queries(self.run, [self.control, dict(self.negative, **changes)])
        failed = search_record(self.run, 'failed', outcome='error')
        failed.pop('limitation')
        with self.assertRaises(ContractError):
            assess_queries(self.run, [failed])


if __name__ == '__main__':
    unittest.main()
